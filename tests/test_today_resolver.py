from __future__ import annotations

import datetime as dt
import importlib
from pathlib import Path

import pytest


BRIEFING_TEMPLATE = """\
---
date: {date}
type: daily-briefing
---

# Daily Briefing for {date}

Content for the {date} briefing.
"""


def _write_briefing(directory: Path, date: dt.date) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date.isoformat()}-daily-briefing.md"
    path.write_text(BRIEFING_TEMPLATE.format(date=date.isoformat()), encoding="utf-8")
    return path


@pytest.fixture
def today_env(tmp_path, monkeypatch):
    (tmp_path / "scott" / "inbox").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scott" / "inbox" / "briefing-archive").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PKA_ROOT", str(tmp_path))
    import app.config as config_mod
    importlib.reload(config_mod)
    from app.services import notes as notes_mod
    importlib.reload(notes_mod)
    from app.routes import today as today_mod
    importlib.reload(today_mod)
    return {
        "root": tmp_path,
        "inbox": tmp_path / "scott" / "inbox",
        "archive": tmp_path / "scott" / "inbox" / "briefing-archive",
        "notes": notes_mod,
        "today_route": today_mod,
    }


def test_today_exists(today_env):
    today = dt.datetime.now().date()
    _write_briefing(today_env["inbox"], today)

    ctx = today_env["today_route"]._today_context()

    assert ctx["today_date"] == today
    assert ctx["body_html"] is not None
    assert "Daily Briefing" in ctx["body_html"]
    assert ctx["fallback_banner"] is False
    assert ctx["fallback_date"] is None
    assert ctx["briefing_filename"] == f"{today.isoformat()}-daily-briefing.md"


def test_fallback_from_inbox(today_env):
    today = dt.datetime.now().date()
    yesterday = today - dt.timedelta(days=1)
    _write_briefing(today_env["inbox"], yesterday)

    recent = today_env["notes"].find_most_recent_briefing()
    assert recent is not None
    assert recent[0] == yesterday
    assert recent[1] == f"{yesterday.isoformat()}-daily-briefing.md"
    assert recent[2] == "inbox"

    ctx = today_env["today_route"]._today_context()
    assert ctx["today_date"] == today
    assert ctx["fallback_banner"] is True
    assert ctx["fallback_date"] == yesterday
    assert ctx["body_html"] is not None
    assert yesterday.isoformat() in ctx["body_html"]


def test_fallback_from_archive(today_env):
    today = dt.datetime.now().date()
    yesterday = today - dt.timedelta(days=1)
    _write_briefing(today_env["archive"], yesterday)

    recent = today_env["notes"].find_most_recent_briefing()
    assert recent is not None
    assert recent[0] == yesterday
    assert recent[2] == "archive"

    ctx = today_env["today_route"]._today_context()
    assert ctx["fallback_banner"] is True
    assert ctx["fallback_date"] == yesterday
    assert ctx["body_html"] is not None
    assert yesterday.isoformat() in ctx["body_html"]


def test_picks_newest_across_both(today_env):
    today = dt.datetime.now().date()
    yesterday = today - dt.timedelta(days=1)
    two_days_ago = today - dt.timedelta(days=2)
    _write_briefing(today_env["inbox"], two_days_ago)
    _write_briefing(today_env["archive"], yesterday)

    recent = today_env["notes"].find_most_recent_briefing()
    assert recent is not None
    assert recent[0] == yesterday
    assert recent[2] == "archive"

    ctx = today_env["today_route"]._today_context()
    assert ctx["fallback_date"] == yesterday
    assert ctx["fallback_banner"] is True


def test_no_briefing(today_env):
    recent = today_env["notes"].find_most_recent_briefing()
    assert recent is None

    ctx = today_env["today_route"]._today_context()
    assert ctx["body_html"] is None
    assert ctx["last_briefing"] is None
    assert ctx["fallback_banner"] is False
    assert ctx["fallback_date"] is None
