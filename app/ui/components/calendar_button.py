"""A small, self-contained "Add to Calendar" button used on interview rows
and on the deadline / next-action fields of the opportunity detail page.
Each one is an independent, explicit push — see app/integrations/google_calendar.py
for why this is manual-only, not an automatic sync."""

from __future__ import annotations

from typing import Callable

from nicegui import run, ui

from app.core.errors import humanize_exception
from app.integrations import google_calendar


def add_to_calendar_button(
    summary: str | Callable[[], str],
    start: str | Callable[[], str | None],
    *,
    all_day: bool = False,
    description: str | None = None,
    location: str | None = None,
):
    """`summary`/`start` are either fixed values or callables read at click
    time (for fields the user might still be editing when the button
    renders, e.g. the free-text "next action" description)."""

    async def on_click():
        actual_summary = summary() if callable(summary) else summary
        actual_start = start() if callable(start) else start
        if not actual_start:
            ui.notify("Nothing to schedule yet — set a date first.", type="warning")
            return
        if not google_calendar.is_connected():
            ui.notify("Connect Google Calendar first (see the Calendar page).", type="warning")
            return

        btn.props("loading")
        try:
            event = await run.io_bound(
                google_calendar.create_event,
                actual_summary,
                actual_start,
                all_day=all_day,
                description=description,
                location=location,
            )
            ui.notify(f'Added "{event.summary}" to Google Calendar.', type="positive")
        except Exception as exc:
            ui.notify(humanize_exception(exc), type="negative")
        finally:
            try:
                btn.props(remove="loading")
            except RuntimeError:
                pass  # the user navigated away mid-request — nothing to update

    btn = ui.button("Add to Calendar", icon="event", on_click=on_click).props("flat dense size=sm")
    return btn
