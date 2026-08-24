"""Persistence for accounts.

The address a person types is kept as they typed it, and a normalised copy
carries the uniqueness constraint, so `Ada@Example.com` and `ada@example.com`
cannot both register.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base

EMAIL_LENGTH = 320
HASH_LENGTH = 255


def normalize_email(value: str) -> str:
    """The form uniqueness is enforced on."""
    return value.strip().lower()


class User(Base):
    """One account. Owns a profile, CVs, and sessions."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("normalized_email", name="uq_users_normalized_email"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(EMAIL_LENGTH), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(EMAIL_LENGTH), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Bumped to end every session at once. Normal logout clears the cookie and
    # leaves this alone; a password change, a disabled account, or an explicit
    # log-out-everywhere increments it and invalidates tokens already issued.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @validates("email")
    def derive_normalized_email(self, _key: str, email: str) -> str:
        self.normalized_email = normalize_email(email)
        return email
