"""User-owned CV metadata.

Document bytes live behind the storage boundary. PostgreSQL keeps only the
ownership, integrity, location, and processing lifecycle needed to coordinate
that object.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.modules.accounts.models import User

STORAGE_KEY_LENGTH = 512
SHA256_HEX_LENGTH = 64
MEDIA_TYPE_LENGTH = 127


class CVProcessingState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


ALLOWED_STATE_TRANSITIONS: dict[CVProcessingState, frozenset[CVProcessingState]] = {
    CVProcessingState.PENDING: frozenset({CVProcessingState.PROCESSING}),
    CVProcessingState.PROCESSING: frozenset(
        {CVProcessingState.PROCESSED, CVProcessingState.FAILED}
    ),
    CVProcessingState.PROCESSED: frozenset(),
    CVProcessingState.FAILED: frozenset({CVProcessingState.PROCESSING}),
}


class InvalidCVProcessingTransition(ValueError):
    """A caller tried to skip or reverse a CV processing stage."""


class CV(Base):
    """Metadata for one externally stored CV owned by one user."""

    __tablename__ = "cvs"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_cvs_storage_key"),
        CheckConstraint(
            "storage_key <> '' AND storage_key = btrim(storage_key)",
            name="ck_cvs_storage_key_nonblank",
        ),
        CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_cvs_checksum_sha256",
        ),
        CheckConstraint(
            "media_type = 'application/pdf'",
            name="ck_cvs_media_type",
        ),
        CheckConstraint("size_bytes > 0", name="ck_cvs_size_bytes_positive"),
        CheckConstraint(
            "processing_state IN ('pending', 'processing', 'processed', 'failed')",
            name="ck_cvs_processing_state",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_cvs_timestamp_order"),
        Index("ix_cvs_owner_id", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "users.id",
            name="fk_cvs_owner_id_users",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(STORAGE_KEY_LENGTH), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    media_type: Mapped[str] = mapped_column(String(MEDIA_TYPE_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processing_state: Mapped[CVProcessingState] = mapped_column(
        Enum(
            CVProcessingState,
            name="cv_processing_state",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=CVProcessingState.PENDING,
        server_default=CVProcessingState.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    owner: Mapped[User] = relationship()

    @validates("processing_state")
    def require_valid_state_transition(
        self, _key: str, target: CVProcessingState
    ) -> CVProcessingState:
        current = self.__dict__.get("processing_state")
        if current is None:
            if target is not CVProcessingState.PENDING:
                raise InvalidCVProcessingTransition("a CV must start pending")
            return target
        if target not in ALLOWED_STATE_TRANSITIONS[current]:
            raise InvalidCVProcessingTransition(f"cannot move a CV from {current} to {target}")
        return target

    def transition_to(self, target: CVProcessingState) -> None:
        self.processing_state = target
