"""CSRF for the browser's session cookie: a double-submit token.

GET /api/session sets the coji_csrf cookie (readable by the page, SameSite=Lax) and answers the
same token. Every write to /api/ must send it back in X-CSRF-Token; a page on another site can
neither read the cookie nor set the header. When the browser names an Origin, it must be this
site or a trusted one (the Vite dev server). Signing in rotates the token.

This runs as middleware before any route, so no module can forget it, and a refused upload is
answered before its body is read.
"""
import hmac
import re
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

COOKIE = "coji_csrf"
HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
FAILED = "驗證已過期，請重新整理後再試。"
YEAR = 60 * 60 * 24 * 365
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def token(request: Request, response: Response, *, secure: bool, rotate: bool = False) -> str:
    """The browser's token, made (or remade when rotating) and sent again so its year starts over."""
    value = None if rotate else request.cookies.get(COOKIE)
    if not value or not TOKEN.fullmatch(value):
        value = secrets.token_urlsafe(32)
    response.set_cookie(COOKIE, value, max_age=YEAR, path="/", samesite="lax", secure=secure)
    return value


def passes(request: Request, trusted_origins: tuple[str, ...]) -> bool:
    origin = request.headers.get("origin")
    if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host', '')}" \
            and origin not in trusted_origins:
        return False
    cookie, sent = request.cookies.get(COOKIE, ""), request.headers.get(HEADER, "")
    return bool(TOKEN.fullmatch(cookie)) and hmac.compare_digest(cookie, sent)


class CsrfMiddleware:
    def __init__(self, app, trusted_origins: tuple[str, ...]):
        self.app, self.trusted_origins = app, trusted_origins

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS and scope["path"].startswith("/api/"):
            if not passes(Request(scope), self.trusted_origins):
                await JSONResponse({"error": FAILED}, 403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
