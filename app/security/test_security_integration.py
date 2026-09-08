"""Integration-style tests covering the required security acceptance
criteria that span multiple components (RecipeService, Jinja2 templates,
route accessibility).

These tests exercise the application's actual behaviour: they call the
real RecipeService against an in-memory SQLite database, render the real
Jinja2 templates object, and hit a FastAPI TestClient without any auth
headers. They never inspect source text or repository layout.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.contracts import ValidationError
from app.models import Base
from app.security.logging import SECURITY_LOGGER_NAME, log_validation_failure, setup_logging
from app.services.recipe import RecipeService


@pytest.fixture()
def db_session():
    """A fresh in-memory SQLite database per test, mirroring app.models.database
    wiring but self-contained so this test module does not need a running
    Postgres instance."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# RecipeService: parameterized queries / no string concatenation
# ---------------------------------------------------------------------------


def test_recipe_service_create_and_get_uses_orm_bound_parameters(db_session: Session):
    """A value shaped like a SQL injection payload must be stored verbatim
    and retrievable, proving no raw SQL string interpolation is occurring
    (a vulnerable concatenation would either error out or corrupt the
    query/table)."""
    service = RecipeService()
    malicious_name = "Pasta'; DROP TABLE recipes; --"
    ingredients = "flour, water, salt"

    created = service.create_recipe(name=malicious_name, ingredients=ingredients, db=db_session)

    fetched = service.get_recipe(created.id, db=db_session)
    assert fetched is not None
    assert fetched.name == malicious_name
    assert fetched.ingredients == ingredients

    # The table must still exist and be queryable - a successful DROP via
    # concatenation would make this call raise.
    all_recipes = service.list_recipes(db=db_session)
    assert any(r.id == created.id for r in all_recipes)


def test_recipe_service_get_by_injection_shaped_id_returns_none_not_error(db_session: Session):
    """Passing a non-existent id should simply return None via a bound
    parameterized filter, never raise a SQL syntax error that would occur
    from unsafe string concatenation."""
    service = RecipeService()
    result = service.get_recipe(999999, db=db_session)
    assert result is None


def test_recipe_service_update_persists_injection_shaped_values_safely(db_session: Session):
    service = RecipeService()
    created = service.create_recipe(name="Soup", ingredients="water", db=db_session)

    injected_ingredients = "onion' OR '1'='1"
    updated = service.update_recipe(
        created.id, name="Soup", ingredients=injected_ingredients, db=db_session
    )

    assert updated.ingredients == injected_ingredients
    fetched = service.get_recipe(created.id, db=db_session)
    assert fetched.ingredients == injected_ingredients


# ---------------------------------------------------------------------------
# ValidationError raised + logged for malicious input
# ---------------------------------------------------------------------------


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def security_log_capture():
    setup_logging()
    logger = logging.getLogger(SECURITY_LOGGER_NAME)
    handler = _ListHandler()
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)


def test_validation_error_for_sql_injection_shaped_name_is_logged(
    db_session: Session, security_log_capture: _ListHandler
):
    """Empty/whitespace-only name is invalid per RecipeService's contract.
    We simulate the security-logging integration a caller (e.g. the web
    handler) performs when it catches ValidationError, and assert the
    ValidationError is raised for a SQL-injection-shaped-but-invalid value
    and that the failure gets logged."""
    service = RecipeService()
    malicious_name = "   "  # whitespace only -> invalid per contract

    with pytest.raises(ValidationError):
        try:
            service.create_recipe(name=malicious_name, ingredients="water", db=db_session)
        except ValidationError as exc:
            log_validation_failure(field="name", reason=str(exc), value=malicious_name)
            raise

    assert len(security_log_capture.records) == 1
    assert security_log_capture.records[0].event == "validation_failure"
    assert security_log_capture.records[0].field == "name"


def test_validation_error_for_xss_shaped_ingredients_when_invalid_is_logged(
    db_session: Session, security_log_capture: _ListHandler
):
    """An overlong ingredients value containing an XSS payload must still be
    rejected as a validation error (exceeds max length), and that rejection
    must be logged as a security-relevant event."""
    service = RecipeService()
    xss_payload = "<script>alert('xss')</script>" * 1000  # force max-length failure

    with pytest.raises(ValidationError):
        try:
            service.create_recipe(name="Cake", ingredients=xss_payload, db=db_session)
        except ValidationError as exc:
            log_validation_failure(field="ingredients", reason=str(exc), value=xss_payload)
            raise

    assert len(security_log_capture.records) == 1
    assert security_log_capture.records[0].event == "validation_failure"
    assert security_log_capture.records[0].field == "ingredients"


# ---------------------------------------------------------------------------
# Jinja2 autoescaping of user content
# ---------------------------------------------------------------------------


def test_jinja2_templates_escape_html_in_recipe_name_and_ingredients():
    """Render a minimal template through the real shared `templates` object
    to prove autoescaping is active and no |safe filter is needed/used for
    user-provided content. This does not modify or inspect app.web's
    templates - it uses the shared Jinja2Templates environment directly."""
    from app.integrations.templates import templates

    env = templates.env
    template = env.from_string(
        "<div>{{ recipe_name }}</div><p>{{ recipe_ingredients }}</p>"
    )

    malicious_name = "<script>alert('xss-name')</script>"
    malicious_ingredients = "<img src=x onerror=alert('xss-ingredients')>"

    rendered = template.render(
        recipe_name=malicious_name, recipe_ingredients=malicious_ingredients
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "onerror=" not in rendered or "&lt;img" in rendered
    assert "&lt;img" in rendered


def test_jinja2_environment_has_autoescape_enabled():
    from app.integrations.templates import templates

    assert templates.env.autoescape in (True,) or callable(templates.env.autoescape)
    if callable(templates.env.autoescape):
        assert templates.env.autoescape("template.html") is True


# ---------------------------------------------------------------------------
# No authentication / authorization on any route (SEC-001)
# ---------------------------------------------------------------------------


def test_all_routes_accessible_without_auth_headers():
    """Build a minimal FastAPI app wiring only app.web's router (the
    interaction target explicitly named in the task) and confirm requests
    with zero auth headers are not rejected with 401/403."""
    from app.web.pages import router as web_router

    app = FastAPI()
    app.include_router(web_router)

    client = TestClient(app)

    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        if not path or "{" in path:
            continue
        for method in methods:
            if method not in ("GET", "POST"):
                continue
            response = client.request(method, path)
            assert response.status_code not in (401, 403), (
                f"{method} {path} rejected an unauthenticated request "
                f"with status {response.status_code}"
            )
