from __future__ import annotations

import html as html_lib
import json
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.services import audit_log
from app.services.file_writer import (
    MtimeConflictError,
    edit_frontmatter_field,
)


router = APIRouter()


def _toast_error(msg: str) -> HTMLResponse:
    body = (
        "<div id='toast-container' hx-swap-oob='beforeend:#toast-container'>"
        f"<div class='toast toast-error'>{msg}</div>"
        "</div>"
    )
    return HTMLResponse(body, status_code=409)


def _resolve_allowed(file_path: str) -> Path | None:
    candidate = (settings.pka_root / file_path).resolve()
    kb = settings.kb.resolve()
    shallan = settings.shallan_inbox.resolve()
    if kb not in candidate.parents and shallan not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


@router.post("/edit/reviewed", response_class=HTMLResponse)
def edit_reviewed(
    request: Request,
    file_path: str = Form(...),
    mtime: float = Form(...),
) -> HTMLResponse:
    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    path = _resolve_allowed(file_path)
    if path is None:
        audit_log.record(
            "edit_reviewed", file_path, status="fail", reason="path-not-allowed",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File not allowed.")

    try:
        edit_frontmatter_field(path, "reviewed", True, mtime)
    except MtimeConflictError:
        audit_log.record(
            "edit_reviewed", file_path, status="fail", reason="mtime-conflict",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File changed on disk — refresh.")

    audit_log.record(
        "edit_reviewed", file_path, remote_addr=client_ip, ua=ua,
    )
    new_mtime = path.stat().st_mtime
    safe_path = html_lib.escape(file_path, quote=True)
    toast_frag = (
        "<div id='toast-container' hx-swap-oob='beforeend:#toast-container'>"
        "<div class='toast toast-success toast-undo'>"
        "Marked reviewed — "
        f"<a href='#' class='undo-link' "
        f"  hx-post='/edit/reviewed-undo' "
        f"  hx-vals='{{\"file_path\": \"{safe_path}\", \"mtime\": {new_mtime}}}' "
        f"  hx-swap='none'>Undo</a>"
        "</div>"
        "</div>"
    )
    response = HTMLResponse(toast_frag)
    response.headers["HX-Trigger"] = json.dumps(
        {"reviewsaved": {"file": file_path, "mtime": new_mtime}}
    )
    return response


@router.post("/edit/reviewed-undo", response_class=HTMLResponse)
def edit_reviewed_undo(
    request: Request,
    file_path: str = Form(...),
    mtime: float = Form(...),
) -> HTMLResponse:
    client_ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    path = _resolve_allowed(file_path)
    if path is None:
        audit_log.record(
            "edit_reviewed_undo", file_path, status="fail", reason="path-not-allowed",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File not allowed.")
    try:
        edit_frontmatter_field(path, "reviewed", False, mtime)
    except MtimeConflictError:
        audit_log.record(
            "edit_reviewed_undo", file_path, status="fail", reason="mtime-conflict",
            remote_addr=client_ip, ua=ua,
        )
        return _toast_error("File changed — undo not possible.")

    audit_log.record(
        "edit_reviewed_undo", file_path, remote_addr=client_ip, ua=ua,
    )
    response = HTMLResponse(
        "<div id='toast-container' hx-swap-oob='beforeend:#toast-container'>"
        "<div class='toast toast-success'>Undo applied — refresh to see note.</div>"
        "</div>"
    )
    return response
