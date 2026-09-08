"""Unit tests for app.security.logging.

These tests exercise observable behaviour: log records actually emitted to
the configured handler, the shape/content of those records, and the
interaction between RecipeService-style validation failures and the
logging seam. They do not assert on file layout or source text.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.security.logging import (
    ACCESS_LOGGER_NAME,
    SECURITY_LOGGER_NAME,
    log_request,
    log_unhandled_exception,
    log_validation_failure,
    setup_logging,
)


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """Reset root logger handlers before/after each test for isolation."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    for h in original_handlers:
        root.removeHandler(h)
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in original_handlers:
        root.addHandler(h)
    root.setLevel(original_level)


class _ListHandler(logging.Handler):
    """Test handler capturing formatted JSON log records."""

    def __init__(self):
        super().__init__()
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        formatted = self.format(record)
        self.records.append(json.loads(formatted))


def test_setup_logging_configures_stdout_handler_and_is_idempotent():
    setup_logging()
    root = logging.getLogger()
    stream_handlers = [
        h for h in root.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) == 1

    # Calling again must not duplicate handlers.
    setup_logging()
    stream_handlers_after = [
        h for h in root.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers_after) == 1


def test_setup_logging_emits_startup_notice_about_sec001(capsys):
    setup_logging()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    payload_lines = [line for line in combined.splitlines() if line.strip()]
    assert any(
        "security_startup_notice" in line and "SEC-001" in line
        for line in payload_lines
    )


def test_log_validation_failure_emits_structured_record():
    setup_logging()
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    handler = _ListHandler()
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)

    log_validation_failure(
        field="name", reason="empty", value="'; DROP TABLE recipes; --"
    )

    assert len(handler.records) == 1
    record = handler.records[0]
    assert record["event"] == "validation_failure"
    assert record["field"] == "name"
    assert record["reason"] == "empty"
    assert "DROP TABLE" in record["value"]
    assert record["level"] == "WARNING"

    logger.removeHandler(handler)


def test_log_validation_failure_truncates_long_values():
    setup_logging()
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    handler = _ListHandler()
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(handler)

    long_value = "a" * 500
    log_validation_failure(field="ingredients", reason="too long", value=long_value)

    record = handler.records[0]
    assert len(record["value"]) < 500
    assert record["value"].endswith("<truncated>")

    logger.removeHandler(handler)


def test_log_unhandled_exception_includes_exception_metadata():
    setup_logging()
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    handler = _ListHandler()
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(handler)

    try:
        raise ValueError("boom")
    except ValueError as exc:
        log_unhandled_exception(context="test_context", exc=exc)

    record = handler.records[0]
    assert record["event"] == "unhandled_exception"
    assert record["context"] == "test_context"
    assert record["exception_type"] == "ValueError"
    assert record["exception_message"] == "boom"
    assert "exc_info" in record

    logger.removeHandler(handler)


def test_log_request_records_method_path_status_without_auth_context():
    setup_logging()
    logger = logging.getLogger(ACCESS_LOGGER_NAME)
    handler = _ListHandler()
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(handler)

    log_request(method="POST", path="/recipe", status_code=201, duration_ms=12.3)

    record = handler.records[0]
    assert record["method"] == "POST"
    assert record["path"] == "/recipe"
    assert record["status_code"] == 201
    assert record["duration_ms"] == 12.3
    assert record["authenticated"] is False

    logger.removeHandler(handler)


def test_no_secrets_logged_in_validation_failure():
    """Regression guard: ensure helper never adds password/token/secret keys."""
    setup_logging()
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    handler = _ListHandler()
    handler.setFormatter(logging.getLogger().handlers[0].formatter)
    logger.addHandler(handler)

    log_validation_failure(field="name", reason="empty", value="<script>alert(1)</script>")

    record = handler.records[0]
    forbidden_keys = {"password", "secret", "token"}
    assert forbidden_keys.isdisjoint(record.keys())

    logger.removeHandler(handler)
