"""Mapping of validated Himalayas records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

from datetime import UTC, datetime

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.normalizer import to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.himalayas.client import SOURCE_KEY
from job_ingestion.himalayas.records import HimalayasJobRecord, describe_failure
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import EMPLOYMENT_PRECEDENCE, most_specific, stated_employments

# Himalayas aggregates postings that employers publish on their own careers
# page, so where the two disagree the employer's own page is the better
# account. Ranked below a board, and above nothing, since it is the only
# aggregator until another is added.
PRECEDENCE = 10


def to_employment_type(employment_type: str) -> EmploymentType:
    """Pick the most specific employment relationship the provider named."""
    return most_specific(
        stated_employments(employment_type),
        EMPLOYMENT_PRECEDENCE,
        EmploymentType.UNSPECIFIED,
    )


def to_published_at(pub_date: int | None) -> datetime | None:
    return datetime.fromtimestamp(pub_date, UTC) if pub_date is not None else None


def to_expires_at(expiry_date: int | None, pub_date: int | None) -> datetime | None:
    """Read the expiry epoch, dropping it when it precedes publication.

    The canonical contract refuses a job whose `expires_at` precedes its
    `published_at`. Himalayas is a feed, not a system of record, and an
    inconsistency between its two dates is a provider glitch rather than a
    reason to lose the posting, so the disputed expiry is dropped instead of
    failing the record. Compared as the raw epochs rather than as converted
    datetimes, since both come from the same clock and neither conversion can
    change their order.
    """
    if expiry_date is None:
        return None
    if pub_date is not None and expiry_date < pub_date:
        return None
    return datetime.fromtimestamp(expiry_date, UTC)


class HimalayasNormalizer:
    """Maps one validated Himalayas record onto the canonical contract."""

    def normalize(self, record: HimalayasJobRecord, raw: RawRecord) -> NormalizedJob:
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.companyName},
                    "title": record.title,
                    "description": to_plain_text(record.description),
                    "location": ", ".join(record.locationRestrictions) or None,
                    # Himalayas lists remote roles exclusively: the arrangement
                    # is a fact about the board, not something each posting
                    # states, so nothing here is read to arrive at it.
                    "workplace_type": WorkplaceType.REMOTE,
                    "employment_type": to_employment_type(record.employmentType),
                    "application_url": str(record.applicationLink),
                    "published_at": to_published_at(record.pubDate),
                    "expires_at": to_expires_at(record.expiryDate, record.pubDate),
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        "source_job_id": str(record.guid),
                        "source_url": str(record.guid),
                        "raw_payload": dict(raw),
                    },
                }
            )
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=str(record.guid),
            ) from error
