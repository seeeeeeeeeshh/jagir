"""Exercises the actual HTTP route the bookmarklet posts to, via FastAPI's
TestClient — confirms the form-POST contract (field name, response shape)
independent of app/sync/bookmarklet_capture.py's own unit tests."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nicegui import app as nicegui_app

from app.api import linkedin_capture

linkedin_capture.register()
client = TestClient(nicegui_app)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "app" / "db" / "schema.sql"


@pytest.fixture
def http_conn():
    # TestClient dispatches the ASGI app through its own worker thread, so
    # this needs check_same_thread=False — same as the real app's shared
    # connection (app/db/database.py), which already sets this for exactly
    # this reason. The plain `conn` fixture doesn't, since ordinary
    # (non-HTTP-layer) tests call repos directly on the main test thread.
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    yield connection
    connection.close()


def test_capture_endpoint_creates_opportunity(http_conn, monkeypatch):
    monkeypatch.setattr(linkedin_capture, "get_connection", lambda: http_conn)

    payload = [
        {
            "title": "Software Engineer Intern",
            "company_name": "Acme Inc.",
            "location": "Remote",
            "linkedin_url": "https://www.linkedin.com/jobs/view/4123456789/",
            "linkedin_job_id": "4123456789",
            "list_type": "saved",
        }
    ]

    response = client.post("/sync/capture", data={"payload": json.dumps(payload)})

    assert response.status_code == 200
    assert "SUCCESS" in response.text.upper()
    assert "1 new saved" in response.text

    from app.db.repositories.opportunities_repo import OpportunitiesRepo

    opps = OpportunitiesRepo(http_conn).list_all()
    assert len(opps) == 1
    assert opps[0].title == "Software Engineer Intern"


def test_capture_endpoint_rejects_malformed_payload(http_conn, monkeypatch):
    monkeypatch.setattr(linkedin_capture, "get_connection", lambda: http_conn)

    response = client.post("/sync/capture", data={"payload": "not valid json"})

    assert response.status_code == 400
    assert "Malformed" in response.text


def test_capture_endpoint_handles_missing_payload_field(http_conn, monkeypatch):
    monkeypatch.setattr(linkedin_capture, "get_connection", lambda: http_conn)

    response = client.post("/sync/capture", data={})

    assert response.status_code == 200  # defaults to "[]" -> empty, valid capture of nothing
    assert "SUCCESS" in response.text.upper()
