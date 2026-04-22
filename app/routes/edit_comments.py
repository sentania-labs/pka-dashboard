from __future__ import annotations

import html as html_lib
import json
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.services import audit_log, notes
from app.services.file_writer import (
    MtimeConflictError,
    edit_comment_block,
    read_with_mtime,
)

_ALLOWED_MARKERS = {
    notes.COMMENTS_MARKER,
    notes.WRITING_PROMPT_RESPONSE_MARKER,
}


router = APIRouter()


def _resolve_under(base: Path, file: str) -> Path | None:
    candidate = (base / file).resolve()
    try:
        base_resolved = base.resolve()
    except OSError:
        return None
    if base_resolved != candidate and base_resolved not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _toast_error(msg: str) -> HTMLResponse:
    body = (
        "<div id='toast-container' hx-swap-oob='beforeend:#toast-container'>"
        f"<div class='toast toast-error'>{msg}</div>"
        "</div>"
    )
    return HTMLResponse(body, status_code=409)


def _serialise_blockquote(new_content: str, marker: str) -> list[str]:
    """Turn edited body text into blockquote lines with marker on line 0."""
    lines_in = new_content.split("\n")
    for known in _ALLOWED_MARKERS:
        if lines_in and lines_in[0].strip() == known.strip():
            lines_in = lines_in[1:]
            break
    out = [marker]
    for ln in lines_in:
        if ln == "":
            out.append(">")
        else:
            out.append(f"> {ln}")
    return out


@router.patch("/edit/comments", response_class=HTMLResponse)
def edit_comments(
    request: Request,
    file: str = Form(...),
    block_start: int = Form(...),
    block_end: int = Form(...),
    new_content: str = Form(...),
    mtime: float = Form(...),
    marker: str = Form(""),
) -> HTMLResponse:
    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    path = _resolve_under(settings.scott_inbox, file)
    if path is None:
        audit_log.record(
            "edit_comments", file, status="fail", reason="path-not-allowed",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File not found or outside inbox.")

    chosen_marker = marker if marker in _ALLOWED_MARKERS else notes.COMMENTS_MARKER

    serialised = _serialise_blockquote(new_content, chosen_marker)
    new_block_text = "\n".join(serialised)

    try:
        edit_comment_block(path, block_start, block_end, new_block_text, mtime)
    except MtimeConflictError:
        audit_log.record(
            "edit_comments", file, status="fail", reason="mtime-conflict",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File changed on disk — refresh.")
    except ValueError:
        audit_log.record(
            "edit_comments", file, status="fail", reason="block-range-invalid",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("Block range invalid — refresh.")

    audit_log.record(
        "edit_comments", file, remote_addr=client_ip, ua=ua,
    )

    # Recompute updated block position so the edit widget stays consistent.
    text, new_mtime = read_with_mtime(path)
    all_lines = text.splitlines()
    new_end = block_start + len(serialised)
    block_lines = all_lines[block_start:new_end]
    content_lines = [
        ln[2:] if ln.startswith("> ") else ln[1:] if ln.startswith(">") else ln
        for ln in block_lines
    ]
    raw_content = "\n".join(content_lines)

    rendered_bq = notes.render_markdown("\n".join(block_lines))

    is_placeholder = (
        notes._PLACEHOLDER_MARKER in raw_content
        or notes._WRITING_PROMPT_PLACEHOLDER in raw_content
    )
    placeholder_cls = " comment-placeholder" if is_placeholder else ""
    is_wp_response = chosen_marker == notes.WRITING_PROMPT_RESPONSE_MARKER
    wp_cls = " writing-prompt-response" if is_wp_response else ""
    file_attr = html_lib.escape(file, quote=True)
    content_attr = html_lib.escape(raw_content, quote=True)
    marker_attr = html_lib.escape(chosen_marker, quote=True)

    fragment = (
        f"<div class='comment-block{wp_cls}{placeholder_cls}' "
        f"data-start='{block_start}' data-end='{new_end}' "
        f"data-file=\"{file_attr}\" "
        f"data-mtime='{new_mtime}' "
        f"data-raw=\"{content_attr}\" "
        f"data-marker=\"{marker_attr}\" "
        f"onclick='openCommentEdit(this)'>"
        f"{rendered_bq.strip()}"
        f"</div>"
    )
    response = HTMLResponse(fragment)
    response.headers["HX-Trigger"] = json.dumps(
        {"commentssaved": {"file": file, "mtime": new_mtime}}
    )
    return response
