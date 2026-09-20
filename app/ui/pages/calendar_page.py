import re
from datetime import date, datetime, time, timedelta, tzinfo

from nicegui import run, ui

from app.config import settings
from app.core.errors import humanize_exception
from app.integrations import google_calendar
from app.ui.layout import page_frame

_WEEK_LENGTH = 7
_MONTH_CHIP_LIMIT = 3  # events shown per month cell before "+N more"

# "3pm", "3:30 pm", "at 3pm" -- an am/pm marker is required so bare numbers
# in a title ("Round 2", "Interview 2") are never mistaken for a time.
_TIME_AMPM = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
# "15:00", "at 09:30" -- unambiguous 24-hour form.
_TIME_24H = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b")


def parse_quick_add(text: str | None) -> tuple[str, str | None]:
    """Splits what was typed into the quick-add box into (title, "HH:MM" or
    None). A time typed anywhere in the title turns the event from all-day
    into a timed one, so "Recruiter call 3pm" needs no second dialog. If
    removing the time would leave nothing, the text is left as the title."""
    text = (text or "").strip()
    match = _TIME_AMPM.search(text)
    hhmm = None
    if match:
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if 1 <= hour <= 12 and minute < 60:
            hhmm = f"{hour % 12 + (12 if match.group(3).lower() == 'pm' else 0):02d}:{minute:02d}"
    if hhmm is None:
        match = _TIME_24H.search(text)
        if match:
            hhmm = f"{int(match.group(1)):02d}:{match.group(2)}"
    if hhmm is None:
        return text, None

    title = re.sub(r"\s{2,}", " ", (text[: match.start()] + " " + text[match.end() :])).strip(" -,:")
    return (title, hhmm) if title else (text, None)


def format_clock(hhmm: str) -> str:
    """"15:30" -> "3:30 PM"."""
    return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")


def _local(raw: str, tz: tzinfo | None = None) -> datetime:
    """A timed event's start as wall-clock time in `tz` (default: this
    machine's own timezone). Google returns times in the *calendar's*
    timezone, but quick-add interprets what you type in the machine's, so
    everything shown is converted to the machine's timezone to keep the two
    consistent (a "3pm" event you add must display at 3pm, on that day)."""
    return datetime.fromisoformat(raw).astimezone(tz)


def event_time_label(raw_start: str, tz: tzinfo | None = None) -> str | None:
    """"HH:MM" for a timed event, None for an all-day one."""
    if len(raw_start) == 10:
        return None
    return _local(raw_start, tz).strftime("%H:%M")


def bucket_events_by_day(events, start_day: date, num_days: int = _WEEK_LENGTH, tz: tzinfo | None = None) -> dict[date, list]:
    """Groups events (google_calendar.CalendarEvent, whose `start` is either
    a plain "YYYY-MM-DD" or a full RFC3339 datetime) by calendar day in `tz`
    (default: this machine's timezone), for a `num_days`-day window starting
    at `start_day`. All-day events have no time, so their date is used as-is.
    Events outside the window, or with an unparseable `start`, are dropped —
    this is a display window, not a data source."""
    buckets: dict[date, list] = {start_day + timedelta(days=i): [] for i in range(num_days)}
    for event in events:
        raw = event.start
        if not raw:
            continue
        try:
            event_date = date.fromisoformat(raw) if len(raw) == 10 else _local(raw, tz).date()
        except ValueError:
            continue
        if event_date in buckets:
            buckets[event_date].append(event)
    for day_events in buckets.values():
        # All-day events first, then timed ones by their local time of day.
        day_events.sort(key=lambda e: (len(e.start) > 10, _local(e.start, tz).time() if len(e.start) > 10 else time.min))
    return buckets


def month_grid_days(anchor: date) -> list[date]:
    """Every day shown in a month view for the month containing `anchor`:
    the whole month, padded out to full Mon-Sun weeks on both ends so the
    grid is always a clean multiple of 7."""
    first_of_month = anchor.replace(day=1)
    start = first_of_month - timedelta(days=first_of_month.weekday())
    next_month = date(first_of_month.year + (first_of_month.month == 12), first_of_month.month % 12 + 1, 1)
    last_of_month = next_month - timedelta(days=1)
    end = last_of_month + timedelta(days=6 - last_of_month.weekday())
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _range_bounds_utc(days: list[date]) -> tuple[str, str]:
    """A one-day buffer on each side absorbs timezone-offset edge cases
    (an event near midnight in the user's own timezone) — bucket_events_by_day
    filters anything outside the actual display window anyway, using each
    event's own local date, not these UTC bounds."""
    from datetime import time as _time
    from datetime import timezone as _timezone

    start = datetime.combine(days[0] - timedelta(days=1), _time.min, tzinfo=_timezone.utc)
    end = datetime.combine(days[-1] + timedelta(days=2), _time.min, tzinfo=_timezone.utc)
    return start.isoformat(), end.isoformat()


