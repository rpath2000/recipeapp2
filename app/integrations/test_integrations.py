"""Integration tests for app.integrations templates and static file serving."""
from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.static import mount_static
from app.integrations.templates import templates


def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app wiring only this component's seams,
    plus small local routes that exercise template rendering, mirroring
    how app/web would call `templates.TemplateResponse`.
    """
    app = FastAPI()
    mount_static(app)

    @app.get("/test/dashboard")
    def _dashboard_page(request=None):
        from starlette.requests import Request

        # Fallback if request not injected by FastAPI dependency system
        raise NotImplementedError

    return app


def _make_app_with_routes() -> FastAPI:
    from starlette.requests import Request

    app = FastAPI()
    mount_static(app)

    @app.get("/test/dashboard")
    def dashboard_route(request: Request):
        recipes = [
            {
                "id": 1,
                "name": "Pancakes",
                "ingredients": "flour, milk, eggs",
                "created_at": datetime(2024, 1, 1, 12, 0, 0),
                "updated_at": datetime(2024, 1, 2, 12, 0, 0),
            }
        ]
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "recipes": recipes},
        )

    @app.get("/test/recipe-form")
    def recipe_form_route(request: Request):
        return templates.TemplateResponse(
            "recipe_form.html",
            {
                "request": request,
                "recipe": None,
                "errors": {"name": "Name is required."},
                "confirmation": "Recipe saved successfully.",
            },
        )

    return app


def test_dashboard_template_renders_with_context_data() -> None:
    app = _make_app_with_routes()
    client = TestClient(app)

    response = client.get("/test/dashboard")

    assert response.status_code == 200
    body = response.text
    assert "Pancakes" in body
    assert "flour, milk, eggs" in body
    assert '<th scope="col">' in body


def test_recipe_form_template_renders_with_context_data() -> None:
    app = _make_app_with_routes()
    client = TestClient(app)

    response = client.get("/test/recipe-form")

    assert response.status_code == 200
    body = response.text
    assert "Recipe saved successfully." in body
    assert 'aria-describedby="name-error"' in body
    assert 'aria-live="polite"' in body
    assert '<label for="name">' in body
    assert '<label for="ingredients">' in body


def test_base_template_includes_navigation_links() -> None:
    app = _make_app_with_routes()
    client = TestClient(app)

    response = client.get("/test/dashboard")

    assert response.status_code == 200
    body = response.text
    assert 'href="/dashboard"' in body
    assert 'href="/recipe"' in body


def test_static_stylesheet_is_served() -> None:
    app = _make_app_with_routes()
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "focus-visible" in response.text
    assert "@media (max-width: 600px)" in response.text


def test_dashboard_and_form_readable_at_narrow_viewport() -> None:
    """Verify the stylesheet defines responsive reflow and keyboard-focus
    styling that keep the dashboard table and recipe form usable on narrow
    viewports (structural/CSS assertions, since headless rendering is out
    of scope for this integration test)."""
    app = _make_app_with_routes()
    client = TestClient(app)

    css_response = client.get("/static/styles.css")
    assert css_response.status_code == 200
    css = css_response.text

    # Narrow viewport table reflow
    assert "thead tr" in css
    assert "display: block" in css

    # Form remains full-width and usable at narrow viewport
    assert "form {" in css or "form{" in css

    dashboard_response = client.get("/test/dashboard")
    assert dashboard_response.status_code == 200
    assert "<table>" in dashboard_response.text

    form_response = client.get("/test/recipe-form")
    assert form_response.status_code == 200
    assert '<input' in form_response.text
    assert '<textarea' in form_response.text
