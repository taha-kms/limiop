"""Mapping of validated Adzuna records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.adzuna.records import AdzunaJobRecord, describe_failure, provenance_id
from job_ingestion.adzuna.source import SOURCE_KEY
from job_ingestion.arbeitnow.normalizer import to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import EMPLOYMENT_PRECEDENCE, most_specific, stated_employments


def to_employment_type(contract_time: str, contract_type: str) -> EmploymentType:
    """Pick the most specific relationship the two contract fields name.

    `contract_time` says `full_time` or `part_time` and `contract_type` says
    `permanent` or `contract`. Both are read, and the shared precedence makes
    `contract` win over a schedule, since a contractor's hours do not change
    what the relationship is.

    `permanent` maps to nothing. It describes the duration of the relationship
    rather than its kind: the canonical vocabulary has `temporary` for a fixed
    term and no member for the absence of one, and reading `permanent` as
    full-time would be invention, because a permanent part-time post is an
    ordinary thing. A result that says only `permanent` is therefore
    unspecified, which is what the vocabulary reserves for silence.
    """
    return most_specific(
        stated_employments(contract_time, contract_type),
        EMPLOYMENT_PRECEDENCE,
        EmploymentType.UNSPECIFIED,
    )


class AdzunaNormalizer:
    """Maps one validated Adzuna record onto the canonical contract."""

    def normalize(self, record: AdzunaJobRecord, raw: RawRecord) -> NormalizedJob:
        source_job_id = provenance_id(record.country, record.id)
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.company.display_name},
                    "title": record.title,
                    "description": to_plain_text(record.description),
                    "location": record.location.display_name or None,
                    # Adzuna states nothing about where the work happens, and
                    # the shared vocabulary refuses to read an arrangement out
                    # of silence. Nothing in the snippet is read for it either:
                    # an excerpt is too little text to be a statement.
                    "workplace_type": WorkplaceType.UNSPECIFIED,
                    "employment_type": to_employment_type(
                        record.contract_time, record.contract_type
                    ),
                    "application_url": str(record.redirect_url),
                    "published_at": record.created,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        "source_job_id": source_job_id,
                        "source_url": str(record.redirect_url),
                        "raw_payload": dict(raw),
                        # The API serves an excerpt, never the posting, and
                        # the terms do not license fetching the rest. The
                        # flag is what keeps deduplication from ever
                        # comparing this text with another source's.
                        "partial_description": True,
                    },
                }
            )
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY, describe_failure(error), source_job_id=source_job_id
            ) from error
