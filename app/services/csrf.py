from __future__ import annotations

import hmac
import secrets

from fastapi import HTTPException, Request, Response


COOKIE_NAME = "renarin_csrf"
HEADER_NAME = "X-CSRF-Token"
_TOKEN_BYTES = 32
# Mutating HTTP methods that must carry a valid token.
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def ensure_token(request: Request, response: Response) -> str:
    """Issue a CSRF cookie on GETs if one isn't already set. Idempotent."""
    existing = request.cookies.get(COOKIE_NAME)
    if existing:
        return existing
    token = _new_token()
    # Readable by JS so the client can echo it in the header.
    # LAN app, no auth — this is a defence-in-depth shim, not the whole story.
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=False,
        samesite="strict",
        secure=False,
        path="/",
        max_age=60 * 60 * 24 * 30,
    )
    return token


def verify(request: Request) -> None:
    """Raise 403 if the request's CSRF header doesn't match the cookie.

    For non-mutating methods this is a no-op.
    """
    if request.method not in MUTATING_METHODS:
        return
    cookie_token = request.cookies.get(COOKIE_NAME)
    header_token = request.headers.get(HEADER_NAME)
    if not cookie_token or not header_token:
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Bad CSRF token")
