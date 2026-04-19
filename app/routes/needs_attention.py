from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services import notes
from app.services.notes import DraftItem, NoteItem


router = APIRouter()


def _bucket(item: NoteItem) -> str:
    if item.age_hours < 24:
        return "fresh"
    if item.age_hours < 72:
        return "aging"
    return "stale"


BUCKET_LABELS = {
    "fresh": "< 24 hours",
    "aging": "24 – 72 hours",
    "stale": "> 72 hours",
}


@router.get("/needs-attention", response_class=HTMLResponse)
def needs_attention(request: Request) -> HTMLResponse:
    items = notes.load_needs_attention()
    grouped: dict[str, list[NoteItem]] = {"fresh": [], "aging": [], "stale": []}
    for it in items:
        grouped[_bucket(it)].append(it)

    # Oldest-first within each bucket.
    for bucket in grouped.values():
        bucket.sort(key=lambda it: it.age_hours, reverse=True)

    drafts = notes.load_drafts()
    aging_drafts: list[DraftItem] = sorted(
        (d for d in drafts if d.age_hours > 24),
        key=lambda d: d.age_hours,
        reverse=True,
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "needs_attention.html",
        {
            "active": "needs-attention",
            "grouped": grouped,
            "bucket_labels": BUCKET_LABELS,
            "total": len(items),
            "aging_drafts": aging_drafts,
        },
    )
