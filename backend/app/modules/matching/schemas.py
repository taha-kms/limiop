"""What a match looks like on the wire."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.jobs.schemas import JobSummary

DEFAULT_MATCH_LIMIT = 20
MAXIMUM_MATCH_LIMIT = 50


class MatchedSkill(BaseModel):
    """One concept, named. Identifiers alone explain nothing to a reader."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    concept_id: UUID
    preferred_label: str


class JobMatch(BaseModel):
    """One posting, scored, with both halves of the reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job: JobSummary
    score: float = Field(ge=0.0, le=1.0)
    matched_skills: tuple[MatchedSkill, ...]
    missing_skills: tuple[MatchedSkill, ...]


class MatchListResponse(BaseModel):
    """One page of matches, and why there might not be any.

    `ranked` is the number scored, not the number returned, so a reader can tell
    a short page from a small catalogue.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    matches: tuple[JobMatch, ...]
    ranked: int


class MatchListQuery(BaseModel):
    """How many matches to return.

    No cursor. The order comes from a score computed per request against a
    profile the candidate can edit and a catalogue that is re-extracted hourly,
    so a position in it is not a position anyone can come back to. A cursor over
    an order that changes underneath it is a cursor that lies, and the listing's
    own rule already says a cursor is only meaningful inside the filter set that
    produced it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int = Field(default=DEFAULT_MATCH_LIMIT, ge=1, le=MAXIMUM_MATCH_LIMIT)
