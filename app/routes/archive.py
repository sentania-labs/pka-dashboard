from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.services import notes


router = APIRouter()


@router.get("/archive", response_class=HTMLResponse)
def archive_list(request: Request) -> HTMLResponse:
    items = notes.list_archive()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "archive.html",
        {
            "active": "archive",
            "items": items,
            "item": None,
            "item_meta": None,
        },
    )


@router.get("/archive/{filename}", response_class=HTMLResponse)
def archive_item(request: Request, filename: str) -> HTMLResponse:
    loaded = notes.load_archive_item(filename)
    if loaded is None:
        raise HTTPException(status_code=404, detail="archive item not found")
    meta, _raw, html_body = loaded
    items = notes.list_archive()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "archive.html",
        {
            "active": "archive",
            "items": items,
            "item": {"filename": filename, "body_html": html_body},
            "item_meta": meta,
        },
    )
