from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.models import User
from app.auth.permissions import can
from app.auth.service import resolve_session
from app.config import get_settings
from app.db import get_db
from app.envelope import AppError

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    resolved = resolve_session(db, token) if token else None
    if resolved is None:
        raise AppError("UNAUTHENTICATED", "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại", 401)
    return resolved[1]


def require(action: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_user)) -> User:
        if not can(user.role, action):
            raise AppError("FORBIDDEN", "Bạn không có quyền thực hiện thao tác này", 403)
        return user

    return dependency


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class CsrfMiddleware:
    """Từ chối request đổi trạng thái đến từ site khác (Sec-Fetch-Site / Origin)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            fetch_site = headers.get("sec-fetch-site")
            origin = headers.get("origin")
            allowed = _origin_of(get_settings().allowed_origin)
            if (fetch_site and fetch_site != "same-origin") or (origin and origin != allowed):
                body = (
                    b'{"success":false,"data":null,"error":{"code":"CSRF_REJECTED",'
                    b'"message":"Request bi tu choi (khac nguon)"},"meta":null}'
                )
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
