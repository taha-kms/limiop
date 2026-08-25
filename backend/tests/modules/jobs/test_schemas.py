import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from platform_db.models import Company, Job, JobProvenance, JobSource
from pydantic import PostgresDsn, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.db.session import Database
from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.schemas import (
    MAX_URL_LENGTH,
    CompanyRead,
    JobRead,
    NormalizedCompany,
    NormalizedJob,
    NormalizedProvenance,
    ProvenanceRead,
)

PUBLISHED_AT = datetime(2026, 8, 18, 10, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 9, 18, 10, tzinfo=UTC)


def normalized_job_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "company": {"display_name": "Acme GmbH", "website_url": "https://acme.example.com"},
        "title": "Data Engineer",
        "description": "Build reliable data pipelines.",
        "location": "Berlin, Germany",
        "workplace_type": "hybrid",
        "employment_type": "full-time",
        "application_url": "https://acme.example.com/jobs/data-engineer",
        "published_at": PUBLISHED_AT,
        "expires_at": EXPIRES_AT,
        "provenance": {
            "source_key": "arbeitnow",
            "source_job_id": "external-42",
            "source_url": "https://arbeitnow.example.com/jobs/42",
            "raw_payload": {"title": "Data Engineer"},
        },
    }
    payload.update(overrides)
    return payload


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def clear(database: Database) -> None:
        async with database.session() as session:
            await session.execute(delete(JobProvenance))
            await session.execute(delete(Job))
            await session.execute(delete(Company))
            await session.execute(delete(JobSource))
            await session.commit()

    async def run() -> None:
        database = Database(database_url)
        try:
            await clear(database)
            await test(database)
        finally:
            await clear(database)
            await database.dispose()

    asyncio.run(run())


def test_normalized_job_accepts_a_complete_record() -> None:
    job = NormalizedJob.model_validate(normalized_job_payload())

    assert job.title == "Data Engineer"
    assert job.company.display_name == "Acme GmbH"
    assert job.workplace_type is WorkplaceType.HYBRID
    assert job.employment_type is EmploymentType.FULL_TIME
    assert job.provenance.source_key == "arbeitnow"
    assert job.provenance.raw_payload == {"title": "Data Engineer"}


def test_normalized_job_defaults_unknown_classifications_to_unspecified() -> None:
    payload = normalized_job_payload()
    del payload["workplace_type"]
    del payload["employment_type"]

    job = NormalizedJob.model_validate(payload)

    assert job.workplace_type is WorkplaceType.UNSPECIFIED
    assert job.employment_type is EmploymentType.UNSPECIFIED


def test_normalized_job_treats_optional_values_as_absent() -> None:
    payload = normalized_job_payload()
    for field in ("location", "published_at", "expires_at"):
        del payload[field]
    del payload["company"]["website_url"]
    del payload["provenance"]["raw_payload"]

    job = NormalizedJob.model_validate(payload)

    assert job.location is None
    assert job.published_at is None
    assert job.expires_at is None
    assert job.company.website_url is None
    assert job.provenance.raw_payload is None


def test_normalized_job_strips_surrounding_whitespace() -> None:
    job = NormalizedJob.model_validate(
        normalized_job_payload(title="  Data Engineer  ", location="  Berlin  ")
    )

    assert job.title == "Data Engineer"
    assert job.location == "Berlin"


def test_normalized_job_is_immutable() -> None:
    job = NormalizedJob.model_validate(normalized_job_payload())

    with pytest.raises(ValidationError):
        job.title = "Senior Data Engineer"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "   "),
        ("title", "x" * 256),
        ("description", ""),
        ("location", ""),
        ("application_url", "not-a-url"),
        ("application_url", "javascript:alert(1)"),
        ("published_at", "not-a-timestamp"),
        ("workplace_type", "somewhere-else"),
        ("employment_type", "freelance-ish"),
    ],
)
def test_normalized_job_rejects_unusable_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as error:
        NormalizedJob.model_validate(normalized_job_payload(**{field: value}))

    assert field in str(error.value)


def test_normalized_job_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="published_at"):
        NormalizedJob.model_validate(normalized_job_payload(published_at=datetime(2026, 8, 18)))


