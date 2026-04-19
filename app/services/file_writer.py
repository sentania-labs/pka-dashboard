from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML as RuamelYAML
from ruamel.yaml import YAMLError
from ruamel.yaml.constructor import DuplicateKeyError


@dataclass
class ReviewResponseResult:
    new_mtime: float
    marked_reviewed: bool


_yaml = RuamelYAML()
_yaml.preserve_quotes = True
_yaml.width = 1_000_000
_yaml.indent(mapping=2, sequence=4, offset=2)


class MtimeConflictError(RuntimeError):
    pass


class FrontmatterCorruptError(RuntimeError):
    pass


def read_with_mtime(path: Path) -> tuple[str, float]:
    text = path.read_text(encoding="utf-8")
    mtime = path.stat().st_mtime
    return text, mtime


def write_atomic(
    path: Path,
    content: str,
    expected_mtime: float,
    tolerance: float = 0.01,
) -> None:
    current_mtime = path.stat().st_mtime
    if abs(current_mtime - expected_mtime) > tolerance:
        raise MtimeConflictError(
            f"mtime drift on {path}: expected {expected_mtime}, found {current_mtime}"
        )
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def _split_frontmatter(path: Path, text: str) -> tuple[str, str]:
    """Split a markdown file with YAML frontmatter into (yaml_text, body_text)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        raise ValueError(f"No frontmatter found in {path}")
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"Unclosed frontmatter in {path}")
    yaml_text = "".join(lines[1:end_idx])
    body_text = "".join(lines[end_idx + 1:])
    return yaml_text, body_text


def edit_frontmatter_field(
    path: Path,
    field: str,
    value: Any,
    expected_mtime: float,
) -> None:
    text, _ = read_with_mtime(path)
    yaml_text, body_text = _split_frontmatter(path, text)

    try:
        data = _yaml.load(yaml_text)
    except (DuplicateKeyError, YAMLError) as exc:
        raise FrontmatterCorruptError(
            f"Frontmatter parse error in {path.name}: {exc}"
        ) from exc
    data[field] = value
    buf = io.StringIO()
    _yaml.dump(data, buf)
    new_yaml = buf.getvalue()

    new_content = "---\n" + new_yaml + "---\n" + body_text
    write_atomic(path, new_content, expected_mtime)


def edit_review_response(
    path: Path,
    index: int,
    response_text: str,
    expected_mtime: float,
    *,
    auto_mark_reviewed: bool = True,
) -> ReviewResponseResult:
    """Set review_responses[index] = response_text.

    If review_responses is absent or shorter than index+1, extend it with
    empty strings. Preserves YAML layout via ruamel.yaml round-trip.

    When auto_mark_reviewed is True and every review_notes entry now has a
    non-empty response, set reviewed=True in the same round-trip write.
    """
    text, _ = read_with_mtime(path)
    yaml_text, body_text = _split_frontmatter(path, text)

    try:
        data = _yaml.load(yaml_text)
    except (DuplicateKeyError, YAMLError) as exc:
        raise FrontmatterCorruptError(
            f"Frontmatter parse error in {path.name}: {exc}"
        ) from exc
    responses = list(data.get("review_responses") or [])
    while len(responses) <= index:
        responses.append("")
    responses[index] = response_text
    data["review_responses"] = responses

    notes_list = list(data.get("review_notes") or [])
    all_complete = (
        len(notes_list) > 0
        and len(responses) >= len(notes_list)
        and all(
            (r or "").strip() for r in responses[: len(notes_list)]
        )
    )
    marked_reviewed = False
    if all_complete and auto_mark_reviewed and data.get("reviewed") is not True:
        data["reviewed"] = True
        marked_reviewed = True

    buf = io.StringIO()
    _yaml.dump(data, buf)
    new_content = "---\n" + buf.getvalue() + "---\n" + body_text
    write_atomic(path, new_content, expected_mtime)

    new_mtime = path.stat().st_mtime
    return ReviewResponseResult(new_mtime=new_mtime, marked_reviewed=marked_reviewed)


def _line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:8]


def edit_line(
    path: Path,
    line_number: int,
    expected_line_hash: str,
    new_line: str,
    expected_mtime: float,
) -> None:
    text, mtime = read_with_mtime(path)
    if abs(mtime - expected_mtime) > 0.01:
        raise MtimeConflictError(
            f"mtime drift on {path}: expected {expected_mtime}, found {mtime}"
        )
    lines = text.splitlines(keepends=True)
    if line_number < 0 or line_number >= len(lines):
        raise ValueError(
            f"line_number {line_number} out of range (file has {len(lines)} lines)"
        )
    current = lines[line_number].rstrip("\n").rstrip("\r")
    if _line_hash(current) != expected_line_hash:
        raise MtimeConflictError(
            f"line hash drift on {path}:{line_number} — content changed"
        )
    trailing = ""
    orig = lines[line_number]
    if orig.endswith("\r\n"):
        trailing = "\r\n"
    elif orig.endswith("\n"):
        trailing = "\n"
    lines[line_number] = new_line + trailing
    write_atomic(path, "".join(lines), expected_mtime)


def edit_comment_block(
    path: Path,
    block_start_line: int,
    block_end_line: int,
    new_content: str,
    expected_mtime: float,
) -> None:
    text, mtime = read_with_mtime(path)
    if abs(mtime - expected_mtime) > 0.01:
        raise MtimeConflictError(
            f"mtime drift on {path}: expected {expected_mtime}, found {mtime}"
        )
    lines = text.splitlines(keepends=True)
    if block_start_line < 0 or block_end_line > len(lines) or block_start_line > block_end_line:
        raise ValueError(
            f"block [{block_start_line}:{block_end_line}] out of range "
            f"(file has {len(lines)} lines)"
        )
    new_lines = [ln + "\n" for ln in new_content.split("\n")]
    lines[block_start_line:block_end_line] = new_lines
    write_atomic(path, "".join(lines), expected_mtime)
