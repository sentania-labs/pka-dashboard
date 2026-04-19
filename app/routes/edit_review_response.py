from __future__ import annotations

import html as html_lib
import json
from pathlib import Path

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from app.config import settings
from app.services.file_writer import (
    FrontmatterCorruptError,
    MtimeConflictError,
    ReviewResponseResult,
    edit_review_response,
)


router = APIRouter()


def _toast_error(msg: str, *, draft: str = "") -> HTMLResponse:
    safe_draft = html_lib.escape(draft, quote=True)
    body = (
        "<div id='toast-container' hx-swap-oob='beforeend:#toast-container' "
        f"data-draft=\"{safe_draft}\">"
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


def _render_item_fragment(
    *,
    file_rel: str,
    index: int,
    response_text: str,
    mtime: float,
    note_text: str,
    question_number: int,
    wrapper_id: str,
) -> str:
    file_attr = html_lib.escape(file_rel, quote=True)
    wrapper_attr = html_lib.escape(wrapper_id, quote=True)
    note_attr = html_lib.escape(note_text, quote=True)
    note_html = html_lib.escape(note_text)
    response_html = html_lib.escape(response_text)
    save_status = "saved" if response_text else ""
    return (
        f"<div class='review-item' id='{wrapper_attr}'>"
        f"<div class='review-question'>"
        f"<small>{question_number}. {note_html}</small>"
        f"</div>"
        f"<div class='review-response-area'>"
        f"<input type='hidden' name='file_path' value=\"{file_attr}\">"
        f"<input type='hidden' name='index' value='{index}'>"
        f"<input type='hidden' name='mtime' value='{mtime}'>"
        f"<input type='hidden' name='wrapper_id' value=\"{wrapper_attr}\">"
        f"<input type='hidden' name='note_text' value=\"{note_attr}\">"
        f"<input type='hidden' name='question_number' value='{question_number}'>"
        f"<textarea name='response_text' class='review-response-textarea' "
        f"placeholder='Your response...' "
        f"data-file=\"{file_attr}\" "
        f"data-index='{index}' "
        f"data-mtime='{mtime}' "
        f"data-save-status='{save_status}' "
        f"hx-patch='/edit/review-response' "
        f"hx-trigger='blur, change delay:50ms' "
        f"hx-include='closest .review-item' "
        f"hx-target='closest .review-item' "
        f"hx-swap='outerHTML' "
        f"hx-sync='closest li:queue all'>"
        f"{response_html}"
        f"</textarea>"
        f"</div>"
        f"</div>"
    )


@router.patch("/edit/review-response", response_class=HTMLResponse)
def edit_review_response_route(
    file_path: str = Form(...),
    index: int = Form(...),
    response_text: str = Form(""),
    mtime: float = Form(...),
    wrapper_id: str = Form(""),
    note_text: str = Form(""),
    question_number: int = Form(0),
) -> HTMLResponse:
    path = _resolve_allowed(file_path)
    if path is None:
        return _toast_error("File not allowed.", draft=response_text)

    try:
        result: ReviewResponseResult = edit_review_response(
            path, index, response_text, mtime
        )
    except MtimeConflictError:
        return _toast_error("File changed on disk — refresh.", draft=response_text)
    except FrontmatterCorruptError as exc:
        return _toast_error(
            f"Can't save: note frontmatter is corrupt ({exc}). Fix the file manually.",
            draft=response_text,
        )
    except Exception as exc:
        return _toast_error(f"Write failed: {exc}", draft=response_text)

    fragment = _render_item_fragment(
        file_rel=file_path,
        index=index,
        response_text=response_text,
        mtime=result.new_mtime,
        note_text=note_text,
        question_number=question_number or (index + 1),
        wrapper_id=wrapper_id or f"review-item-{index}",
    )
    response = HTMLResponse(fragment)
    event_key = "allreviewed" if result.marked_reviewed else "responsesaved"
    response.headers["HX-Trigger"] = json.dumps(
        {event_key: {"file": file_path, "mtime": result.new_mtime}}
    )
    return response


@router.post("/edit/review-response", response_class=HTMLResponse)
def edit_review_response_post(
    file_path: str = Form(...),
    index: int = Form(...),
    response_text: str = Form(""),
    mtime: float = Form(...),
    wrapper_id: str = Form(""),
    note_text: str = Form(""),
    question_number: int = Form(0),
) -> HTMLResponse:
    return edit_review_response_route(
        file_path=file_path,
        index=index,
        response_text=response_text,
        mtime=mtime,
        wrapper_id=wrapper_id,
        note_text=note_text,
        question_number=question_number,
    )