def test_normalized_job_rejects_expiry_before_publication() -> None:
    with pytest.raises(ValidationError, match="expires_at must not precede published_at"):
        NormalizedJob.model_validate(
            normalized_job_payload(published_at=EXPIRES_AT, expires_at=PUBLISHED_AT)
        )


def test_normalized_job_allows_expiry_equal_to_publication() -> None:
    job = NormalizedJob.model_validate(
        normalized_job_payload(published_at=PUBLISHED_AT, expires_at=PUBLISHED_AT)
    )

    assert job.expires_at == job.published_at


def test_normalized_job_rejects_urls_longer_than_the_column() -> None:
    overlong = "https://acme.example.com/jobs/" + "a" * MAX_URL_LENGTH

    with pytest.raises(ValidationError, match=str(MAX_URL_LENGTH)):
        NormalizedJob.model_validate(normalized_job_payload(application_url=overlong))


def test_normalized_job_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="salary_hint"):
        NormalizedJob.model_validate(normalized_job_payload(salary_hint="lots"))


def test_normalized_job_requires_provenance() -> None:
    payload = normalized_job_payload()
    del payload["provenance"]

    with pytest.raises(ValidationError, match="provenance"):
        NormalizedJob.model_validate(payload)


def test_normalized_provenance_requires_a_source_key_that_fits_the_column() -> None:
    with pytest.raises(ValidationError, match="source_key"):
        NormalizedProvenance.model_validate(
            {
                "source_key": "a" * 101,
                "source_job_id": "external-42",
                "source_url": "https://arbeitnow.example.com/jobs/42",
            }
        )


def test_normalized_company_rejects_a_blank_name() -> None:
    with pytest.raises(ValidationError, match="display_name"):
        NormalizedCompany.model_validate({"display_name": "   "})


def test_provenance_read_has_no_raw_payload_field() -> None:
    assert "raw_payload" not in ProvenanceRead.model_fields


@pytest.mark.integration
def test_normalized_job_round_trips_through_postgresql(database_url: PostgresDsn) -> None:
    normalized = NormalizedJob.model_validate(normalized_job_payload())

    async def exercise(database: Database) -> None:
        source = JobSource(
            key=normalized.provenance.source_key,
            display_name="Arbeitnow",
            base_url="https://arbeitnow.example.com",
        )
        company = Company(
            display_name=normalized.company.display_name,
            website_url=str(normalized.company.website_url),
        )
        job = Job(
            company=company,
            title=normalized.title,
            description=normalized.description,
            location=normalized.location,
            workplace_type=normalized.workplace_type,
            employment_type=normalized.employment_type,
            application_url=str(normalized.application_url),
            published_at=normalized.published_at,
            expires_at=normalized.expires_at,
        )
        provenance = JobProvenance(
            job=job,
            source=source,
            source_job_id=normalized.provenance.source_job_id,
            source_url=str(normalized.provenance.source_url),
            raw_payload=normalized.provenance.raw_payload,
        )

        async with database.session() as session:
            session.add(provenance)
            await session.commit()

        async with database.session() as session:
            stored = (
                await session.scalars(
                    select(Job).options(
                        selectinload(Job.company),
                        selectinload(Job.provenance_records),
                    )
                )
            ).one()
            served = JobRead.model_validate(stored)
            served_provenance = ProvenanceRead.model_validate(stored.provenance_records[0])

        assert served.title == normalized.title
        assert served.description == normalized.description
        assert served.location == normalized.location
        assert served.workplace_type is normalized.workplace_type
        assert served.employment_type is normalized.employment_type
        assert served.application_url == normalized.application_url
        assert served.published_at == normalized.published_at
        assert served.expires_at == normalized.expires_at
        assert served.status is JobStatus.ACTIVE
        assert served.company == CompanyRead(
            id=served.company.id,
            display_name=normalized.company.display_name,
            website_url=normalized.company.website_url,
        )
        assert served_provenance.source_job_id == normalized.provenance.source_job_id
        assert served_provenance.source_url == normalized.provenance.source_url
        assert served_provenance.first_seen_at == served_provenance.last_seen_at

    run_database_test(database_url, exercise)
