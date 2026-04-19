from __future__ import annotations

import hashlib
import time
from pathlib import Path

import frontmatter
import pytest

from app.services.file_writer import (
    MtimeConflictError,
    edit_comment_block,
    edit_frontmatter_field,
    edit_line,
    edit_review_response,
    read_with_mtime,
)


EXPECTED_KEYS = {
    "date",
    "type",
    "category",
    "source",
    "source_artifact",
    "status",
    "needs_review",
    "review_notes",
    "attendees",
    "customer",
    "topics",
    "tags",
    "commitments",
    "decisions",
}


def test_roundtrip_frontmatter_reviewed_toggle(tmp_note: Path) -> None:
    orig_text, mtime = read_with_mtime(tmp_note)
    orig_post = frontmatter.load(tmp_note)
    orig_body = orig_post.content
    new_value = not (orig_post.metadata.get("reviewed") is True)

    edit_frontmatter_field(tmp_note, "reviewed", new_value, mtime)

    post = frontmatter.load(tmp_note)
    assert post.metadata["reviewed"] is new_value
    for key in EXPECTED_KEYS:
        assert key in post.metadata, f"missing key after roundtrip: {key}"
    assert post.content == orig_body

    new_text = tmp_note.read_text(encoding="utf-8")
    orig_lines = orig_text.splitlines()
    new_lines = new_text.splitlines()
    assert len(new_lines) == len(orig_lines), (
        f"line count changed: {len(orig_lines)} -> {len(new_lines)}"
    )
    diffs = [
        (i, a, b)
        for i, (a, b) in enumerate(zip(orig_lines, new_lines))
        if a != b
    ]
    assert len(diffs) == 1, f"expected exactly one changed line, got {len(diffs)}: {diffs}"
    assert "reviewed:" in diffs[0][2].lower()


def test_roundtrip_preserves_key_order(tmp_note: Path) -> None:
    orig_post = frontmatter.load(tmp_note)
    new_value = not (orig_post.metadata.get("reviewed") is True)
    _, mtime = read_with_mtime(tmp_note)
    edit_frontmatter_field(tmp_note, "reviewed", new_value, mtime)

    post = frontmatter.load(tmp_note)
    assert post.metadata["reviewed"] is new_value

    new_text = tmp_note.read_text(encoding="utf-8")
    lines = new_text.splitlines()

    date_idx = next(i for i, ln in enumerate(lines) if ln.startswith("date:"))
    type_idx = next(i for i, ln in enumerate(lines) if ln.startswith("type:"))
    assert date_idx < type_idx, (
        f"expected date: before type:, got date@{date_idx} type@{type_idx}"
    )

    review_notes_line = next(
        ln for ln in lines if ln.startswith("review_notes:")
    )
    assert "review_notes" in review_notes_line
    assert not review_notes_line.rstrip().endswith("["), (
        f"review_notes became inline: {review_notes_line!r}"
    )


def test_mtime_conflict_raises(tmp_note: Path) -> None:
    _, orig_mtime = read_with_mtime(tmp_note)
    time.sleep(0.05)
    tmp_note.touch()
    with pytest.raises(MtimeConflictError):
        edit_frontmatter_field(tmp_note, "reviewed", True, orig_mtime)


def test_line_edit_preserves_line_count(tmp_note: Path) -> None:
    text, mtime = read_with_mtime(tmp_note)
    lines = text.splitlines()
    orig_count = len(lines)

    line_idx = 0
    assert lines[line_idx] == "---"
    h = hashlib.sha256(lines[line_idx].encode()).hexdigest()[:8]

    edit_line(tmp_note, line_idx, h, "---", mtime)

    new_text, _ = read_with_mtime(tmp_note)
    new_lines = new_text.splitlines()
    assert len(new_lines) == orig_count
    assert new_lines[line_idx] == "---"


