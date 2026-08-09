"""
TLS / HTTPS enforcement configuration.

This module provides middleware and configuration helpers to:
- Enforce HTTPS by redirecting plain HTTP requests (when enabled).
- Set the `Strict-Transport-Security` (HSTS) header on all responses.

TLS termination itself is expected to be handled by the deployment's
load balancer / ingress / reverse proxy. This module enforces the
application-level policy: reject/redirect insecure traffic and instruct
browsers to always use HTTPS going forward via HSTS.

Configuration is externalized via environment variables (never
hardcoded), per engineering standards:

- `ENFORCE_HTTPS` (default: "true") - whether to redirect HTTP -> HTTPS.
- `HSTS_MAX_AGE` (default: "31536000" i.e. 1 year) - max-age directive.
- `HSTS_INCLUDE_SUBDOMAINS` (default: "true").
- `HSTS_PRELOAD` (default: "false").
- `TRUSTED_PROXY_HEADER` (default: "X-Forwarded-Proto") - header used to
  detect the original scheme when running behind a TLS-terminating proxy.
"""

import logging
import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

logger = logging.getLogger("app.security.tls")


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: str) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


class TLSConfig:
    """
    Holds TLS / HSTS enforcement settings loaded from environment
    variables at construction time.
    """

    def __init__(self) -> None:
        self.enforce_https: bool = _env_bool("ENFORCE_HTTPS", "true")
        self.hsts_max_age: int = _env_int("HSTS_MAX_AGE", "31536000")
        self.hsts_include_subdomains: bool = _env_bool(
            "HSTS_INCLUDE_SUBDOMAINS", "true"
        )
        self.hsts_preload: bool = _env_bool("HSTS_PRELOAD", "false")
        self.trusted_proxy_header: str = os.environ.get(
            "TRUSTED_PROXY_HEADER", "X-Forwarded-Proto"
        )

    def build_hsts_header_value(self) -> str:
        """Build the Strict-Transport-Security header value from config."""
        parts = [f"max-age={self.hsts_max_age}"]
        if self.hsts_include_subdomains:
            parts.append("includeSubDomains")
        if self.hsts_preload:
            parts.append("preload")
        return "; ".join(parts)


class HTTPSEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces HTTPS and sets HSTS headers.

    Behavior:
    - If `enforce_https` is True and the request scheme (accounting for
      the trusted proxy header, since TLS is typically terminated
      upstream) is not `https`, the request is redirected (HTTP 307) to
      the equivalent HTTPS URL.
    - On every response (including redirects), the
      `Strict-Transport-Security` header is set per configuration.
    """

    def __init__(self, app, config: TLSConfig = None) -> None:
        super().__init__(app)
        self._config = config or TLSConfig()

    def _is_secure(self, request: Request) -> bool:
        forwarded_proto = request.headers.get(self._config.trusted_proxy_header)
        if forwarded_proto:
            return forwarded_proto.split(",")[0].strip().lower() == "https"
        return request.url.scheme == "https"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if self._config.enforce_https and not self._is_secure(request):
            https_url = request.url.replace(scheme="https")
            logger.warning(
                "insecure_request_redirected",
                extra={
                    "event": "insecure_request_redirected",
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            response: Response = RedirectResponse(url=str(https_url), status_code=307)
        else:
            response = await call_next(request)

        response.headers["Strict-Transport-Security"] = (
            self._config.build_hsts_header_value()
        )
        return response


def get_tls_config() -> TLSConfig:
    """Factory returning a fresh TLSConfig loaded from the environment."""
    return TLSConfig()
