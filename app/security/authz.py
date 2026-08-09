"""
Ownership-based authorization utilities.

This module provides a single source of truth for verifying that a
requesting user is authorized to perform mutating operations (edit,
delete) on a resource, based on strict owner_id equality.

All authorization decisions are logged with user context for audit
purposes (never logging secrets or tokens).
"""

import logging

from starlette.requests import Request

from app.security.sso_middleware import SSOMiddleware

logger = logging.getLogger("app.security.authz")


def get_current_user(request: Request) -> str:
    """
    Retrieve the authenticated user id from the current request.

    This delegates to the SSO middleware's extraction logic so there is
    a single source of truth for "who is the current user" across the
    application.

    Args:
        request: The incoming Starlette/FastAPI request.

    Returns:
        The authenticated user's id.

    Raises:
        ValueError: if no authenticated user is present on the request.
    """
    return SSOMiddleware.get_current_user(request)


def verify_ownership(resource_owner_id: str, requesting_user_id: str) -> bool:
    """
    Verify that the requesting user owns the resource in question.

    This is the sole authorization rule for edit/delete operations on
    recipes: only the resource's owner may mutate it.

    Args:
        resource_owner_id: The `owner_id` recorded on the target resource.
        requesting_user_id: The id of the user making the request.

    Returns:
        True if `requesting_user_id` matches `resource_owner_id` exactly
        (non-empty), False otherwise.
    """
    is_authorized = bool(
        resource_owner_id
        and requesting_user_id
        and resource_owner_id == requesting_user_id
    )

    if is_authorized:
        logger.info(
            "authz_check_granted",
            extra={
                "event": "authz_check_granted",
                "requesting_user_id": requesting_user_id,
                "resource_owner_id": resource_owner_id,
            },
        )
    else:
        logger.warning(
            "authz_check_denied",
            extra={
                "event": "authz_check_denied",
                "requesting_user_id": requesting_user_id,
                "resource_owner_id": resource_owner_id,
            },
        )

    return is_authorized
