from __future__ import annotations

import datetime as dt
import hashlib
import html as html_lib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter
import mistune

from app.config import settings


_markdown = mistune.create_markdown(
    plugins=["table", "strikethrough", "task_lists", "url"],
    escape=False,
)

# Briefing renderer intentionally omits the task_lists plugin so bracket
# markers survive into HTML as literal "[...]" — the interactive layer
# post-processes those into todo widgets.
_briefing_markdown = mistune.create_markdown(
    plugins=["table", "strikethrough", "url"],
    escape=False,
)

_BRIEFING_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-daily-briefing\.md$")

TODO_RE = re.compile(r"^(\s*[-*]\s+\[)([^\]]*)(\].*)$")

COMMENTS_MARKER = "> **Scott's comments:**"
WRITING_PROMPT_RESPONSE_MARKER = "> **Scott's response:**"

_WRITING_PROMPT_HEADING_RE = re.compile(r"^##\s+Writing Prompt")
_WRITING_PROMPT_TAG_RE = re.compile(r"\*{0,2}\[(technical|fiction)\]\*{0,2}")
_WRITING_PROMPT_PLACEHOLDER = "_[write here"


def parse_todo_line(line: str) -> dict | None:
    m = TODO_RE.match(line)
    if not m:
        return None
    return {"prefix": m.group(1), "content": m.group(2), "suffix": m.group(3)}


def line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:8]


def extract_writing_prompt(raw_md: str) -> dict | None:
    """Locate the Writing Prompt section in a briefing.

    Returns a dict with heading, prompt_text (markdown between heading and
    response block), tag (technical|fiction|None), response_block_start/end
    line indices, and response_content (blockquote body with leading '> '
    stripped). Returns None if no section or no response block is found.
    """
    lines = raw_md.splitlines()
    heading_idx = None
    for i, line in enumerate(lines):
        if _WRITING_PROMPT_HEADING_RE.match(line):
            heading_idx = i
            break
    if heading_idx is None:
        return None

    heading = lines[heading_idx].lstrip("#").strip()

    response_start = None
    for i in range(heading_idx + 1, len(lines)):
        if lines[i].rstrip() == WRITING_PROMPT_RESPONSE_MARKER:
            response_start = i
            break
        if lines[i].startswith("## "):
            return None
    if response_start is None:
        return None

    prompt_lines = []
    for i in range(heading_idx + 1, response_start):
        line = lines[i]
        if line.startswith(">"):
            continue
        prompt_lines.append(line)
    while prompt_lines and not prompt_lines[0].strip():
        prompt_lines.pop(0)
    while prompt_lines and not prompt_lines[-1].strip():
        prompt_lines.pop()
    prompt_text = "\n".join(prompt_lines)

    tag = None
    m = _WRITING_PROMPT_TAG_RE.search(prompt_text)
    if m:
        tag = m.group(1)

    j = response_start + 1
    while j < len(lines) and lines[j].startswith("> "):
        j += 1
    block_lines = [
        ln[2:] if ln.startswith("> ") else ln for ln in lines[response_start:j]
    ]
    response_content = "\n".join(block_lines)

    return {
        "heading": heading,
        "prompt_text": prompt_text,
        "tag": tag,
        "response_block_start": response_start,
        "response_block_end": j,
        "response_content": response_content,
    }


