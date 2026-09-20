"""Raw HTTP endpoint the LinkedIn bookmarklet posts to (see
app/ui/pages/sync_page.py for where the bookmarklet itself is generated,
app/sync/bookmarklet_capture.py for what happens to the payload).

This is a plain form POST, not a NiceGUI page or a fetch()/CORS call — the
bookmarklet builds a hidden <form method="post"> in the LinkedIn tab and
submits it, which browsers allow cross-origin as an ordinary navigation.
That sidesteps CORS entirely and means the response (this confirmation
page) is what the user actually sees, in a new tab, right after capturing.
"""

from __future__ import annotations

import json
import logging

from fastapi import Request
from fastapi.responses import HTMLResponse
from nicegui import app

from app.sync.bookmarklet_capture import capture_jobs
from app.ui import theme
from app.ui.state import get_connection

logger = logging.getLogger(__name__)


def _confirmation_html(status: str, summary: str) -> str:
    accent = {"success": theme.ACCENT_GREEN, "partial": theme.ACCENT_AMBER}.get(status, theme.ACCENT_RED)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Jagir — Capture</title>
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
    @app.post("/sync/capture")
    async def linkedin_capture(request: Request):
        form = await request.form()
        raw_payload = form.get("payload", "[]")
        try:
            items = json.loads(raw_payload)
            if not isinstance(items, list):
                raise ValueError("payload must be a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Malformed bookmarklet payload: %s", exc)
            return HTMLResponse(_confirmation_html("failed", f"Malformed capture payload: {exc}"), status_code=400)

        run = capture_jobs(get_connection(), items)
        return HTMLResponse(_confirmation_html(run.status, run.summary_text or run.status))
