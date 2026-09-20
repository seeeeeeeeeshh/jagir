"""Imports edits made in an exported Jagir workbook back into the database
(app/excel/export.py is the other half of this round trip).

Only the "All Opportunities" sheet is read for opportunity data —
Applications/Research/Saved Jobs are just filtered views of the same rows
at export time. Reading all four risks an untouched, stale copy in one
sheet silently overwriting a fresh edit made only in another; reading just
the complete sheet avoids that ambiguity entirely. Edit opportunities in
"All Opportunities" for changes to be picked up.

For an EXISTING opportunity (matched by Application ID), only
USER_OWNED_FIELDS (app/dedupe/field_ownership.py) are written — the same
set the in-app UI and LinkedIn sync's merge.py already protect — so an
Excel edit can never clobber a field LinkedIn sync manages, and reassigning
a row's Company is not supported (out of scope: touches company stats).
For a NEW row (blank Application ID), every mapped column is used to build
the record, since there is no existing sync-managed data to protect;
`origin` is always stamped "excel_import" regardless of what the column
contains. A blank cell always clears the field it maps to (an Excel export
is a complete snapshot, not a partial one — unlike a LinkedIn scrape, where
a blank field means "not captured this pass", here it means the user
cleared it).

Computed/derived columns (Days Since Application, Urgency, Application
Health, Last Updated, and Companies' Opportunities/Applications/
Interviews/Offers/Rejections counts) are read-only and silently ignored —
they are recomputed (or, for Days Since Application, a live formula) at
export time, never stored, so there is nothing meaningful to import back.

Companies, Networking (Contacts), Prep Resources, and Interviews import
too, matched by name (Companies has no id column) or by their id column.
Company/Role on the Interviews sheet are display-only context; Application
ID is what actually links a row to an opportunity, and reassigning an
existing interview to a different application isn't supported.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import openpyxl

from app.core.enums import (
    EMPLOYMENT_TYPE_OPTIONS,
    INTERVIEW_STAGE_OPTIONS,
    POSITION_TYPE_OPTIONS,
    PREP_CATEGORY_OPTIONS,
    PRIORITY_OPTIONS,
    STATUS_OPTIONS,
    TARGET_REACH_SAFETY_OPTIONS,
    WORKPLACE_TYPE_OPTIONS,
)
from app.core.models import Contact, Interview, Opportunity, PrepResource
from app.db.repositories.companies_repo import CompaniesRepo, canonicalize
from app.db.repositories.contacts_repo import ContactsRepo
from app.db.repositories.cycles_repo import CyclesRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.db.repositories.prep_resources_repo import PrepResourcesRepo
from app.dedupe.field_ownership import USER_OWNED_FIELDS

_IMPORTABLE_SHEETS = {"All Opportunities", "Companies", "Networking", "Prep Resources", "Interviews"}
_KNOWN_UNIMPORTED_SHEETS = ("Applications", "Research", "Saved Jobs", "Dashboard", "Lists")


@dataclass
class ExcelImportResult:
    opportunities_created: int = 0
    opportunities_updated: int = 0
    companies_created: int = 0
    companies_updated: int = 0
    contacts_created: int = 0
    contacts_updated: int = 0
    prep_created: int = 0
    prep_updated: int = 0
    interviews_created: int = 0
    interviews_updated: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_sheets: list[str] = field(default_factory=list)

    @property
    def summary_text(self) -> str:
        parts = [
            f"{self.opportunities_created} opportunity(ies) created, {self.opportunities_updated} updated",
            f"{self.companies_created} compan{'y' if self.companies_created == 1 else 'ies'} created, "
            f"{self.companies_updated} updated",
            f"{self.contacts_created} contact(s) created, {self.contacts_updated} updated",
            f"{self.prep_created} prep resource(s) created, {self.prep_updated} updated",
            f"{self.interviews_created} interview(s) created, {self.interviews_updated} updated",
        ]
        text = "; ".join(parts)
        if self.errors:
            text += f" — {len(self.errors)} row issue(s)"
        return text


# Excel header -> Opportunity attribute, for columns that mean anything on
# import. Anything not listed (Days Since Application, Urgency, Application
# Health, Last Updated) is computed at export time and silently ignored
# here. Employment Type/External Application URL/Hiring Manager/Referral
# Contact/Networking Status/Last Contacted/Next Follow-up/Internship Start-
# End Date/Cover Letter Version/Origin/Rejection Date/Withdrawal Date/
# Latest Interview Stage-Date no longer exist as columns at all (trimmed —
# see opportunity_rows.py's COLUMNS comment for why) rather than being
# ignored on import; a workbook exported before that trim still imports
# fine since unknown headers are simply skipped.
_OPPORTUNITY_FIELD_MAP = {
    "Role": "title",
    "Position Type": "position_type",
    "Location": "location",
    "Workplace": "workplace_type",
    "Job URL": "job_url",
    "Source": "source",
    "Date Saved": "date_saved",
    "Date Applied": "date_applied",
    "Deadline": "application_deadline",
    "Status": "status",
    "Priority": "priority",
    "Target / Reach / Safety": "target_reach_safety",
    "Compensation": "salary_text",
    "Recruiter": "recruiter_name",
    "Offer Date": "offer_date",
    "Next Action": "next_action",
    "Notes": "notes",
    "Resume Version": "resume_version",
}

_ENUM_VALIDATORS = {
    "status": STATUS_OPTIONS,
    "priority": PRIORITY_OPTIONS,
    "target_reach_safety": TARGET_REACH_SAFETY_OPTIONS,
    "position_type": POSITION_TYPE_OPTIONS,
    "workplace_type": WORKPLACE_TYPE_OPTIONS,
    "employment_type": EMPLOYMENT_TYPE_OPTIONS,
}

# NOT NULL columns (schema.sql) among the mapped fields — a blank cell must
# never clear these to None (sqlite would reject the write outright), so it
# leaves the current value (existing row) or constructor default (new row)
# alone instead of the usual "blank clears it" rule.
_REQUIRED_FIELDS = {"source", "position_type", "status", "title"}


def _sheet_rows(ws) -> list[dict]:
    """Header row -> list of {header: value} dicts, skipping fully blank rows."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for raw in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in raw):
            continue
        out.append({headers[i]: raw[i] for i in range(len(headers)) if i < len(raw)})
    return out


