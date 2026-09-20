"""Turns an internal exception into something a user can actually act on.
Used anywhere a caught exception's message would otherwise land directly in
the UI (Sync run failures, Excel import failures) — a raw Playwright/SQLite/
zipfile stack trace is not a next step, it's noise (design critique P1:
both the LLM design review and the mechanical detector independently
flagged the same raw-exception text on the Sync page).
"""

from __future__ import annotations

_PATTERNS: list[tuple[str, str]] = [
    ("net::err_aborted", "Couldn't reach the page — the browser navigation was interrupted. Try again."),
    ("net::err_connection", "Couldn't reach the page — check your internet connection and try again."),
    ("net::err_internet_disconnected", "No internet connection. Reconnect and try again."),
    ("econnrefused", "Couldn't connect — make sure you're online and try again."),
    ("timeout", "The page took too long to respond. Check your connection and try again."),
    ("target page, context or browser has been closed", "The browser window was closed before the sync finished. Try again."),
    ("executable doesn't exist", "The browser Jagir needs isn't installed yet — run `playwright install chromium` and try again."),
    ("badzipfile", "That file isn't a valid Excel workbook (.xlsx). Make sure you selected the right file."),
    ("no such file or directory", "That file couldn't be found. Try selecting it again."),
    ("permission denied", "Jagir couldn't access that file — check it isn't open in another program."),
    ("401 unauthorized", "Google Calendar access expired or was revoked — reconnect it from the Calendar page."),
    ("403 forbidden", "Google Calendar refused that request — reconnect it from the Calendar page."),
]


def humanize_exception(exc: BaseException) -> str:
    """A short, plain-language explanation with a suggested next step where
    a known cause is recognized; otherwise the exception's own first line
    (never the full traceback) so at least nothing is fabricated."""
    text = str(exc).strip()
    lowered = text.lower()
    for needle, message in _PATTERNS:
        if needle in lowered:
            return message
    first_line = text.splitlines()[0] if text else exc.__class__.__name__
    return first_line
