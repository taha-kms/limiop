"""Ranking the catalogue for one candidate.

Everything is computed per request. The score is a set intersection over the
handful of concepts a posting carries, and a stored one would be invalidated by
the candidate editing their profile, by hourly re-extraction, and by publishing
a new alias table — two of which run unattended.
"""

from dataclasses import dataclass
from uuid import UUID

from platform_db.models import Job
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.schemas import JobSummary
from app.modules.matching.overlap import SkillMatch, match_skills
from app.modules.matching.queries import (
    candidate_concepts,
    concept_labels,
    job_concepts,
    scorable_jobs,
)
from app.modules.matching.schemas import JobMatch, MatchedSkill, MatchListResponse

# One skill is not enough to rank a person. Measured: a corpus candidate holding
# only "Communication skills" scored 0.0 on every ranking metric while still
# being served a confident-looking 0.33 match, and that single case is the whole
# gap between the baseline's reported 0.8055 and the 0.9666 the rest average.
#
# The evidence establishes that one is too few, not where the line is. Three is
# a judgment inside that bound: it also refuses a two-concept profile, which has
# the same problem in a less obvious way, and every real candidate in the corpus
# holds four.
MINIMUM_RANKABLE_SKILLS = 3


@dataclass(frozen=True, slots=True)
class Scored:
    """One job and its match, before either is turned into a response."""

    job: Job
    match: SkillMatch


async def rank_jobs_for(session: AsyncSession, user_id: UUID, limit: int) -> MatchListResponse:
    """The candidate's best matches, highest first.

    A profile too thin to rank returns nothing rather than an arbitrary order of
    the whole catalogue. There is no honest ranking of everything against one
    generic skill, and a confident-looking wrong answer is worse than an empty
    one.
    """
    candidate = set(await session.scalars(candidate_concepts(user_id)))
    if len(candidate) < MINIMUM_RANKABLE_SKILLS:
        return MatchListResponse(matches=(), ranked=0)

    jobs = list(await session.scalars(scorable_jobs(candidate)))
    if not jobs:
        return MatchListResponse(matches=(), ranked=0)

    required: dict[UUID, set[UUID]] = {job.id: set() for job in jobs}
    for job_id, concept_id in await session.execute(job_concepts(list(required))):
        required[job_id].add(concept_id)

    scored = sorted(
        (Scored(job=job, match=match_skills(candidate, required[job.id])) for job in jobs),
        # Ties break on the job id, which is total and stable, so two runs
        # against unchanged data return the same order.
        key=lambda entry: (-entry.match.score, entry.job.id),
    )
    page = scored[:limit]

    shown = {concept for entry in page for concept in entry.match.matched + entry.match.missing}
    labels: dict[UUID, str] = {}
    if shown:
        labels = {
            row.id: row.preferred_label for row in await session.execute(concept_labels(shown))
        }

    return MatchListResponse(
        matches=tuple(to_match(entry, labels) for entry in page),
        ranked=len(scored),
    )


def to_match(entry: Scored, labels: dict[UUID, str]) -> JobMatch:
    return JobMatch(
        job=JobSummary.of(entry.job),
        score=entry.match.score,
        matched_skills=named(entry.match.matched, labels),
        missing_skills=named(entry.match.missing, labels),
    )


def named(concepts: tuple[UUID, ...], labels: dict[UUID, str]) -> tuple[MatchedSkill, ...]:
    """Name every concept, ordered by the name a reader will see."""
    return tuple(
        sorted(
            (
                MatchedSkill(concept_id=concept, preferred_label=labels[concept])
                for concept in concepts
                if concept in labels
            ),
            key=lambda skill: skill.preferred_label.lower(),
        )
    )
