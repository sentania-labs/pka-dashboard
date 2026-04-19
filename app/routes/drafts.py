from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services import notes


router = APIRouter()


@router.get("/drafts", response_class=HTMLResponse)
def drafts(request: Request) -> HTMLResponse:
    items = sorted(notes.load_drafts(), key=lambda d: d.age_hours, reverse=True)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "drafts.html",
        {
            "active": "drafts",
            "items": items,
        },
    )
