"""
app.models.audit_log
======================

SQLAlchemy ORM model for audit logging.

Provides traceability for security-sensitive and destructive operations
(create/update/delete of recipes, ownership checks, authentication events)
per the audit/traceability requirements of the universal engineering
standards.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Immutable record of an auditable action taken in the system."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    __table_args__ = (
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_resource_type_resource_id", "resource_type", "resource_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog id={self.id} action={self.action!r} resource={self.resource_type}:{self.resource_id}>"
