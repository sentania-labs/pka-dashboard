from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

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
from app.services import csrf


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["relative_to_pka"] = lambda p: str(
    Path(p).relative_to(settings.pka_root)
)
templates.env.globals["idle_lock_seconds"] = settings.idle_lock_seconds
templates.env.globals["csrf_cookie_name"] = csrf.COOKIE_NAME
templates.env.globals["csrf_header_name"] = csrf.HEADER_NAME

app = FastAPI(title="Renarin — PKA Dashboard")
app.state.templates = templates


class CSRFMiddleware(BaseHTTPMiddleware):
    """Issue a CSRF cookie on GETs; verify the header on mutating routes.

    Only /edit/* paths are mutating today, but we apply the check to any
    mutating method so a future route can't accidentally skip the guard.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in csrf.MUTATING_METHODS:
            try:
                csrf.verify(request)
            except Exception as exc:
                status = getattr(exc, "status_code", 403)
                detail = getattr(exc, "detail", "Forbidden")
                return JSONResponse({"detail": detail}, status_code=status)
            return await call_next(request)

        response = await call_next(request)
        # Only attach the cookie to HTML-ish GETs — avoids polluting JSON/static.
        content_type = response.headers.get("content-type", "")
        if request.method == "GET" and "text/html" in content_type:
            csrf.ensure_token(request, response)
        return response


app.add_middleware(CSRFMiddleware)

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
