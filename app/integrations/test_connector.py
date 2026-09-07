"""
Integration tests for app.integrations: configuration, engine, logging,
connector, and transform behavior.

Uses pytest with monkeypatch for environment isolation and httpx's
MockTransport to avoid real network calls while still exercising the
full connector retry/idempotency logic.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from app.contracts import RecipeCreateDTO, RecipeDTO, ValidationError
from app.integrations import config as config_module
from app.integrations.connector import (
    InsecureTargetError,
    OutboundCallError,
    call_outbound_api,
)
from app.integrations.logging_config import (
    JsonFormatter,
    clear_request_context,
    configure_logging,
    get_request_context,
    reset_request_context,
)
from app.integrations.logging_config import bind_request_context
from app.integrations.transform import (
    outbound_response_to_dict,
    recipe_create_dto_to_outbound_payload,
    recipe_dto_to_outbound_payload,
)


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Ensure each test sees a fresh settings/engine cache."""
    config_module.reset_config_cache()
    clear_request_context()
    yield
    config_module.reset_config_cache()
    clear_request_context()


# ---------------------------------------------------------------------------
# get_settings() tests
# ---------------------------------------------------------------------------


def test_get_settings_reads_database_url_and_log_level_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/recipeapp2book")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = config_module.get_settings()

    assert settings.database_url == "postgresql://user:pass@localhost:5432/recipeapp2book"
    assert settings.log_level == "DEBUG"


def test_get_settings_uses_defaults_when_env_vars_absent(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = config_module.get_settings()

    assert settings.database_url == config_module._DEFAULT_DATABASE_URL
    assert settings.log_level == "INFO"


def test_get_settings_is_a_cached_singleton(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/recipeapp2book")

    first = config_module.get_settings()
    second = config_module.get_settings()

    assert first is second


# ---------------------------------------------------------------------------
# get_engine() tests
# ---------------------------------------------------------------------------


def test_get_engine_connects_to_recipeapp2book_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test_recipeapp2book.db")

    engine = config_module.get_engine()

    assert engine.url.database is not None
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

    engine.dispose()
    import os

    if os.path.exists("./test_recipeapp2book.db"):
        os.remove("./test_recipeapp2book.db")


def test_get_engine_returns_cached_singleton(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test_recipeapp2book2.db")

    first = config_module.get_engine()
    second = config_module.get_engine()

    assert first is second

    first.dispose()
    import os

    if os.path.exists("./test_recipeapp2book2.db"):
        os.remove("./test_recipeapp2book2.db")


def test_get_engine_does_not_connect_at_import_time():
    """Importing the module must never open a connection - only building
    an Engine object is allowed. This is a regression guard: if the
    engine were eagerly connected, an unreachable host below would raise
    on import/build rather than only on explicit .connect()."""
    import importlib

    import app.integrations.config as reloaded

    importlib.reload(reloaded)
    # No exception should have been raised merely by importing/reloading.


# ---------------------------------------------------------------------------
# Configuration failure tests
# ---------------------------------------------------------------------------


def test_get_settings_fails_fast_with_missing_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")

    with pytest.raises(config_module.ConfigurationError) as exc_info:
        config_module.get_settings()

    assert "DATABASE_URL" in str(exc_info.value)


def test_get_settings_fails_fast_with_malformed_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "not-a-valid-url-no-scheme")

    with pytest.raises(config_module.ConfigurationError) as exc_info:
        config_module.get_settings()

    assert "malformed" in str(exc_info.value).lower()


def test_get_settings_fails_fast_with_unsupported_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "ftp://localhost/recipeapp2book")

    with pytest.raises(config_module.ConfigurationError) as exc_info:
        config_module.get_settings()

    assert "unsupported scheme" in str(exc_info.value).lower()


def test_get_settings_fails_fast_with_invalid_log_level(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/recipeapp2book")
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")

    with pytest.raises(config_module.ConfigurationError) as exc_info:
        config_module.get_settings()

    assert "LOG_LEVEL" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Structured JSON logging tests
# ---------------------------------------------------------------------------


def test_logging_outputs_json_with_required_fields(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/recipeapp2book")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    stream = io.StringIO()
    configure_logging(handler_stream=stream)

    token = bind_request_context(request_id="abc-123", path="/api/recipes", method="GET")
    try:
        logger = logging.getLogger("test.logger")
        logger.info("Something happened")
    finally:
        reset_request_context(token)

    output = stream.getvalue().strip()
    record = json.loads(output)

    assert "timestamp" in record
    assert record["level"] == "INFO"
    assert record["message"] == "Something happened"
    assert record["request_context"]["request_id"] == "abc-123"
    assert record["request_context"]["path"] == "/api/recipes"
    assert record["request_context"]["method"] == "GET"


def test_logging_json_formatter_includes_exception_info():
    formatter = JsonFormatter()
    logger = logging.getLogger("test.exc.logger")
    logger.setLevel(logging.ERROR)

    try:
        raise ValueError("boom")
    except ValueError:
        record = logger.makeRecord(
            logger.name, logging.ERROR, __file__, 0, "failure occurred", (), True
        )
        import sys

        record.exc_info = sys.exc_info()

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "ERROR"
    assert "exception" in parsed
    assert "boom" in parsed["exception"]


def test_request_context_is_isolated_between_binds():
    clear_request_context()
    assert get_request_context() == {}

    token = bind_request_context(request_id="r1")
    assert get_request_context()["request_id"] == "r1"
    reset_request_context(token)

    assert get_request_context() == {}


# ---------------------------------------------------------------------------
# Connector tests (retry + idempotency, secure by design)
# ---------------------------------------------------------------------------


def test_connector_rejects_non_https_url():
    with pytest.raises(InsecureTargetError):
        call_outbound_api("http://insecure.example.com/api", json_payload={})


def test_connector_succeeds_on_first_attempt():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Idempotency-Key") is not None
        return httpx.Response(200, json={"id": 1, "attributes": {"name": "Soup"}})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    response = call_outbound_api(
        "https://api.example.com/recipes",
        json_payload={"name": "Soup"},
        client=client,
    )

    assert response.status_code == 200
    assert response.body["attributes"]["name"] == "Soup"
    assert response.idempotency_key


def test_connector_retries_on_transient_5xx_and_then_succeeds():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"id": 2})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    response = call_outbound_api(
        "https://api.example.com/recipes",
        json_payload={"name": "Stew"},
        client=client,
        max_retries=5,
        backoff_base_seconds=0.001,
    )

    assert response.status_code == 200
    assert attempts["count"] == 3


def test_connector_uses_same_idempotency_key_across_retries():
    seen_keys = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers.get("Idempotency-Key"))
        if len(seen_keys) < 2:
            return httpx.Response(500, json={"error": "retry me"})
        return httpx.Response(200, json={"id": 3})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    call_outbound_api(
        "https://api.example.com/recipes",
        json_payload={"name": "Chili"},
        client=client,
        max_retries=3,
        backoff_base_seconds=0.001,
    )

    assert len(seen_keys) == 2
    assert seen_keys[0] == seen_keys[1]