def _clean(value) -> str | None:
    if value is None:
        return None
    # Date-formatted cells (Date Applied, Deadline, etc. — see export.py's
    # _DATE_FIELDS) round-trip through openpyxl as real datetime objects,
    # not text, so str(value) alone would produce "2026-01-05 00:00:00"
    # instead of the plain "YYYY-MM-DD" the rest of the app expects.
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    return s or None


def _parse_id(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def import_workbook(conn: sqlite3.Connection, file_path: str | Path) -> ExcelImportResult:
    wb = openpyxl.load_workbook(file_path, data_only=True)
    result = ExcelImportResult()

    opp_repo = OpportunitiesRepo(conn)
    company_repo = CompaniesRepo(conn)
    contacts_repo = ContactsRepo(conn)
    prep_repo = PrepResourcesRepo(conn)
    interviews_repo = InterviewsRepo(conn)

    if "All Opportunities" in wb.sheetnames:
        _import_opportunities(wb["All Opportunities"], opp_repo, company_repo, CyclesRepo(conn), result)
    else:
        result.errors.append('Sheet "All Opportunities" not found — opportunities not imported.')

    if "Companies" in wb.sheetnames:
        _import_companies(wb["Companies"], company_repo, result)

    if "Networking" in wb.sheetnames:
        _import_contacts(wb["Networking"], contacts_repo, company_repo, result)

    if "Prep Resources" in wb.sheetnames:
        _import_prep_resources(wb["Prep Resources"], prep_repo, result)

    if "Interviews" in wb.sheetnames:
        _import_interviews(wb["Interviews"], interviews_repo, opp_repo, result)

    for sheet_name in _KNOWN_UNIMPORTED_SHEETS:
        if sheet_name in wb.sheetnames:
            result.skipped_sheets.append(sheet_name)

    return result


def _apply_cycle(opp: Opportunity, row: dict, cycles_repo: CyclesRepo) -> None:
    """A named Cycle in the sheet assigns (creating the cycle if it's new). A
    blank cell leaves an existing row where it is and lets a brand-new row
    fall through to the cycle currently being worked in."""
    name = _clean(row.get("Cycle"))
    if name:
        opp.cycle_id = cycles_repo.get_or_create(name).id


def _import_opportunities(
    ws, opp_repo: OpportunitiesRepo, company_repo: CompaniesRepo, cycles_repo: CyclesRepo, result: ExcelImportResult
) -> None:
    for row_num, row in enumerate(_sheet_rows(ws), start=2):
        try:
            opp_id = _parse_id(row.get("Application ID"))

            if opp_id is not None:
                existing = opp_repo.get(opp_id)
                if existing is None:
                    result.errors.append(f"Row {row_num}: Application ID {opp_id} no longer exists — skipped.")
                    continue
                if not _apply_opportunity_fields(existing, row, result, row_num, allowed_fields=USER_OWNED_FIELDS):
                    continue
                _apply_cycle(existing, row, cycles_repo)
                opp_repo.update(existing, log_event=("excel_import", "Updated via Excel import"))
                result.opportunities_updated += 1
            else:
                company_name = _clean(row.get("Company"))
                title = _clean(row.get("Role"))
                if not company_name or not title:
                    result.errors.append(f"Row {row_num}: new row needs both Company and Role — skipped.")
                    continue
                company = company_repo.get_or_create(company_name)
                opp = Opportunity(
                    source="manual", origin="excel_import", status="Saved", company_id=company.id, title=title
                )
                if not _apply_opportunity_fields(opp, row, result, row_num, allowed_fields=None):
                    continue
                opp.origin = "excel_import"  # never let the sheet's Origin column override this
                _apply_cycle(opp, row, cycles_repo)
                opp_repo.create(opp, event_type="excel_import", description=f"Added via Excel import — {opp.title}")
                result.opportunities_created += 1
        except Exception as exc:
            result.errors.append(f"Row {row_num}: {exc}")


def _apply_opportunity_fields(
    opp: Opportunity, row: dict, result: ExcelImportResult, row_num: int, allowed_fields: set[str] | None
) -> bool:
    """Returns False if the row had a hard error (Role blank on a brand-new
    row) and should not be saved at all; True otherwise (individual invalid
    enum cells, or a blank cell for a required column, are skipped with a
    warning where relevant and leave the existing/default value alone —
    never fatal)."""
    for header, attr in _OPPORTUNITY_FIELD_MAP.items():
        if allowed_fields is not None and attr not in allowed_fields:
            continue  # LinkedIn-owned or otherwise protected on an existing row
        if header not in row:
            continue
        value = _clean(row.get(header))
        if attr in _ENUM_VALIDATORS and value is not None and value not in _ENUM_VALIDATORS[attr]:
            result.errors.append(f"Row {row_num}: invalid {header} '{value}' — left unchanged.")
            continue
        if value is None and attr in _REQUIRED_FIELDS:
            if attr == "title":
                result.errors.append(f"Row {row_num}: Role cannot be blank — row skipped.")
                return False
            continue  # source/position_type/status are NOT NULL — a blank cell leaves the current value alone
        setattr(opp, attr, value)
    return True


def _import_companies(ws, company_repo: CompaniesRepo, result: ExcelImportResult) -> None:
    existing_names = {c.canonical_name for c in company_repo.list_all()}
    for row_num, row in enumerate(_sheet_rows(ws), start=2):
        name = _clean(row.get("Company"))
        if not name:
            continue
        is_new = canonicalize(name) not in existing_names
        company = company_repo.get_or_create(name)

        website = _clean(row.get("Website"))
        industry = _clean(row.get("Industry"))
        notes = _clean(row.get("Notes"))
        changed = website != company.website or industry != company.industry or notes != company.notes
        if changed:
            company.website, company.industry, company.notes = website, industry, notes
            company_repo.update(company)

        if is_new:
            result.companies_created += 1
            existing_names.add(canonicalize(name))
        elif changed:
            result.companies_updated += 1


def _import_contacts(
    ws, contacts_repo: ContactsRepo, company_repo: CompaniesRepo, result: ExcelImportResult
) -> None:
    for row_num, row in enumerate(_sheet_rows(ws), start=2):
        try:
            contact_id = _parse_id(row.get("Contact ID"))
            name = _clean(row.get("Name"))
            company_name = _clean(row.get("Company"))
            company_id = company_repo.get_or_create(company_name).id if company_name else None

            if contact_id is not None:
                existing = contacts_repo.get(contact_id)
                if existing is None:
                    result.errors.append(f"Row {row_num}: Contact ID {contact_id} no longer exists — skipped.")
                    continue
                if not name:
                    result.errors.append(f"Row {row_num}: Name cannot be blank — row skipped.")
                    continue
                existing.name = name
                existing.company_id = company_id
                existing.title = _clean(row.get("Title"))
                existing.linkedin_url = _clean(row.get("LinkedIn URL"))
                existing.relationship = _clean(row.get("Relationship / Status"))
                existing.email = _clean(row.get("Email"))
                existing.phone = _clean(row.get("Phone"))
                existing.notes = _clean(row.get("Notes"))
                contacts_repo.update(existing)
                result.contacts_updated += 1
            else:
                if not name:
                    result.errors.append(f"Row {row_num}: new contact needs a Name — skipped.")
                    continue
                contacts_repo.create(
                    Contact(
                        name=name,
                        company_id=company_id,
                        title=_clean(row.get("Title")),
                        linkedin_url=_clean(row.get("LinkedIn URL")),
                        relationship=_clean(row.get("Relationship / Status")),
                        email=_clean(row.get("Email")),
                        phone=_clean(row.get("Phone")),
                        notes=_clean(row.get("Notes")),
                    )
                )
                result.contacts_created += 1
        except Exception as exc:
            result.errors.append(f"Row {row_num}: {exc}")


def _import_prep_resources(ws, prep_repo: PrepResourcesRepo, result: ExcelImportResult) -> None:
    for row_num, row in enumerate(_sheet_rows(ws), start=2):
        try:
            resource_id = _parse_id(row.get("Resource ID"))
            title = _clean(row.get("Title"))
            category = _clean(row.get("Category"))
            category_valid = category is None or category in PREP_CATEGORY_OPTIONS
            if not category_valid:
                result.errors.append(f"Row {row_num}: invalid Category '{category}' — left unchanged.")

            if resource_id is not None:
                existing = prep_repo.get(resource_id)
                if existing is None:
                    result.errors.append(f"Row {row_num}: Resource ID {resource_id} no longer exists — skipped.")
                    continue
                if not title:
                    result.errors.append(f"Row {row_num}: Title cannot be blank — row skipped.")
                    continue
                existing.title = title
                if category_valid:
                    existing.category = category
                existing.url_or_path = _clean(row.get("URL / Path"))
                existing.tags = _clean(row.get("Tags"))
                existing.notes = _clean(row.get("Notes"))
                prep_repo.update(existing)
                result.prep_updated += 1
            else:
                if not title:
                    result.errors.append(f"Row {row_num}: new prep resource needs a Title — skipped.")
                    continue
                prep_repo.create(
                    PrepResource(
                        title=title,
                        category=category if category_valid else None,
                        url_or_path=_clean(row.get("URL / Path")),
                        tags=_clean(row.get("Tags")),
                        notes=_clean(row.get("Notes")),
                    )
                )
                result.prep_created += 1
        except Exception as exc:
            result.errors.append(f"Row {row_num}: {exc}")


def _import_interviews(
    ws, interviews_repo: InterviewsRepo, opp_repo: OpportunitiesRepo, result: ExcelImportResult
) -> None:
    """Company/Role on this sheet are display-only context (mirroring the
    Excel export) — Application ID is the real link, and reassigning an
    existing interview to a different application isn't supported, same as
    Company reassignment isn't supported on the opportunities import."""
    for row_num, row in enumerate(_sheet_rows(ws), start=2):
        try:
            interview_id = _parse_id(row.get("Interview ID"))
            stage = _clean(row.get("Stage"))
            stage_valid = stage is None or stage in INTERVIEW_STAGE_OPTIONS
            if not stage_valid:
                suffix = "left unchanged" if interview_id is not None else "row skipped"
                result.errors.append(f"Row {row_num}: invalid Stage '{stage}' — {suffix}.")
                if interview_id is None:
                    continue

            if interview_id is not None:
                existing = interviews_repo.get(interview_id)
                if existing is None:
                    result.errors.append(f"Row {row_num}: Interview ID {interview_id} no longer exists — skipped.")
                    continue
                if stage_valid and stage is not None:
                    existing.stage = stage
                existing.scheduled_at = _clean(row.get("Scheduled At"))
                existing.completed_at = _clean(row.get("Completed At"))
                existing.outcome = _clean(row.get("Outcome"))
                existing.prep_notes = _clean(row.get("Prep Notes"))
                existing.feedback_notes = _clean(row.get("Feedback Notes"))
                interviews_repo.update(existing)
                result.interviews_updated += 1
            else:
                opp_id = _parse_id(row.get("Application ID"))
                if opp_id is None or opp_repo.get(opp_id) is None:
                    result.errors.append(f"Row {row_num}: new interview needs a valid Application ID — skipped.")
                    continue
                if stage is None:
                    result.errors.append(f"Row {row_num}: new interview needs a Stage — skipped.")
                    continue
                interviews_repo.create(
                    Interview(
                        opportunity_id=opp_id,
                        stage=stage,
                        scheduled_at=_clean(row.get("Scheduled At")),
                        completed_at=_clean(row.get("Completed At")),
                        outcome=_clean(row.get("Outcome")),
                        prep_notes=_clean(row.get("Prep Notes")),
                        feedback_notes=_clean(row.get("Feedback Notes")),
                    )
                )
                result.interviews_created += 1
        except Exception as exc:
            result.errors.append(f"Row {row_num}: {exc}")
