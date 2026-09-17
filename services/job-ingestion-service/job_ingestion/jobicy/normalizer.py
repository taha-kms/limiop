"""Mapping of validated Jobicy records onto the canonical contract.

Pure and deterministic: the same record always produces the same canonical job,
and nothing here touches the network or the database.
"""

import re

from platform_db.models.catalog import EmploymentType, WorkplaceType
from pydantic import ValidationError

from job_ingestion.arbeitnow.normalizer import fit_location, to_plain_text
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.jobicy.client import SOURCE_KEY
from job_ingestion.jobicy.records import JobicyJobRecord, describe_failure
from job_ingestion.schemas import NormalizedJob
from job_ingestion.vocabulary import EMPLOYMENT_PRECEDENCE, most_specific, stated_employments

# Jobicy aggregates postings employers publish through its own remote-jobs
# board, the same relationship Arbeitnow has to the boards it copies. Ranked
# the same as Arbeitnow: both are aggregators, and neither outranks the other.
PRECEDENCE = 10

ANYWHERE = "anywhere"
COLLAPSE_WHITESPACE = re.compile(r"\s+")


def to_location(geo: str) -> str | None:
    """Read a place out of `jobGeo`, or nothing when it names none.

    'Anywhere' is Jobicy's own word for "no particular place", the same claim
    the workplace type already carries as `REMOTE`. Keeping it as a location
    would make every unlocated Jobicy posting claim to be headquartered in a
    place called Anywhere.
    """
    collapsed = COLLAPSE_WHITESPACE.sub(" ", geo).strip()
    if not collapsed or collapsed.casefold() == ANYWHERE:
        return None
    return collapsed


def to_employment_type(job_types: tuple[str, ...]) -> EmploymentType:
    """Pick the most specific employment type the provider named."""
    return most_specific(
        stated_employments(*job_types),
        EMPLOYMENT_PRECEDENCE,
        EmploymentType.UNSPECIFIED,
    )


class JobicyNormalizer:
    """Maps one validated Jobicy record onto the canonical contract."""

    def normalize(self, record: JobicyJobRecord, raw: RawRecord) -> NormalizedJob:
        try:
            return NormalizedJob.model_validate(
                {
                    "company": {"display_name": record.companyName},
                    "title": record.jobTitle,
                    "description": to_plain_text(record.jobDescription),
                    "location": fit_location(to_location(record.jobGeo)),
                    # The feed lists only remote postings, so nothing needs to
                    # be read to know the arrangement: it is the premise of
                    # the source, not something a record can contradict.
                    "workplace_type": WorkplaceType.REMOTE,
                    "employment_type": to_employment_type(record.jobType),
                    "application_url": str(record.url),
                    "published_at": record.pubDate,
                    "provenance": {
                        "source_key": SOURCE_KEY,
                        "source_job_id": record.id,
                        "source_url": str(record.url),
                        "raw_payload": dict(raw),
                    },
                }
            )
        except ValidationError as error:
            raise RecordValidationError(
                SOURCE_KEY,
                describe_failure(error),
                source_job_id=record.id,
            ) from error
