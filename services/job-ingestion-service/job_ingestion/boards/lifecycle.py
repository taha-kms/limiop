"""What one poll does to the boards it touched.

A board is not read forever just because it was found once. Every poll
writes back what happened to the row it came from: when it was checked,
how many postings it had, and whether it answered at all. Three polls in a
row that do not answer take the board out of the walk, because a board that
keeps failing is indistinguishable from one that closed, and asking a dead
address every run wastes the budget every other board depends on.

Retiring a board here does not retire its postings. It only takes the board
out of the next walk; the walk that follows can still be exhausted (the
board is simply absent from it), and it is the existing per-source
reconciliation, run after every walk, that concludes from that absence that
the board's provenance should be retired and withdraws any job no other
source still lists. Nothing here decides that; it only makes the walk
capable of concluding it.

Pinned rows are the exception: an operator decided a board belongs, so a
failing pin is reported, never demoted. Reactivation is the way back, run by
whoever learns the board answers again.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from platform_db.models import JobSource
from platform_db.models.boards import BoardStatus, JobBoard
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.boards.client import BoardOutcome

INACTIVE_AFTER_FAILURES = 3


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    """What one poll recorded on the registry."""

    polled: int
    retired: tuple[str, ...]
    reactivated: tuple[str, ...] = ()


async def _boards_by_slug(
    session: AsyncSession, source_key: str, slugs: Sequence[str]
) -> dict[str, JobBoard]:
    statement = (
        select(JobBoard)
        .join(JobSource, JobBoard.source_id == JobSource.id)
        .where(JobSource.key == source_key, JobBoard.slug.in_(slugs))
    )
    boards = (await session.scalars(statement)).all()
    return {board.slug: board for board in boards}


def _revived_status(board: JobBoard) -> BoardStatus:
    """The status a board answering again earns back.

    Confirmed only if the row's evidence still names a company (evidence
    kind other than operator and company_id set) or the row is pinned;
    otherwise candidate, so it is verified again before it is polled.
    Shared by `record_poll`, when an explicit poll succeeds against an
    inactive row, and by `reactivate`.
    """
    named_by_evidence = (
        board.evidence is not None
        and board.evidence.get("kind") != "operator"
        and board.company_id is not None
    )
    return BoardStatus.CONFIRMED if (named_by_evidence or board.pinned) else BoardStatus.CANDIDATE


async def record_poll(
    session: AsyncSession,
    *,
    source_key: str,
    outcomes: Sequence[BoardOutcome],
    polled_at: datetime,
    inactive_after: int = INACTIVE_AFTER_FAILURES,
) -> LifecycleResult:
    """Write one poll's outcomes back onto the registry.

    A slug with no row is skipped: an explicit `BoardConfig` (a test, or an
    operator running one board by hand) can name a board the registry has
    never heard of, and there is nothing to update. `polled` counts only the
    outcomes that matched a row, since a skipped slug was not, in any sense
    the registry can record, polled.

    An explicit `BoardConfig` can also name a board that is already
    `inactive`, bypassing the registry's own read of what to walk. A
    success there means the board answers again, so it is revived the same
    way `reactivate` would, and reported in `reactivated` rather than left
    looking healthy while still out of the walk.
    """
    if not outcomes:
        return LifecycleResult(polled=0, retired=())

    boards = await _boards_by_slug(session, source_key, [outcome.slug for outcome in outcomes])
    retired: list[str] = []
    reactivated: list[str] = []
    polled = 0
    for outcome in outcomes:
        board = boards.get(outcome.slug)
        if board is None:
            continue
        polled += 1
        board.last_polled_at = polled_at
        if outcome.failure is None:
            board.last_posting_count = outcome.records
            board.consecutive_failures = 0
            if board.status is BoardStatus.INACTIVE:
                board.status = _revived_status(board)
                reactivated.append(board.slug)
            continue
        board.consecutive_failures += 1
        if (
            not board.pinned
            and board.consecutive_failures >= inactive_after
            and board.status is not BoardStatus.INACTIVE
        ):
            board.status = BoardStatus.INACTIVE
            retired.append(board.slug)

    await session.flush()
    return LifecycleResult(polled=polled, retired=tuple(retired), reactivated=tuple(reactivated))


async def reactivate(session: AsyncSession, *, source_key: str, slug: str) -> bool:
    """Put an inactive board back into the walk. Returns whether a row changed.

    Called by whoever learns the board answers again: discovery, or an
    operator.
    """
    boards = await _boards_by_slug(session, source_key, [slug])
    board = boards.get(slug)
    if board is None or board.status is not BoardStatus.INACTIVE:
        return False

    board.status = _revived_status(board)
    board.consecutive_failures = 0
    await session.flush()
    return True
