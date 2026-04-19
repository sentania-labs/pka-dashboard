from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    (tmp_path / "kb" / "work").mkdir(parents=True)
    (tmp_path / "scott" / "inbox").mkdir(parents=True)
    monkeypatch.setenv("PKA_ROOT", str(tmp_path))

    import importlib
    import app.config as config_mod
    importlib.reload(config_mod)
    from app.routes import (
        edit_comments as ec_mod,
        edit_review as er_mod,
        edit_review_response as err_mod,
        edit_todo as et_mod,
    )
    importlib.reload(et_mod)
    importlib.reload(ec_mod)
    importlib.reload(er_mod)
    importlib.reload(err_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


@pytest.fixture
def note(tmp_path: Path) -> Path:
    n = tmp_path / "kb" / "work" / "csrf-test.md"
    n.parent.mkdir(parents=True, exist_ok=True)
    n.write_text(
        "---\n"
        "title: csrf\n"
        "needs_review: true\n"
        "review_notes:\n"
        "  - First?\n"
        "review_responses: []\n"
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    return n


def test_get_root_issues_csrf_cookie(client: TestClient) -> None:
    resp = client.get("/healthz")  # JSON endpoint — no cookie
    assert "renarin_csrf" not in resp.cookies

    # HTML endpoint — today may 200 or 500 depending on briefing fixture;
    # just check a cookie is set regardless. We use /needs-attention which
    # renders without needing a briefing file.
    resp = client.get("/needs-attention")
    assert resp.status_code == 200
    assert "renarin_csrf" in resp.cookies


def test_patch_without_token_is_rejected(client: TestClient, note: Path, tmp_path: Path) -> None:
    # Explicitly drop cookies so the client carries no CSRF state.
    client.cookies.clear()
    rel = str(note.relative_to(tmp_path))
    resp = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "0",
            "response_text": "no csrf here",
            "mtime": str(note.stat().st_mtime),
        },
    )
    assert resp.status_code == 403


def test_patch_with_mismatched_token_is_rejected(
    client: TestClient, note: Path, tmp_path: Path
) -> None:
    # Prime the cookie by hitting an HTML page.
    client.get("/needs-attention")
    rel = str(note.relative_to(tmp_path))
    resp = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "0",
            "response_text": "mismatch",
            "mtime": str(note.stat().st_mtime),
        },
        headers={"X-CSRF-Token": "nonsense-wrong-value"},
    )
    assert resp.status_code == 403


def test_patch_with_valid_token_succeeds(
    client: TestClient, note: Path, tmp_path: Path
) -> None:
    # Prime the cookie, read it back, and echo in the header.
    client.get("/needs-attention")
    token = client.cookies.get("renarin_csrf")
    assert token, "cookie should be issued on first HTML GET"

    rel = str(note.relative_to(tmp_path))
    resp = client.patch(
        "/edit/review-response",
        data={
            "file_path": rel,
            "index": "0",
            "response_text": "with good token",
            "mtime": str(note.stat().st_mtime),
        },
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 200, resp.text


def test_post_reviewed_without_token_is_rejected(
    client: TestClient, note: Path, tmp_path: Path
) -> None:
    client.cookies.clear()
    rel = str(note.relative_to(tmp_path))
    resp = client.post(
        "/edit/reviewed",
        data={"file_path": rel, "mtime": str(note.stat().st_mtime)},
    )
    assert resp.status_code == 403
