"""Unit tests for app.security.authz."""

import pytest
from starlette.requests import Request

from app.security.authz import get_current_user, verify_ownership


def test_verify_ownership_passes_when_ids_match() -> None:
    """Authorization should succeed when requesting_user_id equals owner_id."""
    assert verify_ownership("user-1", "user-1") is True


def test_verify_ownership_fails_when_ids_differ() -> None:
    """Authorization should fail when requesting_user_id differs from owner_id."""
    assert verify_ownership("user-1", "user-2") is False


def test_verify_ownership_fails_on_empty_values() -> None:
    """Authorization should fail (not error) on empty owner or requester ids."""
    assert verify_ownership("", "user-1") is False
    assert verify_ownership("user-1", "") is False
    assert verify_ownership("", "") is False


def test_get_current_user_delegates_to_sso_middleware() -> None:
    """get_current_user should read the user id injected by SSOMiddleware."""
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
    request.state.user_id = "user-42"
    assert get_current_user(request) == "user-42"


def test_get_current_user_raises_without_authenticated_user() -> None:
    """get_current_user should raise ValueError if no user is present."""
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
        get_current_user(request)
