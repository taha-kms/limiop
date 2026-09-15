"""Mapping of validated Remotive records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.normalizer import to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.remotive.client import SOURCE_KEY
from job_ingestion.remotive.records import RemotiveJobRecord, describe_failure
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import (
    EMPLOYMENT_PRECEDENCE,
    most_specific,
    stated_employments,
)


class RemotiveNormalizer:
    """Maps one validated Remotive record onto the canonical contract.

    Remotive is a remote-only board: every posting on it is remote by
    construction of the feed, not by a claim any one field makes, so the
    workplace arrangement is set outright rather than read out of text the
    way a mixed-arrangement aggregator requires.
    """

    def normalize(self, record: RemotiveJobRecord, raw: RawRecord) -> NormalizedJob:
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.company_name},
                    "title": record.title,
                    "description": to_plain_text(record.description),
                    "location": record.candidate_required_location or None,
                    "workplace_type": WorkplaceType.REMOTE,
                    "employment_type": most_specific(
                        stated_employments(record.job_type),
                        EMPLOYMENT_PRECEDENCE,
                        EmploymentType.UNSPECIFIED,
                    ),
                    "application_url": str(record.url),
                    "published_at": record.publication_date,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        "source_job_id": str(record.id),
                        "source_url": str(record.url),
                        "raw_payload": dict(raw),
                    },
                }
            )
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=str(record.id),
            ) from error