def _long_day(day: date) -> str:
    return f"{day.strftime('%A, %B')} {day.day}"


def _week_title(days: list[date]) -> str:
    first, last = days[0], days[-1]
    if first.month == last.month:
        return f"{first.strftime('%B')} {first.day} – {last.day}, {last.year}"
    return f"{first.strftime('%b')} {first.day} – {last.strftime('%b')} {last.day}, {last.year}"


def register():
    @ui.page("/calendar")
    def calendar_page():
        with page_frame("Calendar", "/calendar", show_data_actions=False):
            if not settings.google_calendar_configured:
                with ui.card().classes("w-full"):
                    ui.label("Google Calendar isn't set up yet").classes("jg-panel-title")
                    ui.label(
                        "Jagir needs its own Google OAuth client to talk to your calendar — Google "
                        "requires this per-app, there's no way around it. It's free and takes a few "
                        "minutes:"
                    ).classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                    steps = [
                        "Go to console.cloud.google.com and create a project (or pick an existing one).",
                        '"APIs & Services" → "Enabled APIs" → enable the "Google Calendar API".',
                        '"APIs & Services" → "OAuth consent screen" → External → add your own Google '
                        'account under "Test users" (this keeps the app unpublished/private, which is fine).',
                        '"APIs & Services" → "Credentials" → "Create Credentials" → "OAuth client ID" → '
                        'Application type: Web application.',
                        f'Under "Authorized redirect URIs" add exactly: {settings.google_oauth_redirect_uri}',
                        "Copy the Client ID and Client Secret it gives you into Jagir's .env file as "
                        "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, then restart Jagir.",
                    ]
                    with ui.column().classes("gap-1 mt-3"):
                        for i, step in enumerate(steps, start=1):
                            ui.label(f"{i}. {step}").classes("text-sm")
                return

            # -- adding events ------------------------------------------------

            def open_add_event_dialog(prefill_date: date | None = None, prefill_title: str = ""):
                with ui.dialog() as dialog, ui.card().classes("w-[420px] max-w-full"):
                    ui.label("Add event").classes("text-lg font-semibold")
                    title_input = ui.input("Title *", value=prefill_title).classes("w-full mt-2")
                    with ui.row().classes("w-full gap-3"):
                        date_input = ui.input(
                            "Date *", value=(prefill_date or date.today()).isoformat()
                        ).props("type=date").classes("flex-1")
                        time_input = ui.input("Time").props("type=time").classes("flex-1")
                    ui.label("Leave time blank for an all-day event.").classes("text-xs text-[color:var(--jg-text-dim)]")
                    description_input = ui.textarea("Description").classes("w-full mt-1")
                    error_label = ui.label("").style("color:var(--jg-red);")

                    async def submit():
                        title = title_input.value.strip() if title_input.value else ""
                        if not title:
                            error_label.text = "Title is required."
                            return
                        if not date_input.value:
                            error_label.text = "Date is required."
                            return

                        all_day = not time_input.value
                        start = date_input.value if all_day else f"{date_input.value}T{time_input.value}"

                        submit_btn.props("loading")
                        try:
                            await run.io_bound(
                                google_calendar.create_event,
                                title, start, all_day=all_day,
                                description=description_input.value or None,
                            )
                        except Exception as exc:
                            error_label.text = humanize_exception(exc)
                            submit_btn.props(remove="loading")
                            return

                        dialog.close()
                        ui.notify(f'Added "{title}" to Google Calendar.', type="positive")
                        render_calendar.refresh()

                    with ui.row().classes("w-full justify-end gap-2 mt-3"):
                        ui.button("Cancel", on_click=dialog.close).props("flat")
                        submit_btn = ui.button("Add to Calendar", on_click=submit).props("unelevated")
                dialog.open()

            def open_quick_add_dialog(day: date):
                """Click a day, type, press Enter. A time in the title
                ("Recruiter call 3pm") makes it a timed event; otherwise it's
                all-day. Escape or a click away cancels (NiceGUI dialogs do
                both by default). "More options" hands off to the full
                dialog for a description."""
                with ui.dialog() as dialog, ui.card().classes("w-[340px] max-w-full"):
                    ui.label(_long_day(day)).classes("text-xs text-[color:var(--jg-text-dim)]")
                    title_input = ui.input("Event title").classes("w-full").props("autofocus")
                    hint = ui.label("All day · add a time like “3pm” to set one").classes(
                        "text-xs text-[color:var(--jg-text-faint)] -mt-1"
                    )
                    error_label = ui.label("").style("color:var(--jg-red);")

                    def update_hint(_=None):
                        _, when = parse_quick_add(title_input.value)
                        hint.text = (
                            "All day · add a time like “3pm” to set one"
                            if when is None
                            else f"At {format_clock(when)}"
                        )

                    title_input.on_value_change(update_hint)

                    async def quick_submit():
                        title, when = parse_quick_add(title_input.value)
                        if not title:
                            dialog.close()
                            return
                        start = day.isoformat() if when is None else f"{day.isoformat()}T{when}"
                        try:
                            await run.io_bound(google_calendar.create_event, title, start, all_day=when is None)
                        except Exception as exc:
                            error_label.text = humanize_exception(exc)
                            return
                        dialog.close()
                        ui.notify(f'Added "{title}" to Google Calendar.', type="positive")
                        render_calendar.refresh()

                    title_input.on("keydown.enter", quick_submit)

                    def more_options():
                        dialog.close()
                        open_add_event_dialog(prefill_date=day, prefill_title=title_input.value or "")

                    with ui.row().classes("w-full justify-between items-center mt-1"):
                        ui.link("More options", "#").on("click.prevent", more_options).classes("text-xs")
                        ui.button("Add", on_click=quick_submit).props("unelevated size=sm")
                dialog.open()

            def open_day_dialog(day: date, day_events: list):
                with ui.dialog() as dialog, ui.card().classes("w-[360px] max-w-full"):
                    ui.label(_long_day(day)).classes("jg-panel-title")
                    with ui.column().classes("w-full gap-1 mt-2"):
                        for event in day_events:
                            _render_chip(event, dim=False)

                    def add_here():
                        dialog.close()
                        open_quick_add_dialog(day)

                    with ui.row().classes("w-full justify-between items-center mt-3"):
                        ui.button("Close", on_click=dialog.close).props("flat size=sm")
                        ui.button("+ Add event", on_click=add_here).props("unelevated size=sm")
                dialog.open()

            # -- rendering ------------------------------------------------------

            view_state = {"mode": "month", "anchor": date.today()}

            def _event_click(url: str):
                return lambda: ui.navigate.to(url, new_tab=True)

            def _render_chip(event, dim: bool) -> None:
                time_label = event_time_label(event.start)
                classes = "jg-cal-chip" + (" jg-cal-chip-dim" if dim else "")
                with ui.element("div").classes(classes).on("click.stop", _event_click(event.html_link)):
                    if time_label:
                        ui.label(time_label).classes("jg-cal-chip-time")
                    ui.label(event.summary).classes("jg-cal-chip-text").tooltip(event.summary)

            def _render_grid(days: list[date], buckets: dict[date, list], mode: str, anchor_month: int) -> None:
                today = date.today()
                month_mode = mode == "month"
                grid = ui.element("div").style(
                    "display:grid; grid-template-columns:repeat(7, minmax(0, 1fr)); width:100%;"
                )
                with grid:
                    if month_mode:
                        for wd_label in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
                            ui.label(wd_label).classes("jg-display text-xs text-[color:var(--jg-text-faint)]").style(
                                "padding:.3rem .5rem;"
                            )
                    for i, day in enumerate(days):
                        is_today = day == today
                        in_month = (day.month == anchor_month) if month_mode else True
                        is_weekend = day.weekday() >= 5
                        day_events = buckets.get(day, [])
                        cell_style = (
                            f"min-height:{112 if month_mode else 260}px; min-width:0; padding:.35rem .4rem; "
                            "cursor:pointer; border-top:1px solid var(--jg-border); "
                            + ("border-left:1px solid var(--jg-border); " if i % 7 else "")
                        )
                        if day < today and month_mode:
                            cell_style += "background:rgba(0,0,0,.12); "
                        num_color = (
                            "" if is_today else
                            "color:var(--jg-text-faint);" if not in_month else
                            "color:var(--jg-text-dim);" if is_weekend else "color:var(--jg-text);"
                        )
                        with ui.column().classes("gap-1 jg-cal-cell items-stretch").style(cell_style).on(
                            "click", lambda day=day: open_quick_add_dialog(day)
                        ):
                            with ui.row().classes("items-center gap-1 w-full no-wrap"):
                                if not month_mode:
                                    ui.label(day.strftime("%a")).classes("jg-display text-xs").style(
                                        "color:var(--jg-text-dim);"
                                    )
                                ui.label(str(day.day)).classes(
                                    "jg-cal-daynum" + (" jg-cal-daynum-today" if is_today else "")
                                ).style(num_color)
                                ui.label("+").classes("jg-cal-plus")

                            shown = day_events if not month_mode else day_events[:_MONTH_CHIP_LIMIT]
                            for event in shown:
                                _render_chip(event, dim=not in_month)
                            hidden = len(day_events) - len(shown)
                            if hidden > 0:
                                ui.label(f"+{hidden} more").classes("jg-cal-more").on(
                                    "click.stop", lambda day=day, evs=day_events: open_day_dialog(day, evs)
                                )

            @ui.refreshable
            def render_calendar():
                if not google_calendar.is_connected():
                    with ui.card().classes("w-full"):
                        ui.label("Google Calendar").classes("jg-panel-title")
                        ui.label(
                            "Not connected. Connecting lets you add events here directly, or push "
                            'one from an interview/deadline via "Add to Calendar" elsewhere in the '
                            "app, and shows what's already on your calendar. Jagir never edits or "
                            "deletes events it didn't create."
                        ).classes("text-sm text-[color:var(--jg-text-dim)] mt-2")

                        def do_connect():
                            ui.navigate.to(google_calendar.build_auth_url(), new_tab=True)

                        ui.button("Connect Google Calendar", on_click=do_connect).props("unelevated size=sm").classes("mt-3")
                    return

                mode = view_state["mode"]
                anchor = view_state["anchor"]
                days = (
                    [anchor + timedelta(days=i) for i in range(_WEEK_LENGTH)]
                    if mode == "week"
                    else month_grid_days(anchor)
                )

                with ui.card().classes("w-full q-pa-none"):
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-2").style(
                        "padding: .9rem 1rem .6rem;"
                    ):
                        ui.label(_week_title(days) if mode == "week" else anchor.strftime("%B %Y")).classes(
                            "jg-display"
                        ).style("font-size:1.15rem; font-weight:600;")

                        with ui.row().classes("items-center gap-2"):

                            def step(delta: int):
                                if view_state["mode"] == "week":
                                    view_state["anchor"] += timedelta(days=7 * delta)
                                else:
                                    a = view_state["anchor"]
                                    y, m = a.year, a.month + delta
                                    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
                                    view_state["anchor"] = date(y, m, 1)
                                render_calendar.refresh()

                            def go_today():
                                view_state["anchor"] = date.today()
                                render_calendar.refresh()

                            def set_mode(e):
                                view_state["mode"] = e.value
                                view_state["anchor"] = date.today()
                                render_calendar.refresh()

                            ui.button(icon="chevron_left", on_click=lambda: step(-1)).props("flat dense size=sm")
                            ui.button("Today", on_click=go_today).props("flat dense size=sm")
                            ui.button(icon="chevron_right", on_click=lambda: step(1)).props("flat dense size=sm")
                            ui.toggle({"month": "Month", "week": "Week"}, value=mode, on_change=set_mode).props(
                                "dense unelevated no-caps size=sm"
                            )
                            ui.button("+ Add event", on_click=lambda: open_add_event_dialog()).props(
                                "unelevated size=sm"
                            )

                    content = ui.column().classes("w-full gap-0").style("padding: 0 1rem .5rem;")
                    with content:
                        ui.label("Loading…").classes("text-sm text-[color:var(--jg-text-dim)] px-3 pb-3")

                    with ui.row().classes("w-full items-center justify-between").style(
                        "padding: .4rem 1rem .8rem; border-top:1px solid var(--jg-border);"
                    ):
                        ui.label("● Connected to Google Calendar. Click any day to add an event.").classes(
                            "text-xs"
                        ).style("color:var(--jg-text-dim);")

                        def do_disconnect():
                            google_calendar.disconnect()
                            ui.notify("Disconnected.", type="positive")
                            render_calendar.refresh()

                        ui.button("Disconnect", on_click=do_disconnect).props("flat dense size=xs no-caps").style(
                            "color:var(--jg-text-faint);"
                        )

                    async def load():
                        time_min, time_max = _range_bounds_utc(days)
                        try:
                            events = await run.io_bound(google_calendar.list_events_in_range, time_min, time_max, 250)
                        except Exception as exc:
                            content.clear()
                            with content:
                                ui.label(humanize_exception(exc)).style("color:var(--jg-red);")
                            return

                        buckets = bucket_events_by_day(events, days[0], len(days))
                        content.clear()
                        with content:
                            _render_grid(days, buckets, mode, anchor.month)

                    ui.timer(0.01, load, once=True)

            render_calendar()
