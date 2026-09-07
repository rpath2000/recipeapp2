"""
Secure outbound HTTP connector with retry and idempotency support.

This connector is used for any outbound call this component needs to
make to external services. It:
- Enforces HTTPS-only targets (secure by design).
- Retries transient failures (5xx, timeouts, connection errors) with
  exponential backoff and jitter, but never retries 4xx client errors.
- Attaches an Idempotency-Key header so retried/duplicate calls are safe
  on the receiving end.
- Never logs secrets, tokens, or full authorization headers.
- Reads timeouts/retry settings from environment with safe defaults -
  no hardcoded URLs or credentials.

No network I/O happens at import time; everything is invoked lazily
inside call_outbound_api().
"""

from __future__ import annotations

import logging
import os
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from app.integrations.logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("OUTBOUND_HTTP_TIMEOUT_SECONDS", "10"))
_DEFAULT_MAX_RETRIES = int(os.environ.get("OUTBOUND_HTTP_MAX_RETRIES", "3"))
_DEFAULT_BACKOFF_BASE_SECONDS = float(
    os.environ.get("OUTBOUND_HTTP_BACKOFF_BASE_SECONDS", "0.5")
)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OutboundCallError(Exception):
    """Raised when an outbound call fails permanently (exhausted retries)."""


class InsecureTargetError(Exception):
    """Raised when the target URL does not use HTTPS."""


@dataclass(frozen=True)
class OutboundResponse:
    """Normalized response from an outbound call."""

    status_code: int
    body: dict[str, Any]
    idempotency_key: str


def _validate_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise InsecureTargetError(
            f"Refusing to call non-HTTPS URL: {url!r}. "
            "Outbound calls must use HTTPS."
        )


def _build_idempotency_key(explicit_key: str | None) -> str:
    return explicit_key if explicit_key else str(uuid.uuid4())


def _redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of headers with sensitive values redacted for logging."""
    redacted = {}
    sensitive = {"authorization", "api-key", "x-api-key", "cookie"}
    for key, value in headers.items():
        redacted[key] = "***REDACTED***" if key.lower() in sensitive else value
    return redacted


def _should_retry(status_code: int | None, exc: Exception | None) -> bool:
    if exc is not None:
        return True
    if status_code is not None and status_code in _RETRYABLE_STATUS_CODES:
        return True
    return False


def _sleep_backoff(attempt: int, base_seconds: float) -> None:
    delay = base_seconds * (2 ** (attempt - 1))
    jitter = random.uniform(0, base_seconds)
    time.sleep(delay + jitter)


def call_outbound_api(
    url: str,
    *,
    method: str = "POST",
    json_payload: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    idempotency_key: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    backoff_base_seconds: float = _DEFAULT_BACKOFF_BASE_SECONDS,
    client: httpx.Client | None = None,
) -> OutboundResponse:
    """Make a secure outbound HTTP call with retry and idempotency.

    Args:
        url: Target URL. Must be HTTPS.
        method: HTTP method, defaults to POST.
        json_payload: JSON-serializable request body.
        headers: Additional headers. Authorization/API keys allowed but
            never logged in plaintext.
        idempotency_key: Explicit idempotency key; a UUID4 is generated
            if not provided. The same key is reused across all retry
            attempts for a single logical call so the receiving service
            can safely deduplicate.
        timeout_seconds: Per-attempt request timeout.
        max_retries: Maximum number of attempts (including the first).
        backoff_base_seconds: Base delay for exponential backoff.
        client: Optional injected httpx.Client (used by tests); a new
            client is created and closed automatically if not provided.

    Returns:
        OutboundResponse with status_code, parsed JSON body, and the
        idempotency key used.

    Raises:
        InsecureTargetError: if url is not HTTPS.
        OutboundCallError: if all retry attempts are exhausted or a
            non-retryable client error (4xx other than 429) occurs.
    """
    _validate_https(url)

    key = _build_idempotency_key(idempotency_key)
    request_headers = dict(headers) if headers else {}
    request_headers["Idempotency-Key"] = key
    request_headers.setdefault("Content-Type", "application/json")

    owns_client = client is None
    active_client = client if client is not None else httpx.Client(timeout=timeout_seconds)

    last_exc: Exception | None = None
    last_status: int | None = None

    try:
        for attempt in range(1, max_retries + 1):
            logger.info(
                "Outbound call attempt",
                extra={
                    "attempt": attempt,
                    "max_retries": max_retries,
                    "method": method,
                    "url": url,
                    "idempotency_key": key,
                    "headers": _redact_headers(request_headers),
                },
            )
            try:
                response = active_client.request(
                    method,
                    url,
                    json=json_payload,
                    headers=request_headers,
                    timeout=timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.TransportError) as exc:
                last_exc = exc
                last_status = None
                logger.warning(
                    "Outbound call transport error",
                    extra={"attempt": attempt, "error": str(exc), "idempotency_key": key},
                )
                if attempt < max_retries:
                    _sleep_backoff(attempt, backoff_base_seconds)
                    continue
                break

            last_status = response.status_code
            last_exc = None

            if response.status_code < 400:
                try:
                    body = response.json() if response.content else {}
                except ValueError:
                    body = {}
                logger.info(
                    "Outbound call succeeded",
                    extra={"status_code": response.status_code, "idempotency_key": key},
                )
                return OutboundResponse(
                    status_code=response.status_code, body=body, idempotency_key=key
                )

            if not _should_retry(response.status_code, None):
                logger.error(
                    "Outbound call failed with non-retryable status",
                    extra={"status_code": response.status_code, "idempotency_key": key},
                )
                raise OutboundCallError(
                    f"Outbound call to {url!r} failed with non-retryable "
                    f"status {response.status_code}: {response.text[:500]}"
                )

            logger.warning(
                "Outbound call retryable status, will retry",
                extra={"attempt": attempt, "status_code": response.status_code},
            )
            if attempt < max_retries:
                _sleep_backoff(attempt, backoff_base_seconds)
                continue
            break
    finally:
        if owns_client:
            active_client.close()

    if last_exc is not None:
        raise OutboundCallError(
            f"Outbound call to {url!r} failed after {max_retries} attempts: {last_exc}"
        ) from last_exc

    raise OutboundCallError(
        f"Outbound call to {url!r} failed after {max_retries} attempts "
        f"with final status {last_status}."
    )
