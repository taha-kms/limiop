"""Mapping validated Greenhouse records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.normalizer import to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.greenhouse.records import GreenhouseJobRecord, describe_failure
from job_ingestion.greenhouse.source import SOURCE_KEY
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import (
    EMPLOYMENT_PRECEDENCE,
    WORKPLACE_PRECEDENCE,
    most_specific,
    stated_employments,
    stated_workplaces,
)

# Employer-defined field names that carry an arrangement. Employers pick these
# themselves, so this is a list of what has been seen rather than a schema.
WORKPLACE_FIELDS = ("location type", "workplace", "work arrangement", "remote status")
EMPLOYMENT_FIELDS = ("employment type", "job type", "employment status", "contract type")


def to_workplace_type(record: GreenhouseJobRecord) -> WorkplaceType:
    """Read the arrangement from the employer's own fields, then the location.

    Greenhouse states this outright where Arbeitnow only ever flags remote, so
    this is the first source that can produce `onsite` at all. It still comes
    from a word rather than from silence: a posting with no arrangement field
    and a location naming no arrangement stays unspecified.

    The values are the employer's, not a vocabulary, so `Hybrid
    (Travel-Required)` has to read as hybrid without anyone listing it.
    """
    stated = stated_workplaces(*record.stated(*WORKPLACE_FIELDS), record.location.name)
    return most_specific(stated, WORKPLACE_PRECEDENCE, WorkplaceType.UNSPECIFIED)


def to_employment_type(record: GreenhouseJobRecord) -> EmploymentType:
    """Read the relationship from the employer's own fields.

    Deliberately narrow. Boards use words like `Regular` here, which says the
    post is not fixed-term and says nothing about hours, so it maps to nothing.
    Reading it as full-time would be inventing a fact the employer did not
    state, which is the same mistake #108 removed from the other source.
    """
    stated = stated_employments(*record.stated(*EMPLOYMENT_FIELDS))
    return most_specific(stated, EMPLOYMENT_PRECEDENCE, EmploymentType.UNSPECIFIED)


class GreenhouseNormalizer:
    """Maps one validated Greenhouse record onto the canonical contract."""

    def normalize(self, record: GreenhouseJobRecord, raw: RawRecord) -> NormalizedJob:
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.company_name},
                    "title": record.title,
                    # Boards return their descriptions with the markup escaped,
                    # so a single flattening pass would decode it into tags
                    # rather than remove them. The shared flattener repeats
                    # until it settles, which is why this needs nothing special.
                    "description": to_plain_text(record.content),
                    "location": record.location.name or None,
                    "workplace_type": to_workplace_type(record),
                    "employment_type": to_employment_type(record),
                    "application_url": str(record.absolute_url),
                    # When the posting first appeared, not when it last changed.
                    # An edit is not a repost, and the listing sorts on this.
                    "published_at": record.first_published,
                    "expires_at": record.application_deadline,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        # Unique within the source: a posting identifier is only
                        # unique within the board that issued it.
                        "source_job_id": f"{record.board}:{record.id}",
                        "source_url": str(record.absolute_url),
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
