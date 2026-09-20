"""Receives Google's OAuth2 redirect after the user grants (or denies)
calendar access. See app/integrations/google_calendar.py for the token
exchange itself and app/ui/pages/calendar_page.py for where the flow
starts.
"""

from __future__ import annotations

import logging

from fastapi.responses import HTMLResponse
from nicegui import app

from app.core.errors import humanize_exception
from app.integrations import google_calendar
from app.ui import theme

logger = logging.getLogger(__name__)


def _result_html(status: str, summary: str) -> str:
    accent = theme.ACCENT_GREEN if status == "success" else theme.ACCENT_RED
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Jagir — Google Calendar</title>
<style>
  body {{ background: {theme.BG}; color: {theme.TEXT}; font-family: ui-sans-serif, system-ui, sans-serif;
          display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .card {{ background: {theme.PANEL}; border: 1px solid {theme.BORDER}; border-radius: 6px;
           padding: 2rem; max-width: 420px; text-align: center; }}
  .status {{ color: {accent}; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; font-size: .8rem; }}
  .summary {{ margin-top: .75rem; color: {theme.TEXT_DIM}; font-size: .95rem; }}
  .hint {{ margin-top: 1.5rem; font-size: .8rem; color: {theme.TEXT_DIM}; }}
</style></head>
<body>
  <div class="card">
    <div class="status">{status}</div>
    <div class="summary">{summary}</div>
    <div class="hint">You can close this tab and go back to Jagir.</div>
  </div>
</body></html>"""


def register():
    @app.get("/oauth/google/callback")
    async def google_oauth_callback(code: str | None = None, error: str | None = None, state: str | None = None):
        if error:
            return HTMLResponse(_result_html("failed", f"Google didn't grant access: {error}"))

        if not google_calendar.consume_pending_state(state):
            return HTMLResponse(
                _result_html("failed", "This link expired or was already used — start over from the Calendar page."),
                status_code=400,
            )

        if not code:
            return HTMLResponse(_result_html("failed", "No authorization code received."), status_code=400)

        try:
            google_calendar.exchange_code_for_tokens(code)
        except Exception as exc:
            logger.exception("Google OAuth token exchange failed")
            return HTMLResponse(_result_html("failed", humanize_exception(exc)))

        return HTMLResponse(_result_html("success", "Google Calendar connected."))
