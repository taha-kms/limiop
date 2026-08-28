"""Skill extraction attached to the ingestion of one job posting.

Extraction is enrichment. It runs after the posting is stored and inside the
same transaction, so a posting never commits with half its skills, and a
posting whose skills cannot be written still commits.

The vocabulary comes from the database rather than from a file. The alias table
is published by the backend into `skill_surface_forms`, and reading it back is
the only way this service can share that vocabulary without importing across the
boundary that keeps the two deployables independent.

Nothing here decides which skills are legitimate. That gate was decided in #190
and is closed: a mention that resolves to exactly one concept becomes a
`job_skills` row, and every mention that does not is recorded as an observation
in `job_skill_mentions`, which nothing matches against.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from platform_db.models.catalog import Job
from platform_db.models.job_skills import JobSkill, JobSkillMention
from platform_db.models.skills import SkillAliasVersion, SkillSurfaceForm
from platform_skills import EXTRACTOR_VERSION, Vocabulary, extract_mentions
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class SkillVocabulary:
    """One published alias-table version, ready for the extractor."""

    version: str
    terms: Vocabulary


@dataclass(frozen=True, slots=True)
class ExtractionCounts:
    """What extraction did to one posting."""

    resolved: int = 0
    unknown: int = 0

    def __add__(self, other: "ExtractionCounts") -> "ExtractionCounts":
        return ExtractionCounts(
            resolved=self.resolved + other.resolved,
            unknown=self.unknown + other.unknown,
        )


@dataclass(frozen=True, slots=True)
class Observation:
    """One unresolved surface form as this posting wrote it."""

    normalized_form: str | None
    occurrences: int
    spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class SkillPlan:
    """The rows one posting's text implies, before anything is written."""

    concepts: dict[UUID, str]
    observations: dict[str, Observation]

    @property
    def counts(self) -> ExtractionCounts:
        return ExtractionCounts(
            resolved=len(self.concepts),
            unknown=sum(observation.occurrences for observation in self.observations.values()),
        )


async def load_skill_vocabulary(
    session: AsyncSession,
    *,
    version: str | None = None,
) -> SkillVocabulary | None:
    """Read one published alias table, or report that there is none.

    Defaults to the newest published version rather than to a constant, because
    the constant naming the current version lives in the backend and this
    service may not import it. Pin a version explicitly to stop a publication
    from changing what ingestion extracts under.
    """
    if version is None:
        version = await session.scalar(
            select(SkillAliasVersion.version)
            .order_by(SkillAliasVersion.created_at.desc(), SkillAliasVersion.version.desc())
            .limit(1)
        )
    elif await session.get(SkillAliasVersion, version) is None:
        return None

    if version is None:
        return None

    rows = await session.execute(
        select(
            SkillSurfaceForm.normalized_form,
            SkillSurfaceForm.surface_form,
            SkillSurfaceForm.concept_id,
        ).where(SkillSurfaceForm.alias_version == version)
    )

    # Grouped on the normalized form, which is what the table's own uniqueness
    # key uses. Grouping on the raw spelling would let one ambiguous term reach
    # the extractor as two keys that normalize alike with different concepts,
    # and the extractor refuses that vocabulary outright rather than guessing —
    # turning an ambiguous term into a failure of every record in the run.
    concepts_by_form: dict[str, set[UUID]] = {}
    spelling_by_form: dict[str, str] = {}
    for normalized_form, surface_form, concept_id in rows:
        concepts_by_form.setdefault(normalized_form, set()).add(concept_id)
        spelling_by_form.setdefault(normalized_form, surface_form)

    terms = {
        spelling_by_form[normalized_form]: (next(iter(concepts)) if len(concepts) == 1 else None)
        for normalized_form, concepts in concepts_by_form.items()
    }
    return SkillVocabulary(version=version, terms=terms) if terms else None


def collapse_whitespace(value: str) -> str:
    """Return the matched text as one line.

    Descriptions are flattened from provider markup, so a phrase can be matched
    across a run of newlines the employer never wrote. Collapsing keeps their
    spelling and casing and drops an artefact of our own normalization.

    Nothing truncates afterwards. A collapsed match is the vocabulary phrase as
    the posting spelled it, so it is bounded by the same column that bounds the
    vocabulary. A length filter here would be a shape-based rule on
    observations, which the admission gate forbids, and truncating would corrupt
    the value rather than refusing it.
    """
    return " ".join(value.split())


