"""
Audit logging for recipe service operations.

Provides structured, correlated logging for create/update/delete operations
to satisfy compliance and traceability requirements. Never logs secrets,
tokens, or personal data beyond identifiers necessary for audit trails.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("app.audit")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | AUDIT | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_create(entity_type: str, entity_id: str, actor_id: str) -> None:
    """Record a creation event."""
    logger.info(
        "action=CREATE entity_type=%s entity_id=%s actor_id=%s ts=%s",
        entity_type,
        entity_id,
        actor_id,
        _timestamp(),
    )


def log_update(entity_type: str, entity_id: str, actor_id: str) -> None:
    """Record an update event."""
    logger.info(
        "action=UPDATE entity_type=%s entity_id=%s actor_id=%s ts=%s",
        entity_type,
        entity_id,
        actor_id,
        _timestamp(),
    )


def log_delete(entity_type: str, entity_id: str, actor_id: str) -> None:
    """Record a deletion event."""
    logger.info(
        "action=DELETE entity_type=%s entity_id=%s actor_id=%s ts=%s",
        entity_type,
        entity_id,
        actor_id,
        _timestamp(),
    )


def log_authorization_failure(
    entity_type: str,
    entity_id: str,
    actor_id: str,
    action: str,
    owner_id: Optional[str] = None,
) -> None:
    """Record an authorization failure event (no sensitive data)."""
    logger.info(
        "action=AUTH_DENIED attempted_action=%s entity_type=%s entity_id=%s "
        "actor_id=%s owner_id=%s ts=%s",
        action,
        entity_type,
        entity_id,
        actor_id,
        owner_id,
        _timestamp(),
    )
