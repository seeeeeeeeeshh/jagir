from app.core.models import Opportunity
from app.core.status_transitions import apply_status_change


def test_leaving_pre_application_status_stamps_date_applied():
    opp = Opportunity(title="x", status="Saved", date_applied=None)

    stamped = apply_status_change(opp, "Applied")

    assert stamped is True
    assert opp.status == "Applied"
    assert opp.date_applied is not None


def test_moving_between_pre_application_statuses_does_not_stamp():
    opp = Opportunity(title="x", status="Saved", date_applied=None)

    stamped = apply_status_change(opp, "Interested")

    assert stamped is False
    assert opp.date_applied is None


def test_existing_date_applied_is_never_overwritten():
    opp = Opportunity(title="x", status="Applied", date_applied="2026-01-01")

    stamped = apply_status_change(opp, "Interview 1")

    assert stamped is False
    assert opp.date_applied == "2026-01-01"


def test_moving_back_to_a_pre_application_status_does_not_clear_date_applied():
    opp = Opportunity(title="x", status="Applied", date_applied="2026-01-01")

    apply_status_change(opp, "Saved")

    assert opp.status == "Saved"
    assert opp.date_applied == "2026-01-01"  # not cleared — only ever set, never unset by this helper
