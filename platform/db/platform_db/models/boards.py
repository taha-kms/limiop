"""Persistence model for the automatic board registry.

Every row records the evidence behind it and when it was checked, because
that is what makes automatic registration safe to run unattended: a wrong
decision is visible, dated, and reversible. Rows an operator pinned by hand
are marked so no automated run ever changes them.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_db.base import Base
from platform_db.models.catalog import Company, JobSource


class BoardStatus(StrEnum):
    """Where one guessed or verified board stands.

    CANDIDATE is a guess nobody has decided on yet. CONFIRMED is verified
    against evidence naming the company. NAMED means the board states a
    matching name with no outside evidence yet. WRONG_COMPANY answered for
    somebody else; it is never polled and never re-guessed. NOT_FOUND and
    UNREACHABLE describe a probe that turned up nothing or could not run.
    INACTIVE was polled once and then stopped answering. BLOCKED is an
    operator saying no.
    """

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    NAMED = "named"
    WRONG_COMPANY = "wrong_company"
    NOT_FOUND = "not_found"
    UNREACHABLE = "unreachable"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


# Statuses a poll run reads from. A pinned row is polled regardless of its
# status, so this set alone does not decide what a run actually polls.
POLLED_STATUSES = frozenset({BoardStatus.CONFIRMED, BoardStatus.NAMED})


class JobBoard(Base):
    """One provider board, how it was found and verified, and its poll state."""

    __tablename__ = "job_boards"
    __table_args__ = (
        UniqueConstraint("source_id", "slug", name="uq_job_boards_source_id_slug"),
        CheckConstraint(
            "status IN ("
            "'candidate','confirmed','named','wrong_company',"
            "'not_found','unreachable','inactive','blocked'"
            ")",
            name="ck_job_boards_status",
        ),
        CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_job_boards_failures_not_negative",
        ),
        # The poll query: every source's boards due for polling.
        Index("ix_job_boards_source_id_status", "source_id", "status"),
        Index("ix_job_boards_company_id", "company_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "job_sources.id",
            name="fk_job_boards_source_id_job_sources",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    # No constraint ties status to company_id: an operator-pinned row may have
    # no company yet, until discovery verifies one.
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "companies.id",
            name="fk_job_boards_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    status: Mapped[BoardStatus] = mapped_column(
        Enum(
            BoardStatus,
            name="board_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=BoardStatus.CANDIDATE,
        server_default=BoardStatus.CANDIDATE.value,
    )
    # Keys: kind, found_company, website, checked_at; kinds: provider_name,
    # site_title, website_link, website_redirect, operator. Validated by
    # whoever writes it, not here.
    evidence: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_posting_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    # Set by an operator; automatic runs report on a pinned row and never
    # change it.
    pinned: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default=text("false"),
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
    source: Mapped[JobSource] = relationship(back_populates="boards")
    company: Mapped[Company | None] = relationship(back_populates="boards")
