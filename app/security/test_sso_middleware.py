"""Unit tests for app.security.sso_middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.sso_middleware import SSO_HEADER_NAME, SSOMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SSOMiddleware)

    @app.get("/whoami")
    def whoami(request):
        from app.security.sso_middleware import SSOMiddleware as _SSO

        user_id = _SSO.get_current_user(request)
        return {"user_id": user_id}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


def test_valid_sso_header_injects_user_id(client: TestClient) -> None:
    """A valid X-SSO-User header should inject the user id into the request."""
    response = client.get("/whoami", headers={SSO_HEADER_NAME: "user-123"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}


def test_missing_sso_header_returns_401(client: TestClient) -> None:
    """Requests without the SSO header should be rejected with 401."""
    response = client.get("/whoami")
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]


def test_empty_sso_header_returns_401(client: TestClient) -> None:
    """An empty/whitespace-only SSO header should also be rejected."""
    response = client.get("/whoami", headers={SSO_HEADER_NAME: "   "})
    assert response.status_code == 401


def test_exempt_path_does_not_require_sso_header(client: TestClient) -> None:
    """Exempt paths such as /health should not require authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_current_user_raises_when_not_authenticated() -> None:
    """get_current_user should raise if middleware never ran / no user set."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "query_string": b"",
        "client": ("test", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    with pytest.raises(ValueError):
        SSOMiddleware.get_current_user(request)
