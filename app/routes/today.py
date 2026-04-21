from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.config import settings
from app.services import notes


router = APIRouter()


def _today_context() -> dict:
    today_date = dt.datetime.now(settings.tz).date()
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
            "fallback_banner": False,
            "fallback_date": None,
            "briefing_is_archive": False,
        }
    recent = notes.find_most_recent_briefing()
    if recent is not None:
        fallback_date, fallback_filename, source = recent
        fallback_dir = (
            settings.scott_inbox if source == "inbox" else settings.briefing_archive
        )
        fallback_loaded = notes.load_briefing_by_path(
            fallback_dir / fallback_filename
        )
        if fallback_loaded is not None:
            meta, raw, html_body, filename, mtime, body_offset = fallback_loaded
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
                "fallback_banner": True,
                "fallback_date": fallback_date,
                "briefing_is_archive": source == "archive",
            }
    return {
        "today_date": today_date,
        "body_html": None,
        "writing_prompt_html": None,
        "frontmatter_meta": {},
        "last_briefing": None,
        "fallback_banner": False,
        "fallback_date": None,
        "briefing_is_archive": False,
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
