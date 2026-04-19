from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.services import audit_log, notes
from app.services.file_writer import (
    MtimeConflictError,
    edit_line,
    read_with_mtime,
)


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


@router.patch("/edit/todo", response_class=HTMLResponse)
def edit_todo(
    request: Request,
    file: str = Form(...),
    line: int = Form(...),
    hash: str = Form(...),
    new_content: str = Form(...),
) -> HTMLResponse:
    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    path = _resolve_under(settings.scott_inbox, file)
    if path is None:
        audit_log.record(
            "edit_todo", file, status="fail", reason="path-not-allowed",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File not found or outside inbox.")

    try:
        text, mtime = read_with_mtime(path)
        file_lines = text.splitlines()
        if line < 0 or line >= len(file_lines):
            audit_log.record(
                "edit_todo", file, status="fail", reason="line-out-of-range",
                remote_addr=client_ip, ua=ua,
            )
            return _toast_error("Line out of range — refresh.")
        current_line = file_lines[line]
        if notes.line_hash(current_line) != hash:
            audit_log.record(
                "edit_todo", file, status="fail", reason="hash-mismatch",
                remote_addr=client_ip, ua=ua,
            )
            return _toast_error("Todo changed on disk — refresh.")

        parsed = notes.parse_todo_line(current_line)
        if parsed is None:
            audit_log.record(
                "edit_todo", file, status="fail", reason="not-a-todo",
                remote_addr=client_ip, ua=ua,
            )
            return _toast_error("Line is not a todo — refresh.")

        rebuilt = f"{parsed['prefix']}{new_content}{parsed['suffix']}"
        edit_line(path, line, hash, rebuilt, mtime)
    except MtimeConflictError:
        audit_log.record(
            "edit_todo", file, status="fail", reason="mtime-conflict",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File changed on disk — refresh.")

    audit_log.record(
        "edit_todo", file, remote_addr=client_ip, ua=ua,
    )

    new_hash = notes.line_hash(rebuilt)
    filename = path.name
    new_mtime = path.stat().st_mtime
    suffix_md = parsed["suffix"][1:] if parsed["suffix"].startswith("]") else parsed["suffix"]
    import mistune

    rest_html = mistune.html(suffix_md.strip()) or ""
    rest_html = rest_html.strip()
    if rest_html.startswith("<p>") and rest_html.endswith("</p>"):
        rest_html = rest_html[3:-4]

    from app.services.notes import _build_todo_html

    fragment = _build_todo_html(
        line_num=line,
        content=new_content,
        rest_html=rest_html,
        hash_val=new_hash,
        file_rel=filename,
        mtime=new_mtime,
    )

    response = HTMLResponse(fragment)
    response.headers["HX-Trigger"] = "todosaved"
    return response
