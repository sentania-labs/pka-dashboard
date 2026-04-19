from __future__ import annotations
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


class _CSRFClient(TestClient):
    """TestClient that primes + echoes the CSRF cookie on mutating calls."""

    def request(self, method, url, **kwargs):
        method_upper = method.upper()
        if method_upper in ("POST", "PUT", "PATCH", "DELETE"):
            token = self.cookies.get("renarin_csrf")
            if not token:
                # Prime by hitting an HTML page.
                super().request("GET", "/needs-attention")
                token = self.cookies.get("renarin_csrf")
            if token:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", token)
                kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point PKA_ROOT at tmp_path, set up kb/work/ so the route allows the file
    kb_work = tmp_path / "kb" / "work"
    kb_work.mkdir(parents=True)
    (tmp_path / "scott" / "inbox").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PKA_ROOT", str(tmp_path))
    # Re-import settings after env change. Route modules cache `settings`
    # at import time, so reload them too — otherwise subsequent tests see
    # the first test's PKA_ROOT.
    import importlib
    import app.config as config_mod
    importlib.reload(config_mod)
    from app.routes import edit_review_response as err_mod
    from app.routes import edit_review as er_mod
    importlib.reload(err_mod)
    importlib.reload(er_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    return _CSRFClient(main_mod.app)

@pytest.fixture
def corrupt_note(tmp_path):
    note = tmp_path / "kb" / "work" / "corrupt.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\nreviewed: false\nreviewed: true\ntitle: test\nneeds_review: true\n---\nBody\n",
        encoding="utf-8",
    )
    return note

@pytest.fixture
def multi_note(tmp_path):
    note = tmp_path / "kb" / "work" / "multi.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "title: test\n"
        "needs_review: true\n"
        "review_notes:\n"
        "  - First question?\n"
        "  - Second question?\n"
        "review_responses: []\n"
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    return note


def test_responsesaved_trigger_is_json_payload(client, multi_note, tmp_path):
    mtime = multi_note.stat().st_mtime
    rel = str(multi_note.relative_to(tmp_path))
    resp = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "0",
            "response_text": "first answer",
            "mtime": str(mtime),
        },
    )
    assert resp.status_code == 200
    trigger = resp.headers.get("HX-Trigger")
    assert trigger is not None
    payload = json.loads(trigger)
    assert "responsesaved" in payload
    assert payload["responsesaved"]["file"] == rel
    assert isinstance(payload["responsesaved"]["mtime"], (int, float))


def test_allreviewed_trigger_is_json_payload(client, multi_note, tmp_path):
    # Answer the first, then the second — second response completes all notes.
    rel = str(multi_note.relative_to(tmp_path))
    first = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "0",
            "response_text": "first",
            "mtime": str(multi_note.stat().st_mtime),
        },
    )
    assert first.status_code == 200
    new_mtime = multi_note.stat().st_mtime
    resp = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "1",
            "response_text": "second",
            "mtime": str(new_mtime),
        },
    )
    assert resp.status_code == 200
    payload = json.loads(resp.headers["HX-Trigger"])
    assert "allreviewed" in payload
    assert payload["allreviewed"]["file"] == rel
    assert isinstance(payload["allreviewed"]["mtime"], (int, float))


def test_corrupt_frontmatter_toast(client, corrupt_note, tmp_path):
    mtime = corrupt_note.stat().st_mtime
    rel = str(corrupt_note.relative_to(tmp_path))
    resp = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "0",
            "response_text": "my response",
            "mtime": str(mtime),
        },
    )
    assert resp.status_code == 409
    assert "frontmatter is corrupt" in resp.text
