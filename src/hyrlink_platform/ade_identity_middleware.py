"""ASGI identity boundary for HTTP applications; no untrusted proxy headers."""

import asyncio

from .contracts import PlatformError


class IdentityMiddleware:
    """Authenticate every HTTP request before the application receives it.

    The app must use only the principal injected at `ade.principal` and enforce
    tool/route permissions. This does not implement TLS, proxy trust, or sessions.
    Deploy behind an ingress that validates host and terminates TLS.
    """

    def __init__(self, app, boundary):
        self.app, self.boundary = app, boundary

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            raise RuntimeError("unsupported_scope")
        try:
            hosts = [v for k, v in scope.get("headers", []) if k.lower() == b"host"]
            credentials = [v for k, v in scope.get("headers", []) if k.lower() == b"authorization"]
            if len(hosts) != 1 or len(credentials) != 1:
                raise PlatformError("authentication_failed")
            host = hosts[0].decode("ascii")
            authorization = credentials[0].decode("ascii")
            principal = await asyncio.to_thread(self.boundary.authenticate, authorization, host)
        except (PlatformError, UnicodeError, AttributeError, TypeError):
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"cache-control", b"no-store"),
                                    (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        authenticated_scope = dict(scope)
        authenticated_scope["ade.principal"] = principal
        await self.app(authenticated_scope, receive, send)
