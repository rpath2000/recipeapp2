"""
app.models.password_reset_token
=================================

SQLAlchemy ORM model for password reset / email verification tokens.

Supports password-reset and verification style requirements implied by an
authenticated multi-user application: a single-use, time-bounded token tied
to a user, recorded so it can be validated and invalidated after use.
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


class PasswordResetToken(Base):
    """Single-use token issued for password reset / verification flows."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
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
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
        Index("ix_password_reset_tokens_token", "token", unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PasswordResetToken id={self.id} user_id={self.user_id!r} used={self.used}>"
