"""
SSO authentication middleware for enterprise Single Sign-On integration.

This middleware extracts the authenticated user's identity from an
enterprise SSO reverse-proxy header (`X-SSO-User`) and injects it into
the request's state so downstream handlers/services can rely on
`request.state.user_id` without re-implementing authentication logic.

Security notes:
- This middleware assumes the enterprise SSO gateway/reverse proxy is
  the only component permitted to set the `X-SSO-User` header and that
  network-layer controls prevent clients from spoofing it directly
  (e.g. the header is stripped/overwritten at the edge proxy). This is
  a standard pattern for enterprise SSO integrations (e.g. SiteMinder,
  Shibboleth, corporate API gateways).
- Requests without a valid header are rejected with 401 Unauthorized.
- All authentication events (success/failure) are logged with user
  context for audit purposes, without logging secrets or tokens.
"""

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("app.security.sso")

SSO_HEADER_NAME = "X-SSO-User"

# Paths that do not require SSO authentication (health checks, docs, etc.)
DEFAULT_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/healthz",
        "/readyz",
        "/livez",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    }
)


class SSOMiddleware(BaseHTTPMiddleware):
    """
    Starlette/FastAPI middleware that enforces enterprise SSO authentication.

    On each request, it looks for the `X-SSO-User` header (set by the
    enterprise SSO gateway) and, if present and non-empty, injects the
    user id into `request.state.user_id`. If the header is missing or
    empty, the request is rejected with HTTP 401 Unauthorized, unless
    the request path is in the exempt list (e.g. health checks).
    """

    def __init__(self, app, exempt_paths: frozenset = DEFAULT_EXEMPT_PATHS) -> None:
        super().__init__(app)
        self._exempt_paths = exempt_paths

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ):
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        user_id = request.headers.get(SSO_HEADER_NAME)

        if not user_id or not user_id.strip():
            logger.warning(
                "sso_auth_failed",
                extra={
                    "event": "sso_auth_failed",
                    "path": request.url.path,
                    "method": request.method,
                    "reason": "missing_or_empty_sso_header",
                },
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: missing or invalid SSO credentials"},
            )

        user_id = user_id.strip()
        request.state.user_id = user_id

        logger.info(
            "sso_auth_success",
            extra={
                "event": "sso_auth_success",
                "path": request.url.path,
                "method": request.method,
                "user_id": user_id,
            },
        )

        return await call_next(request)

    @staticmethod
    def get_current_user(request: Request) -> str:
        """
        Extract the authenticated user id from the current request.

        Returns the `user_id` injected by this middleware into
        `request.state`. Raises a ValueError if the middleware has not
        run or the user could not be authenticated -- callers in HTTP
        contexts should prefer catching this and translating to a 401.

        Args:
            request: The incoming Starlette/FastAPI request.

        Returns:
            The authenticated user's id.

        Raises:
            ValueError: if no authenticated user is present on the request.
        """
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            logger.warning(
                "sso_get_current_user_failed",
                extra={
                    "event": "sso_get_current_user_failed",
                    "path": str(request.url.path) if request.url else "unknown",
                    "reason": "no_authenticated_user_in_request_state",
                },
            )
            raise ValueError("No authenticated user found on request")
        return user_id