def render_writing_prompt_card(
    raw_md: str, filename: str, mtime: float, body_offset: int = 0
) -> str | None:
    """Render the Writing Prompt section as a self-contained HTML card.

    body_offset shifts embedded line indices so they match the full file
    (frontmatter + body) rather than body-only positions, since the write
    path operates on the full file.

    Returns None if no Writing Prompt section is present.
    """
    wp = extract_writing_prompt(raw_md)
    if wp is None:
        return None

    lines = raw_md.splitlines()
    block_lines = lines[wp["response_block_start"]:wp["response_block_end"]]
    rendered_bq = mistune.html("\n".join(block_lines))

    prompt_html = _markdown(wp["prompt_text"])

    is_placeholder = (
        _WRITING_PROMPT_PLACEHOLDER in wp["response_content"]
        or _PLACEHOLDER_MARKER in wp["response_content"]
    )
    placeholder_cls = " comment-placeholder" if is_placeholder else ""

    start_abs = wp["response_block_start"] + body_offset
    end_abs = wp["response_block_end"] + body_offset

    file_attr = html_lib.escape(filename, quote=True)
    content_attr = html_lib.escape(wp["response_content"], quote=True)
    marker_attr = html_lib.escape(WRITING_PROMPT_RESPONSE_MARKER, quote=True)
    heading_html = html_lib.escape(wp["heading"])
    tag_html = (
        f"<span class='writing-prompt-tag tag-{html_lib.escape(wp['tag'])}'>"
        f"[{html_lib.escape(wp['tag'])}]</span>"
        if wp["tag"]
        else ""
    )

    return (
        f"<section class='writing-prompt-card'>"
        f"<header class='writing-prompt-header'>"
        f"<h2>{heading_html}</h2>"
        f"{tag_html}"
        f"</header>"
        f"<div class='writing-prompt-body'>{prompt_html}</div>"
        f"<div class='comment-block writing-prompt-response{placeholder_cls}' "
        f"data-start='{start_abs}' "
        f"data-end='{end_abs}' "
        f"data-file=\"{file_attr}\" "
        f"data-mtime='{mtime}' "
        f"data-raw=\"{content_attr}\" "
        f"data-marker=\"{marker_attr}\" "
        f"onclick='openCommentEdit(this)'>"
        f"{rendered_bq.strip()}"
        f"</div>"
        f"</section>"
    )


def find_comment_blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip() == COMMENTS_MARKER:
            start = i
            j = i + 1
            while j < len(lines) and lines[j].startswith("> "):
                j += 1
            block_lines = [
                ln[2:] if ln.startswith("> ") else ln for ln in lines[start:j]
            ]
            content = "\n".join(block_lines)
            blocks.append({"start": start, "end": j, "content": content})
            i = j
        else:
            i += 1
    return blocks


@dataclass(frozen=True)
class NoteItem:
    path: Path
    title: str
    date: dt.date | None
    age_hours: float
    mtime: float = 0.0
    review_notes: list[str] = field(default_factory=list)
    review_responses: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DraftItem:
    path: Path
    title: str
    date: dt.date | None
    word_count: int
    status: str | None
    age_hours: float
    fact_checks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArchiveItem:
    path: Path
    filename: str
    date: dt.date | None


def parse_frontmatter(path: Path) -> dict[str, Any]:
    """Parse a markdown file's YAML frontmatter. Returns {} if no frontmatter."""
    post = frontmatter.load(path)
    return dict(post.metadata)


def _load_post(path: Path) -> frontmatter.Post:
    return frontmatter.load(path)


def _render(md_text: str) -> str:
    return _markdown(md_text)


