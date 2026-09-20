"""No real network calls — every httpx call is monkeypatched. Covers the
OAuth token lifecycle (save/load/refresh), event-body construction (the
part most likely to have a timezone/date-math bug), and the CSRF state
handshake."""

import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.config import settings
from app.integrations import google_calendar as gc


@pytest.fixture(autouse=True)
def _isolated_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "google_token_path", str(tmp_path / "google_token.json"))
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")
    gc._pending_state = None
    yield


def _fake_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://example.com")
    return httpx.Response(status_code, json=json_data, request=request)


def test_build_auth_url_includes_required_params():
    url = gc.build_auth_url()
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert params["client_id"] == ["test-client-id"]
    assert params["redirect_uri"] == [settings.google_oauth_redirect_uri]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert "state" in params


def test_consume_pending_state_matches_then_clears():
    url = gc.build_auth_url()
    state = parse_qs(urlparse(url).query)["state"][0]

    assert gc.consume_pending_state(state) is True
    assert gc.consume_pending_state(state) is False  # one-time use


def test_consume_pending_state_rejects_wrong_value():
    gc.build_auth_url()
    assert gc.consume_pending_state("not-the-real-state") is False


def test_is_connected_false_before_any_token_saved():
    assert gc.is_connected() is False


def test_exchange_code_for_tokens_saves_refresh_token(monkeypatch):
    def fake_post(url, data=None, timeout=None, **kwargs):
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "the-code"
        return _fake_response({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})

    monkeypatch.setattr(gc.httpx, "post", fake_post)
    gc.exchange_code_for_tokens("the-code")

    assert gc.is_connected() is True
    token = gc._load_token()
    assert token["access_token"] == "at-1"
    assert token["refresh_token"] == "rt-1"


def test_disconnect_removes_token_and_attempts_revoke(monkeypatch):
    gc._save_token({"access_token": "at", "refresh_token": "rt", "expires_at": time.time() + 3600})
    revoked = {}

    def fake_post(url, params=None, timeout=None, **kwargs):
        revoked["token"] = params["token"]
        return _fake_response({})

    monkeypatch.setattr(gc.httpx, "post", fake_post)
    gc.disconnect()

    assert gc.is_connected() is False
    assert revoked["token"] == "rt"


def test_disconnect_still_clears_local_token_if_revoke_fails(monkeypatch):
    gc._save_token({"access_token": "at", "refresh_token": "rt", "expires_at": time.time() + 3600})

    def fake_post(*a, **k):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", "https://example.com"))

    monkeypatch.setattr(gc.httpx, "post", fake_post)
    gc.disconnect()  # must not raise

    assert gc.is_connected() is False


def test_get_valid_access_token_reuses_unexpired_token(monkeypatch):
    gc._save_token({"access_token": "still-good", "refresh_token": "rt", "expires_at": time.time() + 3600})

    def fail_if_called(*a, **k):
        raise AssertionError("should not have refreshed a still-valid token")

    monkeypatch.setattr(gc.httpx, "post", fail_if_called)
    assert gc._get_valid_access_token() == "still-good"


def test_get_valid_access_token_refreshes_when_expired(monkeypatch):
    gc._save_token({"access_token": "stale", "refresh_token": "rt-keep", "expires_at": time.time() - 10})

    def fake_post(url, data=None, timeout=None, **kwargs):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "rt-keep"
        return _fake_response({"access_token": "fresh", "expires_in": 3600})

    monkeypatch.setattr(gc.httpx, "post", fake_post)
    assert gc._get_valid_access_token() == "fresh"
    # the refresh grant doesn't reissue a refresh_token — the old one must survive
    assert gc._load_token()["refresh_token"] == "rt-keep"


def test_get_valid_access_token_raises_clear_error_when_never_connected():
    with pytest.raises(gc.GoogleCalendarNotConnected):
        gc._get_valid_access_token()


def test_create_event_all_day_uses_exclusive_end_date(monkeypatch):
    gc._save_token({"access_token": "at", "refresh_token": "rt", "expires_at": time.time() + 3600})
    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return _fake_response({"id": "evt1", "summary": json["summary"], "htmlLink": "https://cal/evt1"})

    monkeypatch.setattr(gc.httpx, "request", fake_request)
    event = gc.create_event("Deadline — Acme", "2026-09-25", all_day=True)

    assert captured["json"]["start"] == {"date": "2026-09-25"}
    assert captured["json"]["end"] == {"date": "2026-09-26"}
    assert event.id == "evt1"


def test_create_event_timed_defaults_to_one_hour(monkeypatch):
    gc._save_token({"access_token": "at", "refresh_token": "rt", "expires_at": time.time() + 3600})
    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None, **kwargs):
        captured["json"] = json
        return _fake_response({"id": "evt2", "summary": json["summary"], "htmlLink": "https://cal/evt2"})

    monkeypatch.setattr(gc.httpx, "request", fake_request)
    gc.create_event("Interview 1 — Acme", "2026-09-20T14:00", description="via Jagir")

    start = captured["json"]["start"]["dateTime"]
    end = captured["json"]["end"]["dateTime"]
    assert start.startswith("2026-09-20T14:00:00")
    assert end.startswith("2026-09-20T15:00:00")
    assert captured["json"]["description"] == "via Jagir"


def test_list_upcoming_events_parses_timed_and_all_day_items(monkeypatch):
    gc._save_token({"access_token": "at", "refresh_token": "rt", "expires_at": time.time() + 3600})

    def fake_request(method, url, headers=None, params=None, timeout=None, **kwargs):
        return _fake_response(
            {
                "items": [
                    {"id": "1", "summary": "Interview", "start": {"dateTime": "2026-09-20T14:00:00+05:45"}, "htmlLink": "https://cal/1"},
                    {"id": "2", "summary": "Deadline", "start": {"date": "2026-09-25"}, "htmlLink": "https://cal/2"},
                ]
            }
        )

    monkeypatch.setattr(gc.httpx, "request", fake_request)
    events = gc.list_upcoming_events()

    assert [e.start for e in events] == ["2026-09-20T14:00:00+05:45", "2026-09-25"]


def test_list_events_in_range_passes_explicit_bounds(monkeypatch):
    gc._save_token({"access_token": "at", "refresh_token": "rt", "expires_at": time.time() + 3600})
    captured = {}

    def fake_request(method, url, headers=None, params=None, timeout=None, **kwargs):
        captured["params"] = params
        return _fake_response({"items": [{"id": "1", "summary": "Mid-month thing", "start": {"date": "2026-09-10"}, "htmlLink": "https://cal/1"}]})

    monkeypatch.setattr(gc.httpx, "request", fake_request)
    events = gc.list_events_in_range("2026-09-01T00:00:00+00:00", "2026-10-01T00:00:00+00:00")

    assert captured["params"]["timeMin"] == "2026-09-01T00:00:00+00:00"
    assert captured["params"]["timeMax"] == "2026-10-01T00:00:00+00:00"
    assert [e.id for e in events] == ["1"]


def test_401_from_api_surfaces_as_http_status_error(monkeypatch):
    gc._save_token({"access_token": "expired", "refresh_token": "rt", "expires_at": time.time() + 3600})

    def fake_request(method, url, headers=None, **kwargs):
        request = httpx.Request(method, url)
        return httpx.Response(401, json={"error": "unauthorized"}, request=request)

    monkeypatch.setattr(gc.httpx, "request", fake_request)
    with pytest.raises(httpx.HTTPStatusError):
        gc.list_upcoming_events()
