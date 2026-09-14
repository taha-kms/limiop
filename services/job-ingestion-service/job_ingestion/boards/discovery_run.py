"""One scheduled pass that guesses, verifies, and registers boards.

Discovery used to be a report a person read; this is the run that writes what
it found onto the registry, with a budget bounding how many companies one run
probes and a cadence deciding when a settled row is worth asking about again.
The rest of the registry's safety property carries over unchanged: a wrong
guess costs one request and is stored as what it was, not silently retried.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import httpx2
from platform_db.models import Company, Job, JobSource
from platform_db.models.boards import BoardStatus, JobBoard
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import (
    DiscoveryOutcome,
    DiscoveryResult,
    candidate_slugs,
    discover,
)
from job_ingestion.boards.lifecycle import _revived_status
from job_ingestion.boards.pipeline import configured_base_url
from job_ingestion.boards.provider import BoardProvider, Verification
from job_ingestion.config import Settings, get_settings
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration, ensure_source
from job_ingestion.pipeline import utc_now

logger = logging.getLogger(__name__)

# A company with any row in one of these states, for this provider, is
# excluded from `due_companies` entirely: an operator or a wrong-company
# decision already settled it, and this run has nothing to add.
_NEVER_DUE = frozenset({BoardStatus.BLOCKED, BoardStatus.WRONG_COMPANY})

# A row `register` must never write over, whatever the new probe found.
_SETTLED_STATUSES = frozenset({BoardStatus.BLOCKED, BoardStatus.WRONG_COMPANY})

# A row in one of these states has been proven to belong to whoever it is
# keyed on. Owned by a *different* company than the one being registered, it
# is just as settled as `_SETTLED_STATUSES` and must not be reassigned.
# Owned by the same company, none of this applies. A row in any other state
# (not_found, unreachable, candidate, inactive) is unproven and may still be
# re-keyed to whoever a later probe actually confirms.
_OWNED_STATUSES = frozenset({BoardStatus.CONFIRMED, BoardStatus.NAMED})

# `register`'s return values that a run tallies into its summary.
_TALLIED_OUTCOMES = (
    "confirmed",
    "named",
    "wrong_company",
    "unverifiable",
    "not_found",
    "unreachable",
    "reactivated",
    "unchanged",
)


@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    """Bounds and cadence for one discovery run."""

    budget: int = 200  # companies probed per run
    politeness_seconds: float = 0.5  # pause between companies
    recheck_not_found: timedelta = timedelta(days=7)
    recheck_verified: timedelta = timedelta(days=30)  # confirmed and named
    recheck_inactive: timedelta = timedelta(days=7)
    # unreachable and candidate rows are due on the next run

    def __post_init__(self) -> None:
        if self.budget < 1:
            raise ValueError("budget must be at least 1")
        if self.politeness_seconds < 0:
            raise ValueError("politeness_seconds must not be negative")


@dataclass(frozen=True, slots=True)
class DiscoverySummary:
    """What one discovery run found and wrote."""

    source_key: str
    seeded: int  # companies that were due
    probed: int = 0
    confirmed: int = 0
    named: int = 0  # a board states a matching name with no outside evidence
    wrong_company: int = 0
    unverifiable: int = 0
    not_found: int = 0
    unreachable: int = 0
    reactivated: int = 0
    unchanged: int = 0  # a settled row, owned by another company, left alone
    skipped_nameless: int = 0  # companies whose name yields no candidate slug
    stopped_at_budget: bool = False


def _cadence(status: BoardStatus, config: DiscoveryConfig) -> timedelta | None:
    """How long a decided row stands before it is worth guessing about again.

    `None` means the row is due on the next run regardless of when it was
    last checked: an unverifiable guess stored as `candidate`, or a probe
    that could not even reach the provider.
    """
    if status is BoardStatus.NOT_FOUND:
        return config.recheck_not_found
    if status in (BoardStatus.CONFIRMED, BoardStatus.NAMED):
        return config.recheck_verified
    if status is BoardStatus.INACTIVE:
        return config.recheck_inactive
    return None


def _row_is_due(board: JobBoard, config: DiscoveryConfig, now: datetime) -> bool:
    cadence = _cadence(board.status, config)
    if cadence is None or board.last_checked_at is None:
        return True
    return board.last_checked_at + cadence <= now


def _company_is_due(boards: Sequence[JobBoard], config: DiscoveryConfig, now: datetime) -> bool:
    if not boards:
        return True
    if any(board.pinned or board.status in _NEVER_DUE for board in boards):
        return False
    return all(_row_is_due(board, config, now) for board in boards)


async def due_companies(
    session: AsyncSession, *, source_key: str, config: DiscoveryConfig, now: datetime
) -> list[Company]:
    """Companies worth guessing about again this run, ranked by stored jobs.

    A company with no row for this provider is always due. A company whose
    rows are all past their cadence is due for a recheck. A company with any
    pinned, blocked, or wrong-company row is excluded entirely. No limit is
    applied here; the budget is the run's job.
    """
    job_counts = (
        select(Job.company_id, func.count(Job.id).label("job_count"))
        .group_by(Job.company_id)
        .subquery()
    )
    companies_statement = (
        select(Company)
        .outerjoin(job_counts, job_counts.c.company_id == Company.id)
        .order_by(func.coalesce(job_counts.c.job_count, 0).desc(), Company.display_name)
    )
    companies = list((await session.scalars(companies_statement)).all())

    boards_statement = (
        select(JobBoard)
        .join(JobSource, JobBoard.source_id == JobSource.id)
        .where(JobSource.key == source_key, JobBoard.company_id.is_not(None))
    )
    boards_by_company: dict[UUID, list[JobBoard]] = {}
    for row in (await session.scalars(boards_statement)).all():
        assert row.company_id is not None  # filtered above
        boards_by_company.setdefault(row.company_id, []).append(row)

    return [
        company
        for company in companies
        if _company_is_due(boards_by_company.get(company.id, ()), config, now)
    ]


async def _existing_board(session: AsyncSession, source_id: UUID, slug: str) -> JobBoard | None:
    statement = select(JobBoard).where(JobBoard.source_id == source_id, JobBoard.slug == slug)
    return (await session.scalars(statement)).one_or_none()


async def _skip_slugs(session: AsyncSession, source_id: UUID) -> set[str]:
    """Slugs already known to belong to somebody else, or blocked by an
    operator, for this source. Never worth a probe or a re-guess."""
    statement = select(JobBoard.slug).where(
        JobBoard.source_id == source_id,
        JobBoard.status.in_((BoardStatus.WRONG_COMPANY, BoardStatus.BLOCKED)),
    )
    return set((await session.scalars(statement)).all())


async def register(
    session: AsyncSession,
    *,
    source: JobSource,
    company: Company,
    result: DiscoveryResult,
    now: datetime,
    skip: Collection[str] = (),
    client: BoardClient | None = None,
) -> str:
    """Write one probe's outcome onto the registry. Returns what happened:
    confirmed, named, wrong_company, unverifiable, not_found, unreachable,
    reactivated, or unchanged when an already-settled row was left alone.

    A feed that states nothing (`result.outcome` is `UNVERIFIABLE`) gets one
    more chance: when `client` is given and its provider has a `verify`
    hook, that is called with the slug this probe would otherwise register,
    and its answer — `CONFIRMED`, `NAMED`, `WRONG_COMPANY`, or still
    `UNVERIFIABLE` — is written instead, evidence and all. Without a
    `client`, or a provider that cannot verify beyond its feed, this behaves
    exactly as before.

    Never modifies a row that is pinned, blocked, already `wrong_company`, or
    `confirmed`/`named` for a *different* company: a decision an operator, an
    earlier probe, or an earlier confirmation already made outranks a fresh
    guess, whatever this company's name happens to produce. Without this, two
    companies whose names guess the same slug would fight over it, and the
    row's `company_id` would ping-pong between them on every run that probes
    both. A row that is `not_found`, `unreachable`, `candidate`, or `inactive`
    for another company is unproven rather than settled, and may still be
    re-keyed to whoever a later probe actually confirms.

    A company whose only candidate is owned by a different, settled company
    has no row of its own to become not-due, so `due_companies` marks it due
    again every run: this returns `unchanged` before ever probing further,
    but the probe itself still happens and still costs one budget slot each
    time. There is no automatic way out of that from here; an operator
    resolves it by blocking the slug (so it stops being guessed) or pinning
    the row (which does not change whose company_id it holds, but ends the
    argument).

    `skip` should be the same set `discover` was called with. A `NOT_FOUND`
    result carries no slug of its own, so one has to be picked to key the
    row on; it is the first candidate that was actually requested, not one
    that was skipped because it already belongs to somebody else — keying on
    a skipped slug would find that settled row, refuse to touch it, and
    leave this company with no row at all to show it was checked.
    """
    tried = [
        candidate for candidate in candidate_slugs(company.display_name) if candidate not in skip
    ]
    if result.slug is not None:
        slug = result.slug
    elif tried:
        slug = tried[0]
    else:
        # Every candidate was skipped: nothing was requested, and there is no
        # slug left to key a row on that isn't already somebody else's.
        slug = candidate_slugs(company.display_name)[0]
    board = await _existing_board(session, source.id, slug)
    owned_by_someone_else = (
        board is not None
        and board.company_id is not None
        and board.company_id != company.id
        and board.status in _OWNED_STATUSES
    )
    if board is not None and (
        board.pinned or board.status in _SETTLED_STATUSES or owned_by_someone_else
    ):
        if board.pinned:
            reason = "pinned"
        elif owned_by_someone_else:
            reason = f"{board.status.value} for a different company"
        else:
            reason = board.status.value
        logger.info(
            "not writing over board %s for %s: row is %s", slug, company.display_name, reason
        )
        return "unchanged"

    verification: Verification | None = None
    outcome_kind = result.outcome
    if (
        result.outcome is DiscoveryOutcome.UNVERIFIABLE
        and client is not None
        and client.provider.verify is not None
    ):
        verification = await client.provider.verify(client, slug, company)
        outcome_kind = verification.outcome

    if board is None:
        board = JobBoard(source_id=source.id, slug=slug)
        session.add(board)

    board.company_id = company.id
    board.last_checked_at = now

    if outcome_kind is DiscoveryOutcome.CONFIRMED:
        was_inactive = board.status is BoardStatus.INACTIVE
        board.evidence = (
            dict(verification.evidence)
            if verification is not None
            else {
                "kind": "provider_name",
                "found_company": result.found_company,
                "checked_at": now.isoformat(),
            }
        )
        board.verified_at = now
        if was_inactive:
            board.status = _revived_status(board)
            board.consecutive_failures = 0
            outcome = "reactivated"
        else:
            board.status = BoardStatus.CONFIRMED
            outcome = "confirmed"
    elif outcome_kind is DiscoveryOutcome.NAMED:
        assert verification is not None  # only a provider's verify() reports NAMED
        board.status = BoardStatus.NAMED
        board.evidence = dict(verification.evidence)
        board.verified_at = now
        outcome = "named"
    elif outcome_kind is DiscoveryOutcome.WRONG_COMPANY:
        board.status = BoardStatus.WRONG_COMPANY
        board.evidence = (
            dict(verification.evidence)
            if verification is not None
            else {"kind": "provider_name", "found_company": result.found_company}
        )
        outcome = "wrong_company"
    elif outcome_kind is DiscoveryOutcome.UNVERIFIABLE:
        board.status = BoardStatus.CANDIDATE
        board.evidence = (
            dict(verification.evidence)
            if verification is not None
            else {"kind": "unverified", "checked_at": now.isoformat()}
        )
        outcome = "unverifiable"
    elif outcome_kind is DiscoveryOutcome.NOT_FOUND:
        board.status = BoardStatus.NOT_FOUND
        board.evidence = {"kind": "not_found", "tried": tried or [slug]}
        outcome = "not_found"
    else:
        board.status = BoardStatus.UNREACHABLE
        board.evidence = {"kind": "unreachable"}
        outcome = "unreachable"

    await session.flush()
    return outcome


async def run_discovery(
    database: Database,
    provider: BoardProvider[Any],
    *,
    config: DiscoveryConfig,
    settings: Settings,
    http_client: httpx2.AsyncClient | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now: Callable[[], datetime] = utc_now,
) -> DiscoverySummary:
    """Guess, verify, and register boards for one provider's due companies."""
    moment = now()
    tallies = dict.fromkeys(_TALLIED_OUTCOMES, 0)
    probed = 0
    skipped_nameless = 0
    stopped_at_budget = False

    async with database.session() as session:
        due = await due_companies(
            session, source_key=provider.source_key, config=config, now=moment
        )
        seeded = len(due)

        source = await ensure_source(
            session,
            SourceRegistration(
                key=provider.source_key,
                display_name=provider.display_name,
                base_url=configured_base_url(provider, settings),
                precedence=provider.precedence,
            ),
        )
        skip = await _skip_slugs(session, source.id)

        client_config = BoardConfig(boards=(), base_url=configured_base_url(provider, settings))
        async with BoardClient(
            provider, client_config, http_client=http_client, sleeper=sleeper
        ) as client:
            for company in due:
                if probed >= config.budget:
                    stopped_at_budget = True
                    break
                if not candidate_slugs(company.display_name):
                    skipped_nameless += 1
                    continue

                # Paces one probe against the next, never after the last:
                # nothing is waiting to be polite before once this run is
                # about to make its final request.
                if probed > 0:
                    await sleeper(config.politeness_seconds)

                result = await discover(client, company.display_name, skip=skip)
                probed += 1
                outcome = await register(
                    session,
                    source=source,
                    company=company,
                    result=result,
                    now=moment,
                    skip=skip,
                    client=client,
                )
                if outcome in tallies:
                    tallies[outcome] += 1

        await session.commit()

    return DiscoverySummary(
        source_key=provider.source_key,
        seeded=seeded,
        probed=probed,
        confirmed=tallies["confirmed"],
        named=tallies["named"],
        wrong_company=tallies["wrong_company"],
        unverifiable=tallies["unverifiable"],
        not_found=tallies["not_found"],
        unreachable=tallies["unreachable"],
        reactivated=tallies["reactivated"],
        unchanged=tallies["unchanged"],
        skipped_nameless=skipped_nameless,
        stopped_at_budget=stopped_at_budget,
    )


async def discover_boards(
    provider: BoardProvider[Any],
    *,
    config: DiscoveryConfig | None = None,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> DiscoverySummary:
    """Run one complete discovery pass against the configured database.

    Mirrors `boards.pipeline.ingest_board_source`: this registers what it
    verified, and nothing is polled that was not.
    """
    app_settings = settings if settings is not None else get_settings()
    resolved_config = config if config is not None else DiscoveryConfig()
    database = Database(app_settings.database_url)
    try:
        summary = await run_discovery(
            database,
            provider,
            config=resolved_config,
            settings=app_settings,
            http_client=http_client,
        )
        logger.info("discovery for %s: %s", provider.source_key, summary)
        return summary
    finally:
        await database.dispose()