def _build_todo_html(
    *,
    line_num: int,
    content: str,
    rest_html: str,
    hash_val: str,
    file_rel: str,
    mtime: float,
) -> str:
    """Render the interactive todo <li> for one bracket position."""
    file_attr = html_lib.escape(file_rel, quote=True)
    data_attrs = (
        f"data-line='{line_num}' "
        f"data-hash='{hash_val}' "
        f"data-file=\"{file_attr}\" "
        f"data-mtime='{mtime}'"
    )
    stripped = content.strip()
    if stripped == "":
        new_vals = json.dumps(
            {"file": file_rel, "line": line_num, "hash": hash_val, "new_content": "x"}
        )
        hx_vals = html_lib.escape(new_vals, quote=True)
        return (
            f"<li class='todo-item' {data_attrs}>"
            f"<input type='checkbox' class='todo-checkbox' "
            f"hx-patch='/edit/todo' "
            f"hx-vals='{hx_vals}' "
            f"hx-target='closest li' "
            f"hx-swap='outerHTML'>"
            f"<span class='todo-text'>{rest_html}</span>"
            f"<button class='todo-edit-btn' type='button' title='Edit state' "
            f"onclick='openTodoEdit(this)'>&#9998;</button>"
            f"</li>"
        )
    if stripped.lower() == "x":
        new_vals = json.dumps(
            {"file": file_rel, "line": line_num, "hash": hash_val, "new_content": ""}
        )
        hx_vals = html_lib.escape(new_vals, quote=True)
        return (
            f"<li class='todo-item todo-done' {data_attrs}>"
            f"<input type='checkbox' class='todo-checkbox' checked "
            f"hx-patch='/edit/todo' "
            f"hx-vals='{hx_vals}' "
            f"hx-target='closest li' "
            f"hx-swap='outerHTML'>"
            f"<span class='todo-text'>{rest_html}</span>"
            f"<button class='todo-edit-btn' type='button' title='Edit state' "
            f"onclick='openTodoEdit(this)'>&#9998;</button>"
            f"</li>"
        )
    pill = html_lib.escape(content)
    return (
        f"<li class='todo-item todo-pill-item' {data_attrs}>"
        f"<span class='todo-pill' onclick='openTodoEdit(this)'>{pill}</span>"
        f"<span class='todo-text'>{rest_html}</span>"
        f"<button class='todo-edit-btn' type='button' title='Edit state' "
        f"onclick='openTodoEdit(this)'>&#9998;</button>"
        f"</li>"
    )


_LI_BRACKET_RE = re.compile(r"<li>\[([^\]]*)\]([\s\S]*?)</li>")
_COMMENT_ANCHOR_RE = re.compile(
    r"<!--COMMENT_BLOCK start=(\d+) end=(\d+)-->\s*(<blockquote>[\s\S]*?</blockquote>)"
)
_PLACEHOLDER_MARKER = "_[status updates"


def render_briefing(
    raw_md: str, filename: str, mtime: float, body_offset: int = 0
) -> str:
    """Render a briefing to HTML with interactive todos + comment blocks.

    body_offset shifts data-line and data-start/data-end values so they
    match the full file (frontmatter + body), since the write path
    operates on full-file line indices.
    """
    lines = raw_md.splitlines()

    todos: list[dict] = []
    for i, line in enumerate(lines):
        if TODO_RE.match(line):
            todos.append(
                {
                    "line": i,
                    "content": TODO_RE.match(line).group(2),
                    "hash": line_hash(line),
                }
            )

    comment_blocks = find_comment_blocks(lines)

    annotated_lines = list(lines)
    for block in sorted(comment_blocks, key=lambda b: b["start"], reverse=True):
        end_marker = "<!--COMMENT_BLOCK_END-->"
        start_marker = (
            f"<!--COMMENT_BLOCK start={block['start']} end={block['end']}-->"
        )
        annotated_lines.insert(block["end"], "")
        annotated_lines.insert(block["end"], end_marker)
        annotated_lines.insert(block["start"], start_marker)
        annotated_lines.insert(block["start"], "")
    annotated_md = "\n".join(annotated_lines)

    html = _briefing_markdown(annotated_md)

    idx = [0]

    def _todo_sub(match: re.Match) -> str:
        if idx[0] >= len(todos):
            return match.group(0)
        todo = todos[idx[0]]
        idx[0] += 1
        rest_html = match.group(2)
        return _build_todo_html(
            line_num=todo["line"] + body_offset,
            content=todo["content"],
            rest_html=rest_html,
            hash_val=todo["hash"],
            file_rel=filename,
            mtime=mtime,
        )

    html = _LI_BRACKET_RE.sub(_todo_sub, html)

    def _comment_sub(match: re.Match) -> str:
        start = int(match.group(1))
        end = int(match.group(2))
        bq = match.group(3)
        block = next(
            (b for b in comment_blocks if b["start"] == start and b["end"] == end),
            None,
        )
        content = block["content"] if block else ""
        placeholder_cls = (
            " comment-placeholder" if _PLACEHOLDER_MARKER in content else ""
        )
        file_attr = html_lib.escape(filename, quote=True)
        content_attr = html_lib.escape(content, quote=True)
        marker_attr = html_lib.escape(COMMENTS_MARKER, quote=True)
        return (
            f"<div class='comment-block{placeholder_cls}' "
            f"data-start='{start + body_offset}' data-end='{end + body_offset}' "
            f"data-file=\"{file_attr}\" "
            f"data-mtime='{mtime}' "
            f"data-raw=\"{content_attr}\" "
            f"data-marker=\"{marker_attr}\" "
            f"onclick='openCommentEdit(this)'>"
            f"{bq}"
            f"</div>"
        )

    html = _COMMENT_ANCHOR_RE.sub(_comment_sub, html)
    html = html.replace("<!--COMMENT_BLOCK_END-->", "")
    return html


