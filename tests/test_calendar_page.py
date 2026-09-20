from datetime import date, datetime, timedelta, timezone

from app.integrations.google_calendar import CalendarEvent
import pytest

from app.ui.pages.calendar_page import (
    _range_bounds_utc,
    bucket_events_by_day,
    event_time_label,
    format_clock,
    month_grid_days,
    parse_quick_add,
)


def _event(event_id: str, start: str, summary: str = "Event") -> CalendarEvent:
    return CalendarEvent(id=event_id, summary=summary, start=start, html_link="https://cal/" + event_id)


def test_buckets_timed_and_all_day_events_by_local_date():
    today = date(2026, 9, 20)
    events = [
        _event("1", "2026-09-20T14:00:00+05:45", "Interview"),
        _event("2", "2026-09-22", "Deadline"),
    ]
    buckets = bucket_events_by_day(events, today, tz=timezone(timedelta(hours=5, minutes=45)))

    assert [e.id for e in buckets[date(2026, 9, 20)]] == ["1"]
    assert [e.id for e in buckets[date(2026, 9, 22)]] == ["2"]
    assert buckets[date(2026, 9, 21)] == []


def test_window_covers_exactly_num_days_starting_at_start_day():
    today = date(2026, 9, 20)
    buckets = bucket_events_by_day([], today, num_days=7)

    assert list(buckets.keys()) == [date(2026, 9, 20 + i) for i in range(7)]


def test_events_outside_the_window_are_dropped_not_errored():
    today = date(2026, 9, 20)
    events = [_event("1", "2026-10-05T09:00:00+00:00")]
    buckets = bucket_events_by_day(events, today, num_days=7)

    assert all(e == [] for e in buckets.values())


def test_unparseable_start_is_skipped_not_raised():
    today = date(2026, 9, 20)
    events = [_event("1", "not-a-date"), _event("2", "2026-09-20T14:00:00+00:00")]
    buckets = bucket_events_by_day(events, today, num_days=1, tz=timezone.utc)

    assert [e.id for e in buckets[today]] == ["2"]


def test_events_within_a_day_sort_by_start_time():
    today = date(2026, 9, 20)
    events = [
        _event("late", "2026-09-20T16:00:00+00:00"),
        _event("early", "2026-09-20T09:00:00+00:00"),
    ]
    buckets = bucket_events_by_day(events, today, num_days=1, tz=timezone.utc)

    assert [e.id for e in buckets[today]] == ["early", "late"]


def test_month_grid_days_covers_the_whole_month():
    # September 2026: 1st is a Tuesday, 30th is a Wednesday
    days = month_grid_days(date(2026, 9, 15))

    for d in range(1, 31):
        assert date(2026, 9, d) in days


def test_month_grid_days_is_always_a_multiple_of_seven():
    for anchor in (date(2026, 2, 1), date(2026, 9, 15), date(2024, 2, 29)):
        assert len(month_grid_days(anchor)) % 7 == 0


def test_month_grid_days_starts_on_monday_and_ends_on_sunday():
    days = month_grid_days(date(2026, 9, 15))

    assert days[0].weekday() == 0  # Monday
    assert days[-1].weekday() == 6  # Sunday


def test_month_grid_days_handles_december_to_january_rollover():
    days = month_grid_days(date(2026, 12, 15))

    for d in range(1, 32):
        assert date(2026, 12, d) in days
    # Dec 31 2026 is a Thursday, so the grid must pad forward into January
    # 2027 to complete that week.
    assert date(2027, 1, 3) in days
    assert date(2026, 11, 30) in days  # Dec 1 is a Tuesday — pads back to Monday Nov 30


def test_range_bounds_utc_pads_one_day_on_each_side():
    days = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]

    time_min, time_max = _range_bounds_utc(days)

    assert time_min.startswith("2026-08-31")
    assert time_max.startswith("2026-09-05")


# -- quick-add: a time typed in the title makes a timed event ---------------


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("Recruiter call 3pm", ("Recruiter call", "15:00")),
        ("Recruiter call at 3:30 PM", ("Recruiter call", "15:30")),
        ("9am standup", ("standup", "09:00")),
        ("Lunch 12pm", ("Lunch", "12:00")),        # noon
        ("Midnight thing 12am", ("Midnight thing", "00:00")),
        ("Interview 15:45", ("Interview", "15:45")),
        ("Interview at 09:05", ("Interview", "09:05")),
        ("Google OA 2:00pm - HackerRank", ("Google OA - HackerRank", "14:00")),
    ],
)
def test_quick_add_extracts_a_time(typed, expected):
    assert parse_quick_add(typed) == expected


