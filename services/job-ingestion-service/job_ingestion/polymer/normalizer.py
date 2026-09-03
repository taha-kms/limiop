"""Mapping validated Polymer records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.normalizer import to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.polymer.records import PolymerJobRecord, describe_failure
from job_ingestion.polymer.source import SOURCE_KEY
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import (
    EMPLOYMENT_PRECEDENCE,
    WORKPLACE_PRECEDENCE,
    most_specific,
    stated_employments,
    stated_workplaces,
)


class PolymerNormalizer:
    """Maps one validated Polymer record onto the canonical contract.

    "Remote friendly" reads as remote because the shared vocabulary counts the
    word `remote`, and that is the vocabulary's rule rather than this
    normalizer's.
    """

    def normalize(self, record: PolymerJobRecord, raw: RawRecord) -> NormalizedJob:
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.organization_name},
                    "title": record.title,
                    "description": to_plain_text(record.description),
                    "location": record.display_location or None,
                    "workplace_type": most_specific(
                        stated_workplaces(record.remoteness_pretty),
                        WORKPLACE_PRECEDENCE,
                        WorkplaceType.UNSPECIFIED,
                    ),
                    "employment_type": most_specific(
                        stated_employments(record.kind_pretty),
                        EMPLOYMENT_PRECEDENCE,
                        EmploymentType.UNSPECIFIED,
                    ),
                    "application_url": str(record.job_post_url),
                    "published_at": record.published_at,
                    "expires_at": None,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        # Unique within the source: a posting identifier is only
                        # unique within the board that issued it.
                        "source_job_id": f"{record.board}:{record.id}",
                        "source_url": str(record.job_post_url),
                        "raw_payload": raw,
                    },
                }
            )
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=f"{record.board}:{record.id}",
            ) from error
