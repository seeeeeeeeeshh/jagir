"""The one trusted path for LinkedIn sync to overwrite fields on an existing
opportunity. Nothing else in the codebase should apply a scraped record onto
an existing row — every write goes through here so LINKEDIN_OWNED_FIELDS is
enforced in exactly one place.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone

from app.core.models import Opportunity
from app.dedupe.field_ownership import LINKEDIN_OWNED_FIELDS
from app.sync.scraped_types import ScrapedJob

# Stamped on every merge regardless of whether anything else changed —
# "synced, found nothing new" is itself information worth recording.
_ALWAYS_WRITTEN_FIELDS = {"linkedin_last_synced_at", "linkedin_metadata_json"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def merge_linkedin_fields(existing: Opportunity, scraped: ScrapedJob) -> Opportunity:
    """Returns a NEW Opportunity: `existing` with every LinkedIn-owned field
    overwritten from `scraped` (mapped field-for-field) wherever `scraped`
    actually captured a value this run, plus a fresh sync timestamp. Never
    mutates `existing` in place. A `None` on `scraped` means "not captured
    this pass" (e.g. a list-only scrape without a detail fetch), not "clear
    it" — so it never blanks out a previously-synced value.
    """
    scraped_dict = asdict(scraped)
    updates = {
        field_name: scraped_dict[field_name]
        for field_name in LINKEDIN_OWNED_FIELDS
        if field_name in scraped_dict and scraped_dict[field_name] is not None
    }
    updates["linkedin_last_synced_at"] = _now()
    updates["linkedin_metadata_json"] = json.dumps(scraped.raw_metadata)

    return replace(existing, **updates)


def changed_fields(existing: Opportunity, merged: Opportunity) -> list[str]:
    """Field names that differ between `existing` and `merged` — used to log
    a human-readable activity entry for the merge."""
    return [
        f
        for f in LINKEDIN_OWNED_FIELDS | _ALWAYS_WRITTEN_FIELDS
        if getattr(existing, f, None) != getattr(merged, f, None)
    ]