def plan_skills(text: str, vocabulary: SkillVocabulary) -> SkillPlan:
    """Decide what one posting's text implies, touching no database.

    Pure so the counting rules can be tested without one, which matters because
    `occurrences` is the field most likely to be quietly wrong.
    """
    concepts: dict[UUID, str] = {}
    normalized_by_form: dict[str, str | None] = {}
    spans_by_form: dict[str, list[tuple[int, int]]] = {}

    for mention in extract_mentions(text, vocabulary.terms):
        surface_form = collapse_whitespace(mention.surface_form)
        if mention.concept_id is not None:
            # The first spelling in the posting wins, so re-running over
            # unchanged text cannot rewrite the stored surface form.
            concepts.setdefault(mention.concept_id, surface_form)
            continue
        normalized_by_form.setdefault(surface_form, mention.normalized_form)
        spans_by_form.setdefault(surface_form, []).append(mention.span)

    observations = {
        surface_form: Observation(
            normalized_form=normalized_by_form[surface_form],
            occurrences=len(spans),
            spans=tuple(spans),
        )
        for surface_form, spans in spans_by_form.items()
    }
    return SkillPlan(concepts=concepts, observations=observations)


async def store_job_skills(
    session: AsyncSession,
    *,
    job_id: UUID,
    vocabulary: SkillVocabulary,
    seen_at: datetime,
) -> ExtractionCounts:
    """Replace one posting's skills with what its stored text says now.

    Replacement rather than accumulation: a posting that stops mentioning a
    skill stops carrying it, and an hourly re-run over unchanged text is a
    no-op rather than a slow drift.

    The text is read here, from the stored row, rather than taken from the
    caller. It has to be the merged description — the one that won precedence
    across sources — or a job two sources describe would flap between their two
    accounts every run. Reading it here also keeps the read inside the caller's
    savepoint, where a database error is contained.
    """
    text = await session.scalar(select(Job.description).where(Job.id == job_id))
    if not text:
        return ExtractionCounts()

    plan = plan_skills(text, vocabulary)

    await session.execute(delete(JobSkill).where(JobSkill.job_id == job_id))
    if plan.concepts:
        await session.execute(
            insert(JobSkill).values(
                [
                    {
                        "job_id": job_id,
                        "concept_id": concept_id,
                        "alias_version": vocabulary.version,
                        "surface_form": surface_form,
                    }
                    for concept_id, surface_form in plan.concepts.items()
                ]
            )
        )

    if plan.observations:
        statement = insert(JobSkillMention).values(
            [
                {
                    "job_id": job_id,
                    "surface_form": surface_form,
                    "normalized_form": observation.normalized_form,
                    "occurrences": observation.occurrences,
                    "first_seen_at": seen_at,
                    "last_seen_at": seen_at,
                    "extractor_version": EXTRACTOR_VERSION,
                    "alias_version": vocabulary.version,
                    # Where it was found, so an observation can be read back
                    # against the posting rather than taken on trust.
                    "evidence": {"spans": [list(span) for span in observation.spans]},
                }
                for surface_form, observation in plan.observations.items()
            ]
        )
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_job_skill_mentions_job_surface_extractor_alias",
                set_={
                    # Recomputed from the text, never incremented: an unchanged
                    # posting seen a hundred times still occurs as often as it
                    # is written.
                    "occurrences": statement.excluded.occurrences,
                    "normalized_form": statement.excluded.normalized_form,
                    "evidence": statement.excluded.evidence,
                    # first_seen_at is deliberately absent: an observation keeps
                    # the moment it was first made. last_seen_at only ever moves
                    # forward, so a clock that goes backwards cannot rewind it.
                    "last_seen_at": func.greatest(
                        JobSkillMention.last_seen_at, statement.excluded.last_seen_at
                    ),
                },
            )
        )

    kept = [
        (surface_form, EXTRACTOR_VERSION, vocabulary.version) for surface_form in plan.observations
    ]
    prune = delete(JobSkillMention).where(JobSkillMention.job_id == job_id)
    if kept:
        prune = prune.where(
            tuple_(
                JobSkillMention.surface_form,
                JobSkillMention.extractor_version,
                JobSkillMention.alias_version,
            ).not_in(kept)
        )
    await session.execute(prune)

    return plan.counts