def _coerce_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    return [str(value)]


def _title_from(meta: dict[str, Any], path: Path, body: str | None = None) -> str:
    raw = meta.get("title")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if body:
        for line in body.splitlines()[:20]:
            if line.startswith("# "):
                candidate = line[2:].strip()
                if candidate:
                    return candidate
    return path.stem


def _mtime_date(path: Path) -> dt.date:
    return dt.datetime.fromtimestamp(path.stat().st_mtime).date()


def _age_hours_from_mtime(path: Path, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now()
    return (now.timestamp() - path.stat().st_mtime) / 3600.0


def _compute_body_offset(full_text: str, body_text: str) -> int:
    """Number of lines in full_text before body_text begins."""
    idx = full_text.find(body_text)
    if idx < 0:
        return 0
    return full_text[:idx].count("\n")


def load_briefing(date: dt.date) -> tuple[dict, str, str, str, float, int] | None:
    """Load a daily briefing by date.

    Returns (metadata, raw_body, rendered_html, filename, mtime, body_offset)
    or None. Rendered HTML line indices are full-file (frontmatter + body)
    to match the write path; body_offset is exposed so other consumers
    (e.g. the writing prompt card) can apply the same shift.
    """
    filename = f"{date.isoformat()}-daily-briefing.md"
    path = settings.scott_inbox / filename
    if not path.is_file():
        return None
    post = _load_post(path)
    mtime = path.stat().st_mtime
    full_text = path.read_text(encoding="utf-8")
    body_offset = _compute_body_offset(full_text, post.content)
    html = render_briefing(post.content, filename, mtime, body_offset)
    return dict(post.metadata), post.content, html, filename, mtime, body_offset


def find_most_recent_briefing() -> tuple[dt.date, str] | None:
    """Scan scott/inbox/ for YYYY-MM-DD-daily-briefing.md. Return (date, filename)
    of the newest one found, or None. Does not look in briefing-archive."""
    inbox = settings.scott_inbox
    if not inbox.is_dir():
        return None
    candidates: list[tuple[dt.date, str]] = []
    for entry in inbox.iterdir():
        if not entry.is_file():
            continue
        m = _BRIEFING_RE.match(entry.name)
        if not m:
            continue
        try:
            d = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        candidates.append((d, entry.name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0]


def _needs_review_item(md_path: Path, now: dt.datetime) -> NoteItem | None:
    try:
        meta = parse_frontmatter(md_path)
    except Exception:
        return None
    if meta.get("needs_review") is not True:
        return None
    if meta.get("reviewed") is True:
        return None

    note_date = _coerce_date(meta.get("date"))
    if note_date is not None:
        age = now - dt.datetime.combine(note_date, dt.time.min)
        age_hours = age.total_seconds() / 3600.0
    else:
        age_hours = _age_hours_from_mtime(md_path, now)

    # Title extraction may need the body; load again if we want a heading scan.
    title = _title_from(meta, md_path)
    if not meta.get("title"):
        try:
            post = _load_post(md_path)
            title = _title_from(meta, md_path, post.content)
        except Exception:
            pass

    try:
        mtime = md_path.stat().st_mtime
    except OSError:
        mtime = 0.0

    review_notes = _coerce_str_list(meta.get("review_notes"))
    raw_responses = meta.get("review_responses") or []
    if isinstance(raw_responses, list):
        review_responses = [str(x) if x is not None else "" for x in raw_responses]
    else:
        review_responses = [str(raw_responses)]
    while len(review_responses) < len(review_notes):
        review_responses.append("")

    return NoteItem(
        path=md_path,
        title=title,
        date=note_date,
        age_hours=age_hours,
        mtime=mtime,
        review_notes=review_notes,
        review_responses=review_responses,
    )


def load_needs_attention() -> list[NoteItem]:
    """Collect notes from kb/ (excluding kb/Attachments/) and
    agents/shallan/inbox/ that have needs_review=true and reviewed != true.
    Sorted oldest-first."""
    items: list[NoteItem] = []
    now = dt.datetime.now()

    kb = settings.kb
    if kb.is_dir():
        attachments = (kb / "Attachments").resolve()
        for md_path in kb.rglob("*.md"):
            try:
                resolved = md_path.resolve()
            except OSError:
                continue
            if resolved == attachments or attachments in resolved.parents:
                continue
            item = _needs_review_item(md_path, now)
            if item is not None:
                items.append(item)

    shallan = settings.shallan_inbox
    if shallan.is_dir():
        for md_path in shallan.glob("*.md"):
            item = _needs_review_item(md_path, now)
            if item is not None:
                items.append(item)

    items.sort(key=lambda it: it.age_hours, reverse=True)
    return items


def load_drafts() -> list[DraftItem]:
    """List content drafts in scott/inbox/content-drafts/."""
    items: list[DraftItem] = []
    drafts_dir = settings.content_drafts
    if not drafts_dir.is_dir():
        return items

    now = dt.datetime.now()
    for md_path in sorted(drafts_dir.glob("*.md")):
        try:
            post = _load_post(md_path)
        except Exception:
            continue
        meta = dict(post.metadata)
        word_count = len(post.content.split())
        status_raw = meta.get("status")
        status = str(status_raw) if status_raw is not None else None
        items.append(
            DraftItem(
                path=md_path,
                title=_title_from(meta, md_path, post.content),
                date=_coerce_date(meta.get("date")),
                word_count=word_count,
                status=status,
                age_hours=_age_hours_from_mtime(md_path, now),
                fact_checks=_coerce_str_list(meta.get("fact_checks")),
            )
        )
    return items


def list_archive() -> list[ArchiveItem]:
    """List archived briefings newest-first."""
    items: list[ArchiveItem] = []
    archive_dir = settings.briefing_archive
    if not archive_dir.is_dir():
        return items

    for md_path in archive_dir.glob("*.md"):
        meta: dict[str, Any] = {}
        try:
            meta = parse_frontmatter(md_path)
        except Exception:
            pass
        date = _coerce_date(meta.get("date"))
        if date is None:
            # Fall back to date embedded in filename: YYYY-MM-DD-*.md
            try:
                date = dt.date.fromisoformat(md_path.name[:10])
            except ValueError:
                date = _mtime_date(md_path)
        items.append(
            ArchiveItem(
                path=md_path,
                filename=md_path.name,
                date=date,
            )
        )

    items.sort(key=lambda it: (it.date or dt.date.min, it.filename), reverse=True)
    return items


def load_archive_item(filename: str) -> tuple[dict, str, str] | None:
    """Load a single archived briefing by filename.

    Returns (metadata_dict, raw_markdown, rendered_html) or None.
    """
    archive_dir = settings.briefing_archive
    candidate = archive_dir / filename
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved.parent != archive_dir.resolve():
        return None
    if not resolved.is_file() or resolved.suffix != ".md":
        return None
    post = _load_post(resolved)
    return dict(post.metadata), post.content, _render(post.content)
