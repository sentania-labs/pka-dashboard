from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services import notes


router = APIRouter()


def _today_context() -> dict:
    today_date = dt.date.today()
    loaded = notes.load_briefing(today_date)
    if loaded is not None:
        meta, raw, html_body, filename, mtime, body_offset = loaded
        writing_prompt_html = notes.render_writing_prompt_card(
            raw, filename, mtime, body_offset
        )
        return {
            "today_date": today_date,
            "body_html": html_body,
            "writing_prompt_html": writing_prompt_html,
            "frontmatter_meta": meta,
            "last_briefing": None,
            "briefing_filename": filename,
            "briefing_mtime": mtime,
        }
    recent = notes.find_most_recent_briefing()
    last_briefing = None
    if recent is not None:
        last_briefing = {"date": recent[0], "filename": recent[1]}
    return {
        "today_date": today_date,
        "body_html": None,
        "writing_prompt_html": None,
        "frontmatter_meta": {},
        "last_briefing": last_briefing,
    }


@router.get("/", response_class=HTMLResponse)
def today(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    ctx = _today_context()
    ctx["active"] = "today"
    return templates.TemplateResponse(request, "today.html", ctx)


@router.get("/partials/today-body", response_class=HTMLResponse)
def today_body_partial(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    ctx = _today_context()
    return templates.TemplateResponse(request, "_today_body.html", ctx)
