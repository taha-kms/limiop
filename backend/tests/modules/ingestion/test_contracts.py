import asyncio
from collections.abc import AsyncIterator
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from app.modules.ingestion.contracts import (
    IngestionStage,
    IngestionSummary,
    JobRecordNormalizer,
    JobRecordValidator,
    JobSourceClient,
    RawPage,
    RawRecord,
    RecordFailure,
    RecordOutcome,
)
from app.modules.ingestion.errors import RecordValidationError
from app.modules.jobs.schemas import NormalizedJob

SOURCE_KEY = "arbeitnow"


class ProviderRecord(BaseModel):
    slug: str
    title: str
    company_name: str
    url: str


class FakeClient:
    """A provider client that satisfies the fetch boundary."""

    def __init__(self, pages: dict[int, RawPage]) -> None:
        self.pages = pages
        self.requested: list[int] = []
        self._reached_the_end = False

    @property
    def source_key(self) -> str:
        return SOURCE_KEY

    @property
    def reached_the_end(self) -> bool:
        return self._reached_the_end

    async def fetch_page(self, page: int) -> RawPage:
        self.requested.append(page)
        return self.pages[page]

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        self._reached_the_end = False
        page = 1
        while page in self.pages:
            fetched = await self.fetch_page(page)
            yield fetched
            if fetched.next_page is None:
                self._reached_the_end = True
                return
            page = fetched.next_page


class FakeValidator:
    """A validator that satisfies the validate boundary."""

    def validate(self, record: RawRecord) -> ProviderRecord:
        if "slug" not in record:
            raise RecordValidationError(SOURCE_KEY, "slug is required")
        return ProviderRecord.model_validate(record)


class FakeNormalizer:
    """A normalizer that satisfies the normalize boundary."""

    def normalize(self, record: ProviderRecord, raw: RawRecord) -> NormalizedJob:
        return NormalizedJob.model_validate(
            {
                "company": {"display_name": record.company_name},
                "title": record.title,
                "description": "Build reliable data pipelines.",
                "application_url": record.url,
                "published_at": datetime(2026, 8, 18, 10, tzinfo=UTC),
                "provenance": {
                    "source_key": SOURCE_KEY,
                    "source_job_id": record.slug,
                    "source_url": record.url,
                },
            }
        )


def accepts_client(client: JobSourceClient) -> str:
    return client.source_key


def accepts_validator(
    validator: JobRecordValidator[ProviderRecord],
) -> JobRecordValidator[ProviderRecord]:
    return validator


def accepts_normalizer(
    normalizer: JobRecordNormalizer[ProviderRecord],
) -> JobRecordNormalizer[ProviderRecord]:
    return normalizer


def test_stage_and_outcome_vocabularies_are_stable_strings() -> None:
    assert [stage.value for stage in IngestionStage] == [
        "fetch",
        "validate",
        "normalize",
        "persist",
    ]
    assert [outcome.value for outcome in RecordOutcome] == ["created", "updated", "skipped"]


def test_raw_page_reports_whether_more_pages_follow() -> None:
    assert RawPage(records=({"slug": "a"},), next_page=2).has_next_page is True
    assert RawPage(records=({"slug": "a"},)).has_next_page is False


def test_raw_page_is_immutable() -> None:
    page = RawPage(records=())

    with pytest.raises(FrozenInstanceError):
        page.next_page = 3  # type: ignore[misc]


def test_record_failure_keeps_the_stage_that_rejected_the_record() -> None:
    failure = RecordFailure(
        stage=IngestionStage.VALIDATE,
        reason="slug is required",
        source_job_id="external-42",
    )

    assert failure.stage is IngestionStage.VALIDATE
    assert failure.source_job_id == "external-42"


def test_record_failure_allows_an_unidentifiable_record() -> None:
    failure = RecordFailure(stage=IngestionStage.VALIDATE, reason="record is not an object")

    assert failure.source_job_id is None


def test_summary_starts_empty() -> None:
    summary = IngestionSummary(source_key=SOURCE_KEY)

    assert summary.fetched == 0
    assert summary.persisted == 0
    assert summary.failed == 0
    assert summary.failures == ()
    assert summary.processing_complete is True


def test_summary_counts_persisted_records() -> None:
    summary = IngestionSummary(source_key=SOURCE_KEY, fetched=5, created=3, updated=1, skipped=1)

    assert summary.persisted == 4
    assert summary.failed == 0
    assert summary.processing_complete is True


def test_summary_is_incomplete_while_any_record_failed() -> None:
    summary = IngestionSummary(
        source_key=SOURCE_KEY,
        fetched=2,
        created=1,
        failures=(RecordFailure(stage=IngestionStage.NORMALIZE, reason="missing title"),),
    )

    assert summary.failed == 1
    assert summary.processing_complete is False


def test_summary_is_incomplete_when_records_vanish_without_a_failure() -> None:
    summary = IngestionSummary(source_key=SOURCE_KEY, fetched=10, created=4)

    assert summary.failures == ()
    assert summary.processing_complete is False


@pytest.mark.parametrize(
    ("implementation", "protocol"),
    [
        (FakeClient({}), JobSourceClient),
        (FakeValidator(), JobRecordValidator),
        (FakeNormalizer(), JobRecordNormalizer),
    ],
)
def test_stage_implementations_satisfy_their_protocol(
    implementation: object,
    protocol: type,
) -> None:
    assert isinstance(implementation, protocol)


def test_a_partial_implementation_does_not_satisfy_a_protocol() -> None:
    class MissingFetch:
        @property
        def source_key(self) -> str:
            return SOURCE_KEY

    assert not isinstance(MissingFetch(), JobSourceClient)


def test_stages_chain_from_raw_record_to_canonical_job() -> None:
    client = FakeClient(
        {
            1: RawPage(
                records=(
                    {
                        "slug": "external-42",
                        "title": "Data Engineer",
                        "company_name": "Acme GmbH",
                        "url": "https://arbeitnow.example.com/jobs/42",
                    },
                )
            )
        }
    )
    validator = accepts_validator(FakeValidator())
    normalizer = accepts_normalizer(FakeNormalizer())

    page = asyncio.run(client.fetch_page(1))
    raw = page.records[0]
    normalized = normalizer.normalize(validator.validate(raw), raw)

    assert accepts_client(client) == SOURCE_KEY
    assert client.requested == [1]
    assert normalized.title == "Data Engineer"
    assert normalized.provenance.source_job_id == "external-42"
    assert normalized.company.display_name == "Acme GmbH"


def test_validator_reports_an_unusable_record_as_a_typed_failure() -> None:
    with pytest.raises(RecordValidationError, match="slug is required"):
        FakeValidator().validate({"title": "Data Engineer"})
