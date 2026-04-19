from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.file_writer import (
    auto_commit,
    edit_frontmatter_field,
    read_with_mtime,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )


def _has_git() -> bool:
    return shutil.which("git") is not None


pytestmark = pytest.mark.skipif(not _has_git(), reason="git not available")


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "commit", "--allow-empty", "-m", "init")
    return repo


def _head_subject(repo: Path) -> str:
    out = _git(repo, "log", "-1", "--pretty=%s")
    return out.stdout.strip()


def _head_files(repo: Path) -> list[str]:
    out = _git(repo, "show", "--name-only", "--pretty=", "HEAD")
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


def test_auto_commit_creates_commit_after_frontmatter_edit(tmp_repo: Path) -> None:
    note = tmp_repo / "kb" / "work" / "sample.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\nreviewed: false\nneeds_review: true\n---\nBody text\n",
        encoding="utf-8",
    )
    _git(tmp_repo, "add", "kb/work/sample.md")
    _git(tmp_repo, "commit", "-m", "add sample")
    start_subject = _head_subject(tmp_repo)

    _, mtime = read_with_mtime(note)
    edit_frontmatter_field(note, "reviewed", True, mtime)

    new_subject = _head_subject(tmp_repo)
    assert new_subject != start_subject, "expected a new commit to land after edit"
    assert new_subject.startswith("renarin:"), f"subject={new_subject!r}"
    assert "kb/work/sample.md" in new_subject
    assert "kb/work/sample.md" in _head_files(tmp_repo)


def test_auto_commit_no_op_when_not_in_repo(tmp_path: Path, caplog) -> None:
    # File is outside any git repo. auto_commit must not raise.
    note = tmp_path / "loose.md"
    note.write_text("hello\n", encoding="utf-8")
    auto_commit(note, "test-op")
    # Nothing to assert except that we got here without raising.


def test_auto_commit_handles_clean_tree(tmp_repo: Path) -> None:
    # Second call against an already-committed file should not raise.
    note = tmp_repo / "file.md"
    note.write_text("content\n", encoding="utf-8")
    _git(tmp_repo, "add", "file.md")
    _git(tmp_repo, "commit", "-m", "add")

    # Call auto_commit without making any change — should log & move on.
    auto_commit(note, "noop")
