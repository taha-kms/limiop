"""Persistence models for the shared job catalog."""

import unicodedata
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from platform_db.base import Base

# A version prefix plus a 64-character SHA-256 digest, with room to grow.
MATCH_KEY_LENGTH = 80


class WorkplaceType(StrEnum):
    """Canonical workplace arrangement.

    REMOTE means work is performed away from an employer site. HYBRID combines
    remote and employer-site work. ONSITE requires employer-site work.
    UNSPECIFIED is the fallback for missing or unknown provider values.
    """

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class EmploymentType(StrEnum):
    """Canonical employment relationship.

    FULL_TIME and PART_TIME describe employee schedules. CONTRACT describes
    contract work, INTERNSHIP describes a training placement, and TEMPORARY
    describes time-limited employment. UNSPECIFIED is the fallback for missing
    or unknown provider values.
    """

    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNSPECIFIED = "unspecified"


class JobStatus(StrEnum):
    """Canonical job lifecycle state.

    ACTIVE jobs are listable, EXPIRED jobs passed their stated lifetime, and
    REMOVED jobs were withdrawn or disappeared under a trusted lifecycle rule.
    """

    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"


def normalize_company_name(value: str) -> str:
    """Apply NFKC, case-fold, and collapse whitespace while preserving punctuation."""
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if not normalized:
        raise ValueError("company name must contain non-whitespace characters")
    return normalized


class JobSource(Base):
    """A provider from which SkillSync can ingest jobs."""

    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("key", name="uq_job_sources_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # How much this source's account of a field is trusted against another's.
    # Higher wins. Stored rather than held in code so the ordering that produced
    # a stored record can be read back out of the database.
    precedence: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
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
    provenance_records: Mapped[list["JobProvenance"]] = relationship(back_populates="source")


class Company(Base):
    """A canonical employer referenced by job records."""

    __tablename__ = "companies"
    __table_args__ = (Index("ix_companies_normalized_name", "normalized_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
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
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")

    @validates("display_name")
    def derive_normalized_name(self, _key: str, display_name: str) -> str:
        self.normalized_name = normalize_company_name(display_name)
        return display_name


class Job(Base):
    """A source-independent job used by serving, analytics, and matching."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "workplace_type IN ('remote', 'hybrid', 'onsite', 'unspecified')",
            name="ck_jobs_workplace_type",
        ),
        CheckConstraint(
            "employment_type IN ("
            "'full-time', 'part-time', 'contract', 'internship', 'temporary', 'unspecified'"
            ")",
            name="ck_jobs_employment_type",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'removed')",
            name="ck_jobs_status",
        ),
        CheckConstraint(
            "published_at IS NULL OR expires_at IS NULL OR expires_at >= published_at",
            name="ck_jobs_expiry_not_before_publication",
        ),
        Index("ix_jobs_match_key", "match_key"),
        # Stored in the order the listing reads it. See migration 0007.
        Index(
            "ix_jobs_status_published_at_id",
            "status",
            text("published_at DESC NULLS LAST"),
            text("id DESC"),
        ),
        Index("ix_jobs_status_expires_at", "status", "expires_at"),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_location", "location"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "companies.id",
            name="fk_jobs_company_id_companies",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    # Blocks candidates by employer and role. Not an identity on its own:
    # `jobs.matching` explains why place and text decide among them.
    match_key: Mapped[str] = mapped_column(
        String(MATCH_KEY_LENGTH),
        nullable=False,
        server_default="",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workplace_type: Mapped[WorkplaceType] = mapped_column(
        Enum(
            WorkplaceType,
            name="job_workplace_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=WorkplaceType.UNSPECIFIED,
        server_default=WorkplaceType.UNSPECIFIED.value,
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(
            EmploymentType,
            name="job_employment_type",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=EmploymentType.UNSPECIFIED,
        server_default=EmploymentType.UNSPECIFIED.value,
    )
    application_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            native_enum=False,
            create_constraint=False,
            validate_strings=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=JobStatus.ACTIVE,
        server_default=JobStatus.ACTIVE.value,
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
    company: Mapped[Company] = relationship(back_populates="jobs")
    provenance_records: Mapped[list["JobProvenance"]] = relationship(back_populates="job")


class JobProvenance(Base):
    """Trace one canonical job back to an untrusted external source record."""

    __tablename__ = "job_provenance"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "source_job_id",
            name="uq_job_provenance_source_id_source_job_id",
        ),
        CheckConstraint(
            "last_seen_at >= first_seen_at",
            name="ck_job_provenance_seen_order",
        ),
        Index("ix_job_provenance_job_id", "job_id"),
        # Reconciliation asks one question of one source: which of its
        # postings did this run not see.
        Index("ix_job_provenance_source_id_retired_at", "source_id", "retired_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "jobs.id",
            name="fk_job_provenance_job_id_jobs",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "job_sources.id",
            name="fk_job_provenance_source_id_job_sources",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # When this source stopped listing the posting. Null while the source
    # still carries it. Set per source rather than per job, because one source
    # dropping a posting says nothing about whether another still has it.
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    job: Mapped[Job] = relationship(back_populates="provenance_records")
    source: Mapped[JobSource] = relationship(back_populates="provenance_records")
