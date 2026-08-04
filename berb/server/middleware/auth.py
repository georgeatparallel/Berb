"""Basic token authentication middleware."""

from __future__ import annotations

import hmac
from urllib.parse import parse_qs

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class TokenAuthMiddleware:
    """Optional bearer-token authentication.

    Pure ASGI middleware — not ``BaseHTTPMiddleware``. Starlette only routes
    ``scope["type"] == "http"`` through ``BaseHTTPMiddleware``, which silently
    let every WebSocket connection through unauthenticated even when a token
    was configured. Implementing ``__call__`` directly lets this middleware
    see and reject "websocket" scopes too.

    If *token* is empty, all requests are allowed (no-op).
    """

    # Paths that never require auth. /docs and /openapi.json are deliberately
    # NOT exempt: they expose the full API surface and must be gated like any
    # other route when a token is configured.
    EXEMPT_PATHS = frozenset({"/api/health"})

    def __init__(self, app: ASGIApp, token: str = "") -> None:
        self.app = app
        self._token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not self._token:
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in self.EXEMPT_PATHS or path.startswith("/static"):
            await self.app(scope, receive, send)
            return

        token = self._extract_token(scope)
        if hmac.compare_digest(token, self._token):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await self._reject_websocket(receive, send)
        else:
            await self._reject_http(scope, receive, send)

    @staticmethod
    def _extract_token(scope: Scope) -> str:
        if scope["type"] == "websocket":
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            return query.get("token", [""])[0]
        headers = dict(scope.get("headers") or ())
        auth_header = headers.get(b"authorization", b"").decode("latin-1")
        return auth_header.removeprefix("Bearer ").strip()

    @staticmethod
    async def _reject_websocket(receive: Receive, send: Send) -> None:
        # Per the ASGI websocket protocol, the handshake's "websocket.connect"
        # message must be consumed before the connection can be closed.
        message = await receive()
        if message["type"] == "websocket.connect":
            await send({"type": "websocket.close", "code": 4401})

    @staticmethod
    async def _reject_http(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
        await response(scope, receive, send)
