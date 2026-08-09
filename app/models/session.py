"""
app.models.session
===================

SQLAlchemy ORM model for authentication sessions.

The SSO middleware (app.security.sso_middleware.SSOMiddleware) authenticates
requests and needs somewhere durable to record active session/token state,
including issuance and expiry timestamps, so that sessions can be
validated, audited, and revoked. This table backs that requirement.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthSession(Base):
    """Represents an issued authentication session/token for a user."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    session_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_session_token", "session_token", unique=True),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuthSession id={self.id} user_id={self.user_id!r} expires_at={self.expires_at}>"