def test_review_response_write_preserves_fields(tmp_note: Path) -> None:
    orig_text, mtime = read_with_mtime(tmp_note)
    orig_post = frontmatter.load(tmp_note)
    orig_body = orig_post.content
    orig_line_count = len(orig_text.splitlines())

    edit_review_response(tmp_note, 0, "The customer is Acme Corp.", mtime)
    _, mtime2 = read_with_mtime(tmp_note)
    edit_review_response(tmp_note, 1, "Speaker 1 is the PM lead.", mtime2)

    post = frontmatter.load(tmp_note)
    responses = post.metadata["review_responses"]
    assert responses[0] == "The customer is Acme Corp."
    assert responses[1] == "Speaker 1 is the PM lead."

    for key in EXPECTED_KEYS:
        assert key in post.metadata, f"missing key after roundtrip: {key}"

    assert post.content == orig_body

    new_text = tmp_note.read_text(encoding="utf-8")
    new_line_count = len(new_text.splitlines())
    assert new_line_count - orig_line_count <= 3, (
        f"line count grew by more than 3: {orig_line_count} -> {new_line_count}"
    )


def test_edit_review_response_auto_marks_reviewed_when_complete(
    tmp_path: Path,
) -> None:
    path = tmp_path / "note.md"
    path.write_text(
        "---\n"
        "review_notes:\n"
        "  - Question one\n"
        "  - Question two\n"
        "reviewed: false\n"
        "---\n"
        "Body text.\n",
        encoding="utf-8",
    )
    _, mtime = read_with_mtime(path)

    result = edit_review_response(path, 0, "Answer one.", mtime)
    assert result.marked_reviewed is False

    result2 = edit_review_response(path, 1, "Answer two.", result.new_mtime)
    assert result2.marked_reviewed is True

    post = frontmatter.load(path)
    assert post.metadata["reviewed"] is True


def test_edit_review_response_does_not_mark_reviewed_if_incomplete(
    tmp_path: Path,
) -> None:
    path = tmp_path / "note.md"
    path.write_text(
        "---\n"
        "review_notes:\n"
        "  - Question one\n"
        "  - Question two\n"
        "reviewed: false\n"
        "---\n"
        "Body text.\n",
        encoding="utf-8",
    )
    _, mtime = read_with_mtime(path)

    result = edit_review_response(path, 0, "Answer one.", mtime)
    assert result.marked_reviewed is False

    post = frontmatter.load(path)
    assert post.metadata.get("reviewed") != True


def test_edit_review_response_empty_string_does_not_mark_reviewed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "note.md"
    path.write_text(
        "---\n"
        "review_notes:\n"
        "  - Question one\n"
        "  - Question two\n"
        "reviewed: false\n"
        "---\n"
        "Body text.\n",
        encoding="utf-8",
    )
    _, mtime = read_with_mtime(path)

    result = edit_review_response(path, 0, "", mtime)
    assert result.marked_reviewed is False

    result2 = edit_review_response(path, 1, "Answer two.", result.new_mtime)
    assert result2.marked_reviewed is False

    result3 = edit_review_response(path, 0, "filled", result2.new_mtime)
    assert result3.marked_reviewed is True


def test_comment_block_edit_preserves_surroundings(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(
        "header line A\n"
        "header line B\n"
        "> **Scott's comments:**\n"
        "> old line one\n"
        "> old line two\n"
        "footer line A\n"
        "footer line B\n",
        encoding="utf-8",
    )
    _, mtime = read_with_mtime(path)

    new_content = "> **Scott's comments:**\n> replaced line"
    edit_comment_block(path, 2, 5, new_content, mtime)

    result_lines = path.read_text(encoding="utf-8").splitlines()
    assert result_lines[0] == "header line A"
    assert result_lines[1] == "header line B"
    assert result_lines[-2] == "footer line A"
    assert result_lines[-1] == "footer line B"
    assert "> **Scott's comments:**" in result_lines
    assert "> replaced line" in result_lines


def test_edit_review_response_corrupt_frontmatter(tmp_path):
    """FrontmatterCorruptError is raised when note has duplicate YAML keys."""
    # Write a tmp file with duplicate 'reviewed' keys in frontmatter
    note = tmp_path / "corrupt.md"
    note.write_text(
        "---\nreviewed: false\nreviewed: true\ntitle: test\n---\nBody text\n",
        encoding="utf-8",
    )
    mtime = note.stat().st_mtime
    from app.services.file_writer import FrontmatterCorruptError, edit_review_response
    with pytest.raises(FrontmatterCorruptError):
        edit_review_response(note, 0, "some response", mtime)
