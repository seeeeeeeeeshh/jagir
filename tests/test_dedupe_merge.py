from dataclasses import fields

from app.core.models import Opportunity
from app.dedupe.field_ownership import LINKEDIN_OWNED_FIELDS
from app.dedupe.merge import changed_fields, merge_linkedin_fields
from app.sync.scraped_types import ScrapedJob


def _existing(**overrides) -> Opportunity:
    defaults = dict(
        id=1,
        title="Old Title",
        company_id=1,
        salary_text="$50k",
        job_description="Old description",
        notes="My private notes",
        status="Interview 1",
        priority="High",
        linkedin_job_id="123",
    )
    defaults.update(overrides)
    return Opportunity(**defaults)


def _scraped(**overrides) -> ScrapedJob:
    defaults = dict(
        linkedin_job_id="123",
        linkedin_url="https://linkedin.com/jobs/view/123",
        canonical_linkedin_url="https://linkedin.com/jobs/view/123",
        title="New Title",
        company_name="Acme Inc.",
        salary_text="$60k",
        job_description=None,  # not captured this pass
    )
    defaults.update(overrides)
    return ScrapedJob(**defaults)


def test_merge_overwrites_only_linkedin_owned_fields():
    existing = _existing()
    merged = merge_linkedin_fields(existing, _scraped())

    assert merged.title == "New Title"
    assert merged.salary_text == "$60k"
    # user-owned fields untouched
    assert merged.notes == "My private notes"
    assert merged.status == "Interview 1"
    assert merged.priority == "High"


def test_merge_does_not_null_out_fields_scraper_didnt_capture():
    existing = _existing(job_description="Already have a full description from a prior detail fetch")
    merged = merge_linkedin_fields(existing, _scraped(job_description=None))

    assert merged.job_description == "Already have a full description from a prior detail fetch"


def test_merge_always_stamps_last_synced_at_and_metadata():
    existing = _existing(linkedin_last_synced_at=None, linkedin_metadata_json=None)
    scraped = _scraped(title=None, salary_text=None, job_description=None, raw_metadata={})

    merged = merge_linkedin_fields(existing, scraped)

    assert merged.linkedin_last_synced_at is not None
    assert merged.linkedin_metadata_json == "{}"
    # nothing else should have changed since every other field was None
    assert merged.title == existing.title
    assert merged.salary_text == existing.salary_text


def test_merge_changed_keys_are_subset_of_linkedin_owned_fields():
    existing = _existing()
    merged = merge_linkedin_fields(existing, _scraped())

    allowed = LINKEDIN_OWNED_FIELDS | {"linkedin_last_synced_at", "linkedin_metadata_json"}
    for f in fields(Opportunity):
        if getattr(existing, f.name) != getattr(merged, f.name):
            assert f.name in allowed, f"merge changed a non-LinkedIn-owned field: {f.name}"


def test_merge_never_mutates_existing_in_place():
    existing = _existing()
    original_title = existing.title
    merge_linkedin_fields(existing, _scraped())

    assert existing.title == original_title


def test_changed_fields_reports_what_actually_changed():
    existing = _existing()
    merged = merge_linkedin_fields(existing, _scraped())

    changed = changed_fields(existing, merged)

    assert "title" in changed
    assert "salary_text" in changed
    assert "linkedin_last_synced_at" in changed
    assert "notes" not in changed
