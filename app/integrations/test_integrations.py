"""Integration tests for app.integrations templates and static file serving."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.static import mount_static
from app.integrations.templates import templates


def test_static_stylesheet_is_served() -> None:
    app = FastAPI()
    mount_static(app)
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "focus-visible" in response.text
    assert "@media (max-width: 600px)" in response.text


def test_templates_seam_points_at_web_templates_dir() -> None:
    # The templates seam should be configured to look in app/web/templates,
    # which is owned by the frontend task. We don't render any page here -
    # rendering pages is not this component's job - we just verify the
    # environment is wired to the correct directory.
    loader = templates.env.loader
    assert loader is not None
    search_path = str(loader.searchpath[0]) if hasattr(loader, "searchpath") else ""
    assert search_path.endswith(("web/templates", "web\\templates"))