@pytest.mark.parametrize(
    "typed",
    [
        "Submit application",
        "Interview 2",          # a round number is not a time
        "Round 3 prep",
        "Apply to 15 companies",
        "13pm nonsense",        # invalid 12-hour value
        "Call 3:75pm",          # invalid minutes
        "",
        None,
    ],
)
def test_quick_add_leaves_ambiguous_text_as_all_day(typed):
    title, when = parse_quick_add(typed)
    assert when is None
    assert title == (typed or "").strip()


def test_quick_add_never_returns_an_empty_title():
    # Typing only a time keeps it as the title rather than creating a blank event.
    assert parse_quick_add("3pm") == ("3pm", None)


def test_format_clock():
    assert format_clock("15:30") == "3:30 PM"
    assert format_clock("09:05") == "9:05 AM"
    assert format_clock("00:00") == "12:00 AM"


# -- timezone: everything is shown in the viewer's timezone -----------------

UTC_PLUS_8 = timezone(timedelta(hours=8))
NEW_YORK_SUMMER = timezone(timedelta(hours=-4))


def test_event_is_bucketed_by_the_viewers_day_not_the_calendars():
    # 11:30 PM on Sep 20 in New York is 11:30 AM on Sep 21 for someone at UTC+8.
    # Bucketing by the offset Google happened to send would put it on Sep 20.
    events = [_event("1", "2026-09-20T23:30:00-04:00", "Late call")]
    buckets = bucket_events_by_day(events, date(2026, 9, 20), num_days=3, tz=UTC_PLUS_8)

    assert buckets[date(2026, 9, 20)] == []
    assert [e.id for e in buckets[date(2026, 9, 21)]] == ["1"]


def test_time_label_is_converted_to_the_viewers_timezone():
    assert event_time_label("2026-09-20T23:30:00-04:00", tz=UTC_PLUS_8) == "11:30"
    assert event_time_label("2026-09-21T11:30:00+08:00", tz=NEW_YORK_SUMMER) == "23:30"


def test_time_label_is_none_for_all_day_events():
    assert event_time_label("2026-09-30") is None


def test_all_day_events_stay_on_their_own_date_in_any_timezone():
    events = [_event("1", "2026-09-30", "Darshan day")]
    for tz in (UTC_PLUS_8, NEW_YORK_SUMMER, timezone.utc):
        buckets = bucket_events_by_day(events, date(2026, 9, 29), num_days=3, tz=tz)
        assert [e.id for e in buckets[date(2026, 9, 30)]] == ["1"]


def test_a_quick_added_time_displays_at_the_same_hour():
    # Quick-add sends "3pm" as machine-local time; the API echoes it back in
    # the calendar's timezone. Whatever that is, the page must show 15:00 again,
    # on the day it was added.
    for machine_tz, calendar_tz in (
        (UTC_PLUS_8, NEW_YORK_SUMMER),
        (NEW_YORK_SUMMER, UTC_PLUS_8),
        (UTC_PLUS_8, UTC_PLUS_8),
    ):
        sent = datetime(2026, 9, 24, 15, 0, tzinfo=machine_tz)
        echoed = sent.astimezone(calendar_tz).isoformat()

        buckets = bucket_events_by_day([_event("1", echoed)], date(2026, 9, 23), num_days=3, tz=machine_tz)

        assert event_time_label(echoed, tz=machine_tz) == "15:00"
        assert [e.id for e in buckets[date(2026, 9, 24)]] == ["1"]


def test_events_within_a_day_sort_all_day_first_then_by_local_time():
    events = [
        _event("late", "2026-09-24T22:00:00+08:00"),
        _event("allday", "2026-09-24"),
        _event("early", "2026-09-24T09:00:00+08:00"),
    ]
    day = bucket_events_by_day(events, date(2026, 9, 24), num_days=1, tz=UTC_PLUS_8)[date(2026, 9, 24)]
    assert [e.id for e in day] == ["allday", "early", "late"]
