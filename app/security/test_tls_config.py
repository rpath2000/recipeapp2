"""Unit tests for app.security.tls_config."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.tls_config import HTTPSEnforcementMiddleware, TLSConfig


def _build_app(config: TLSConfig = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(HTTPSEnforcementMiddleware, config=config)

    @app.get("/secure-endpoint")
    def secure_endpoint():
        return {"status": "ok"}

    return app


def test_hsts_header_present_on_https_request() -> None:
    """HSTS header should be present on responses served over HTTPS."""
    config = TLSConfig()
    config.enforce_https = False  # avoid redirect complications in test client
    app = _build_app(config)
    client = TestClient(app, base_url="https://testserver")
    response = client.get("/secure-endpoint")
    assert response.status_code == 200
    assert "Strict-Transport-Security" in response.headers
    assert "max-age=" in response.headers["Strict-Transport-Security"]


def test_http_request_redirected_when_enforced() -> None:
    """HTTP requests should be redirected to HTTPS when enforcement is on."""
    config = TLSConfig()
    config.enforce_https = True
    app = _build_app(config)
    client = TestClient(app, base_url="http://testserver")
    response = client.get("/secure-endpoint", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")


def test_hsts_header_uses_configured_directives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HSTS header should reflect configured max-age and directives."""
    monkeypatch.setenv("HSTS_MAX_AGE", "12345")
    monkeypatch.setenv("HSTS_INCLUDE_SUBDOMAINS", "true")
    monkeypatch.setenv("HSTS_PRELOAD", "true")
    monkeypatch.setenv("ENFORCE_HTTPS", "false")
    config = TLSConfig()
    app = _build_app(config)
    client = TestClient(app, base_url="https://testserver")
    response = client.get("/secure-endpoint")
    header_value = response.headers["Strict-Transport-Security"]
    assert "max-age=12345" in header_value
    assert "includeSubDomains" in header_value
    assert "preload" in header_value


def test_forwarded_proto_https_is_treated_as_secure() -> None:
    """X-Forwarded-Proto: https should be treated as a secure request."""
    config = TLSConfig()
    config.enforce_https = True
    app = _build_app(config)
    client = TestClient(app, base_url="http://testserver")
    response = client.get(
        "/secure-endpoint", headers={"X-Forwarded-Proto": "https"}
    )
    assert response.status_code == 200
