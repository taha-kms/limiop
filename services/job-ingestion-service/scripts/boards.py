"""An operator's tool for the board registry: list, add, block, unblock, reactivate.

Discovery guesses and probes at a budget; a person is what overrules it.
`add` pins a board the way a verified discovery would, on the operator's own
say. `block` refuses a slug so a known-bad guess is never tried again, and
creates the row itself so a slug discovery never reached can still be
refused. `reactivate` puts a board retired by repeated poll failures back
into the walk once a person has learned it answers again. Neither `list`,
`add`, `block`, nor `unblock` reaches the network: verifying a board by hand
is the operator's job, and this script's is only to record the decision.

The logic lives in `job_ingestion.boards.operator` and
`job_ingestion.boards.lifecycle`, so it is testable without a subprocess;
this script is the thin command line over it.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from platform_db.models import JobSource
from platform_db.models.boards import JobBoard
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from job_ingestion.boards.lifecycle import reactivate
from job_ingestion.boards.operator import add_board, as_row, block_board, list_boards, unblock_board
from job_ingestion.boards.registry import provider_for
from job_ingestion.config import get_settings
from job_ingestion.database import Database


async def run_list(database: Database, source_key: str) -> object:
    provider = provider_for(source_key)
    async with database.session() as session:
        return await list_boards(session, provider)


async def run_add(database: Database, source_key: str, slug: str) -> object:
    provider = provider_for(source_key)
    settings = get_settings()
    async with database.session() as session:
        board = await add_board(session, provider, settings, slug)
        await session.commit()
        return as_row(board)


async def run_block(database: Database, source_key: str, slug: str) -> object:
    provider = provider_for(source_key)
    settings = get_settings()
    async with database.session() as session:
        board = await block_board(session, provider, settings, slug)
        await session.commit()
        return as_row(board)


async def run_unblock(database: Database, source_key: str, slug: str) -> object:
    provider = provider_for(source_key)
    async with database.session() as session:
        board = await unblock_board(session, provider, slug)
        await session.commit()
        return as_row(board)


async def run_reactivate(database: Database, source_key: str, slug: str) -> object:
    # Not used beyond validating the source key: reactivate does not need a
    # provider, but a typo'd --source should fail the way every other
    # command's does, rather than silently reactivating nothing.
    provider_for(source_key)
    async with database.session() as session:
        changed = await reactivate(session, source_key=source_key, slug=slug)
        statement = (
            select(JobBoard)
            .join(JobSource, JobBoard.source_id == JobSource.id)
            .options(selectinload(JobBoard.company))
            .where(JobSource.key == source_key, JobBoard.slug == slug)
        )
        board = (await session.scalars(statement)).one()
        await session.commit()
        return {**as_row(board), "reactivated": changed}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("list", "add", "block", "unblock", "reactivate"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--source", required=True, help="registered board provider key")
        if name != "list":
            subparser.add_argument("slug")

    return parser.parse_args(argv)


COMMANDS: dict[str, Callable[[Database, str, str], Coroutine[Any, Any, object]]] = {
    "add": run_add,
    "block": run_block,
    "unblock": run_unblock,
    "reactivate": run_reactivate,
}


def main() -> None:
    arguments = parse_args()
    database = Database(arguments.database_url)
    try:
        if arguments.command == "list":
            result = asyncio.run(run_list(database, arguments.source))
        else:
            result = asyncio.run(
                COMMANDS[arguments.command](database, arguments.source, arguments.slug)
            )
    finally:
        asyncio.run(database.dispose())

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
