"""Persistence models for the job catalog."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base
from app.modules.jobs.constants import FINGERPRINT_LENGTH
from app.modules.jobs.domain import (
    EmploymentType,
    JobStatus,
    WorkplaceType,
    normalize_company_name,
)


class JobSource(Base):
    """A provider from which SkillSync can ingest jobs."""

    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("key", name="uq_job_sources_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
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
        Index("ix_jobs_fingerprint", "fingerprint"),
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
    fingerprint: Mapped[str] = mapped_column(
        String(FINGERPRINT_LENGTH),
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
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    job: Mapped[Job] = relationship(back_populates="provenance_records")
    source: Mapped[JobSource] = relationship(back_populates="provenance_records")
