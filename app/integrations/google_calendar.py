"""One-way Google Calendar integration: push interviews/deadlines from
Jagir as events (manual, per-item — never automatic), and read the user's
own upcoming events for visibility on the Calendar page. No two-way sync,
no writes outside events Jagir itself created.

Auth is the standard OAuth2 "web application" flow, using Jagir's own
local server as the redirect target (app/api/google_oauth.py) rather than
a separate loopback listener. The refresh token is stored in its own file
(settings.google_token_abs_path) — see the comment in app/config.py for
why that's not in the sqlite db.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_API_BASE = "https://www.googleapis.com/calendar/v3"

# calendar.events (create) + calendar.readonly (list) — deliberately not
# the broad "calendar" scope, which also allows deleting/renaming calendars.
_SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly"

# Set by build_auth_url, checked by the callback route — cheap CSRF guard;
# not load-bearing security for a single-user local app, but free to add.
_pending_state: str | None = None


class GoogleCalendarNotConnected(Exception):
    pass


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start: str  # RFC3339 datetime or plain date, whichever the event uses
    html_link: str


def build_auth_url() -> str:
    global _pending_state
    _pending_state = secrets.token_urlsafe(16)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",  # forces a fresh refresh_token every reconnect
        "state": _pending_state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def consume_pending_state(state: str | None) -> bool:
    global _pending_state
    matched = state is not None and state == _pending_state
    _pending_state = None
    return matched


def exchange_code_for_tokens(code: str) -> None:
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _save_token(
        {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + data.get("expires_in", 3600),
        }
    )


def is_connected() -> bool:
    token = _load_token()
    return token is not None and bool(token.get("refresh_token"))


def disconnect() -> None:
    token = _load_token()
    if token and token.get("refresh_token"):
        try:
            httpx.post(_REVOKE_URL, params={"token": token["refresh_token"]}, timeout=10)
        except httpx.HTTPError:
            pass  # best-effort revoke; still forget the local copy below
    path = settings.google_token_abs_path
    if path.exists():
        path.unlink()


def list_upcoming_events(max_results: int = 10) -> list[CalendarEvent]:
    now = datetime.now(timezone.utc).isoformat()
    resp = _authed_request(
        "GET",
        f"{_API_BASE}/calendars/primary/events",
        params={"timeMin": now, "singleEvents": "true", "orderBy": "startTime", "maxResults": max_results},
    )
    return _parse_events(resp)


def list_events_in_range(time_min_iso: str, time_max_iso: str, max_results: int = 250) -> list[CalendarEvent]:
    """Unlike list_upcoming_events (always forward from now), this fetches
    a fixed window — needed for a month view, since the part of a month
    before today is in the past and list_upcoming_events would never
    return it."""
    resp = _authed_request(
        "GET",
        f"{_API_BASE}/calendars/primary/events",
        params={
            "timeMin": time_min_iso,
            "timeMax": time_max_iso,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": max_results,
        },
    )
    return _parse_events(resp)


def _parse_events(resp: httpx.Response) -> list[CalendarEvent]:
    events = []
    for item in resp.json().get("items", []):
        start = item.get("start", {})
        events.append(
            CalendarEvent(
                id=item.get("id", ""),
                summary=item.get("summary") or "(no title)",
                start=start.get("dateTime") or start.get("date") or "",
                html_link=item.get("htmlLink", ""),
            )
        )
    return events


def create_event(
    summary: str,
    start: str,
    *,
    all_day: bool = False,
    description: str | None = None,
    location: str | None = None,
) -> CalendarEvent:
    """`start` is a `datetime-local` input value ("2026-09-20T14:00") for a
    timed event, or a plain date ("2026-09-20") when all_day=True. Timed
    events default to 1 hour and are interpreted in the machine's own local
    timezone (the same one the browser's datetime picker showed)."""
    if all_day:
        start_date = date.fromisoformat(start)
        body = {
            "summary": summary,
            "start": {"date": start_date.isoformat()},
            "end": {"date": (start_date + timedelta(days=1)).isoformat()},
        }
    else:
        # A naive datetime's .astimezone() with no args treats it as
        # already being in the system's local time and attaches that
        # offset — exactly what a <input type=datetime-local> value means.
        start_dt = datetime.fromisoformat(start).astimezone()
        end_dt = start_dt + timedelta(hours=1)
        body = {
            "summary": summary,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
    if description:
        body["description"] = description
    if location:
        body["location"] = location

    resp = _authed_request("POST", f"{_API_BASE}/calendars/primary/events", json=body)
    data = resp.json()
    return CalendarEvent(id=data["id"], summary=data.get("summary", summary), start=start, html_link=data.get("htmlLink", ""))


def _authed_request(method: str, url: str, **kwargs) -> httpx.Response:
    token = _get_valid_access_token()
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    resp = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
    resp.raise_for_status()
    return resp


def _get_valid_access_token() -> str:
    token = _load_token()
    if token is None:
        raise GoogleCalendarNotConnected("Google Calendar isn't connected yet — connect it from the Calendar page.")
    if time.time() > token.get("expires_at", 0) - 60:
        token = _refresh_access_token(token["refresh_token"])
    return token["access_token"]


def _refresh_access_token(refresh_token: str) -> dict:
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    token = {
        "access_token": data["access_token"],
        "refresh_token": refresh_token,  # not reissued on a refresh grant
        "expires_at": time.time() + data.get("expires_in", 3600),
    }
    _save_token(token)
    return token


def _load_token() -> dict | None:
    path = settings.google_token_abs_path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_token(token: dict) -> None:
    path = settings.google_token_abs_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2), encoding="utf-8")
