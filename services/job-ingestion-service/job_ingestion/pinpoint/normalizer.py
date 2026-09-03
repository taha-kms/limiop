"""Mapping validated Pinpoint records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.normalizer import to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.pinpoint.records import PinpointJobRecord, describe_failure
from job_ingestion.pinpoint.source import SOURCE_KEY
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import (
    EMPLOYMENT_PRECEDENCE,
    WORKPLACE_PRECEDENCE,
    most_specific,
    stated_employments,
    stated_workplaces,
)


def to_description(record: PinpointJobRecord) -> str:
    """Flatten the posting's own sections, leaving the employer's boilerplate out.

    The feed splits one posting across several fields. `description` and
    `key_responsibilities` are the posting's own text, and
    `skills_knowledge_expertise` is the part skill extraction reads; `benefits`
    is the employer's standard perks copy, repeated across every posting on
    the board, and is deliberately not read here.
    """
    sections = (
        to_plain_text(record.description),
        to_plain_text(record.key_responsibilities),
        to_plain_text(record.skills_knowledge_expertise),
    )
    return "\n\n".join(section for section in sections if section)


class PinpointNormalizer:
    """Maps one validated Pinpoint record onto the canonical contract.

    The feed names no employer anywhere: not an organisation, not an account,
    nothing a posting or a listing states. The subdomain configured for the
    board is the only identity a run has, and it is the employer's own choice
    of name for its careers site, the same act as choosing a name for a
    storefront's URL. So the company is normalized as that slug, exactly as
    configured: `display_name = record.board`. A deployment that wants a
    prettier name renames the company in the catalogue afterwards; that is a
    presentation choice for the catalogue to make, not a mapping this
    normalizer should invent.
    """

    def normalize(self, record: PinpointJobRecord, raw: RawRecord) -> NormalizedJob:
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.board},
                    "title": record.title,
                    "description": to_description(record),
                    "location": record.location.name or record.location.city or None,
                    "workplace_type": most_specific(
                        stated_workplaces(record.workplace_type, record.workplace_type_text),
                        WORKPLACE_PRECEDENCE,
                        WorkplaceType.UNSPECIFIED,
                    ),
                    "employment_type": most_specific(
                        stated_employments(record.employment_type, record.employment_type_text),
                        EMPLOYMENT_PRECEDENCE,
                        EmploymentType.UNSPECIFIED,
                    ),
                    "application_url": str(record.url),
                    # The feed carries no created, published, or updated
                    # timestamp anywhere; there is nothing to read one from.
                    "published_at": None,
                    "expires_at": record.deadline_at,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        # Unique within the source: a posting identifier is only
                        # unique within the board that issued it.
                        "source_job_id": f"{record.board}:{record.id}",
                        "source_url": str(record.url),
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
