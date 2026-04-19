from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.routes import (
    archive,
    drafts,
    edit_comments,
    edit_review,
    edit_review_response,
    edit_todo,
    needs_attention,
    today,
)


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["relative_to_pka"] = lambda p: str(
    Path(p).relative_to(settings.pka_root)
)

app = FastAPI(title="Renarin — PKA Dashboard")
app.state.templates = templates

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(today.router)
app.include_router(needs_attention.router)
app.include_router(drafts.router)
app.include_router(archive.router)
app.include_router(edit_todo.router)
app.include_router(edit_comments.router)
app.include_router(edit_review.router)
app.include_router(edit_review_response.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
