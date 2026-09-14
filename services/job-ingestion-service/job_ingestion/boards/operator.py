"""An operator's tools for the board registry: list, add, block, unblock.

Discovery guesses and probes at a budget and a schedule; this is where a
person overrules it. `add` pins a board the way a verified discovery would,
but on nobody's authority but the operator's, who looked at the board
themselves. `block` is how a wrong or unwanted slug is kept from being tried
again, and creates the row if discovery never reached it, so a known-bad
guess is never made by accident. Neither function reaches the network:
checking a slug by hand is the operator's job, and this module's is only to
record what they decided.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from platform_db.models import JobSource
from platform_db.models.boards import BoardStatus, JobBoard
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from job_ingestion.boards.pipeline import configured_base_url
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.config import Settings
from job_ingestion.persistence import SourceRegistration, ensure_source


def operator_evidence(checked_at: datetime) -> dict[str, object]:
    """What an operator's own decision looks like as evidence."""
    return {"kind": "operator", "checked_at": checked_at.isoformat()}


def as_row(board: JobBoard) -> dict[str, object]:
    """One row, in the shape the operator script prints."""
    return {
        "slug": board.slug,
        "status": board.status.value,
        "pinned": board.pinned,
        "company": board.company.display_name if board.company is not None else None,
        "evidence": board.evidence,
        "last_checked_at": board.last_checked_at.isoformat() if board.last_checked_at else None,
        "last_polled_at": board.last_polled_at.isoformat() if board.last_polled_at else None,
        "consecutive_failures": board.consecutive_failures,
    }


async def _source_for(
    session: AsyncSession, provider: BoardProvider[Any], settings: Settings
) -> JobSource:
    """The provider's source row, registered the way `boards.pipeline.build_run` does.

    `add` and `block` have to work on a database that has never run an
    ingestion, so the row cannot be assumed to already exist.
    """
    return await ensure_source(
        session,
        SourceRegistration(
            key=provider.source_key,
            display_name=provider.display_name,
            base_url=configured_base_url(provider, settings),
            precedence=provider.precedence,
        ),
    )


async def _board_for(session: AsyncSession, source_id: UUID, slug: str) -> JobBoard | None:
    statement = (
        select(JobBoard)
        .options(selectinload(JobBoard.company))
        .where(JobBoard.source_id == source_id, JobBoard.slug == slug)
    )
    return (await session.scalars(statement)).one_or_none()


async def list_boards(
    session: AsyncSession, provider: BoardProvider[Any], *, status: BoardStatus | None = None
) -> list[dict[str, object]]:
    """Every row registered for one provider, or only those at one status.

    `status` narrows the listing to rows an operator is actually looking
    for — `named`, say, to see what re-verification still has a chance to
    upgrade — instead of making them read past every other row.
    """
    statement = (
        select(JobBoard)
        .join(JobSource, JobBoard.source_id == JobSource.id)
        .options(selectinload(JobBoard.company))
        .where(JobSource.key == provider.source_key)
    )
    if status is not None:
        statement = statement.where(JobBoard.status == status)
    statement = statement.order_by(JobBoard.slug)
    boards = (await session.scalars(statement)).all()
    return [as_row(board) for board in boards]


async def add_board(
    session: AsyncSession, provider: BoardProvider[Any], settings: Settings, slug: str
) -> JobBoard:
    """Pin one board as confirmed, overriding whatever discovery decided.

    An operator overrides discovery, `wrong_company` included: the person
    looked at the board and decided it belongs where they say it does, which
    outranks a guess discovery already rejected.
    """
    source = await _source_for(session, provider, settings)
    board = await _board_for(session, source.id, slug)
    if board is None:
        board = JobBoard(source_id=source.id, slug=slug)
        session.add(board)
    checked_at = datetime.now(UTC)
    board.status = BoardStatus.CONFIRMED
    board.pinned = True
    board.verified_at = checked_at
    board.evidence = operator_evidence(checked_at)
    # A board an operator is pinning may have been retired by repeated poll
    # failures; the pin is a fresh decision, so the streak that led to that
    # retirement should not linger and immediately retire it again.
    board.consecutive_failures = 0
    await session.flush()
    return board


async def block_board(
    session: AsyncSession, provider: BoardProvider[Any], settings: Settings, slug: str
) -> JobBoard:
    """Refuse one slug, so a known-bad guess is never tried again.

    Creates the row if it is absent, so a slug nobody has guessed yet can
    still be blocked before discovery ever reaches it. `pinned` is cleared: a
    row an operator once pinned and now blocks should not still read as
    something nothing may touch.
    """
    source = await _source_for(session, provider, settings)
    board = await _board_for(session, source.id, slug)
    if board is None:
        board = JobBoard(source_id=source.id, slug=slug)
        session.add(board)
    board.status = BoardStatus.BLOCKED
    board.pinned = False
    board.evidence = operator_evidence(datetime.now(UTC))
    await session.flush()
    return board


async def unblock_board(session: AsyncSession, provider: BoardProvider[Any], slug: str) -> JobBoard:
    """Let discovery decide again about a slug an operator had blocked."""
    statement = (
        select(JobBoard)
        .join(JobSource, JobBoard.source_id == JobSource.id)
        .options(selectinload(JobBoard.company))
        .where(JobSource.key == provider.source_key, JobBoard.slug == slug)
    )
    board = (await session.scalars(statement)).one_or_none()
    if board is None:
        raise ValueError(f"no board {slug} registered for {provider.source_key}")
    board.status = BoardStatus.CANDIDATE
    await session.flush()
    return board