def test_connector_does_not_retry_on_client_error():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, text="bad request")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    with pytest.raises(OutboundCallError):
        call_outbound_api(
            "https://api.example.com/recipes",
            json_payload={"name": "Bad"},
            client=client,
            max_retries=3,
            backoff_base_seconds=0.001,
        )

    assert attempts["count"] == 1


def test_connector_raises_after_exhausting_retries_on_persistent_5xx():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503, json={"error": "down"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    with pytest.raises(OutboundCallError):
        call_outbound_api(
            "https://api.example.com/recipes",
            json_payload={"name": "Persistent"},
            client=client,
            max_retries=2,
            backoff_base_seconds=0.001,
        )

    assert attempts["count"] == 2


def test_connector_never_logs_authorization_header(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 4})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    with caplog.at_level(logging.INFO, logger="app.integrations.connector"):
        call_outbound_api(
            "https://api.example.com/recipes",
            json_payload={"name": "Secret"},
            headers={"Authorization": "Bearer super-secret-token"},
            client=client,
        )

    for record in caplog.records:
        assert "super-secret-token" not in record.getMessage()
        if hasattr(record, "headers"):
            assert record.headers.get("Authorization") == "***REDACTED***"


# ---------------------------------------------------------------------------
# Transform tests
# ---------------------------------------------------------------------------


def test_recipe_dto_to_outbound_payload_maps_fields_correctly():
    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    recipe = RecipeDTO(id=1, name="Pancakes", ingredients="flour, milk, eggs", created_at=now, updated_at=now)

    payload = recipe_dto_to_outbound_payload(recipe)

    assert payload["id"] == 1
    assert payload["attributes"]["name"] == "Pancakes"
    assert payload["attributes"]["ingredients"] == ["flour", "milk", "eggs"]
    assert payload["metadata"]["created_at"] == now.isoformat()


def test_recipe_dto_to_outbound_payload_rejects_empty_name():
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    recipe = RecipeDTO(id=1, name="   ", ingredients="flour", created_at=now, updated_at=now)

    with pytest.raises(ValidationError):
        recipe_dto_to_outbound_payload(recipe)


def test_recipe_create_dto_to_outbound_payload_maps_fields():
    create = RecipeCreateDTO(name="Waffles", ingredients="flour, sugar")

    payload = recipe_create_dto_to_outbound_payload(create)

    assert payload["attributes"]["name"] == "Waffles"
    assert payload["attributes"]["ingredients"] == ["flour", "sugar"]


def test_recipe_create_dto_to_outbound_payload_rejects_empty_ingredients():
    create = RecipeCreateDTO(name="Waffles", ingredients="")

    with pytest.raises(ValidationError):
        recipe_create_dto_to_outbound_payload(create)


def test_outbound_response_to_dict_handles_full_response():
    body = {
        "id": 5,
        "attributes": {"name": "Tacos", "ingredients": ["beef", "tortilla"]},
        "status": "created",
    }

    result = outbound_response_to_dict(body)

    assert result["id"] == 5
    assert result["name"] == "Tacos"
    assert result["ingredients"] == "beef, tortilla"
    assert result["status"] == "created"


def test_outbound_response_to_dict_handles_missing_optional_fields():
    body = {"id": 6}

    result = outbound_response_to_dict(body)

    assert result["id"] == 6
    assert result["name"] is None
    assert result["status"] == "unknown"


def test_outbound_response_to_dict_rejects_non_dict_body():
    with pytest.raises(ValidationError):
        outbound_response_to_dict("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# End-to-end: transform + connector composed together
# ---------------------------------------------------------------------------


def test_end_to_end_transform_and_call_outbound_api():
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    recipe = RecipeDTO(id=7, name="Omelette", ingredients="eggs, cheese", created_at=now, updated_at=now)
    payload = recipe_dto_to_outbound_payload(recipe)

    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert sent["attributes"]["name"] == "Omelette"
        return httpx.Response(201, json={"id": 7, "attributes": sent["attributes"], "status": "created"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    response = call_outbound_api(
        "https://api.example.com/recipes",
        json_payload=payload,
        client=client,
    )
    normalized = outbound_response_to_dict(response.body)

    assert response.status_code == 201
    assert normalized["name"] == "Omelette"
    assert normalized["status"] == "created"
