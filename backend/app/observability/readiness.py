"""Whether this process can actually serve, as opposed to whether it is alive.

Two different questions, and conflating them is how a deploy either never
becomes ready or is declared ready while its database is unreachable.

**Liveness** asks whether the process should be restarted. It touches nothing
external, because a dependency being down is not a reason to kill a healthy
process — and a liveness probe that talks to the database turns one outage into
a restart loop.

**Readiness** asks whether traffic should be sent here, so it does check the
dependencies a request needs. Every check is bounded: a probe that hangs is
worse than one that fails, because a failing probe is an answer.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from anyio import to_thread
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("app.readiness")

# Long enough to survive a slow query, short enough that a probe answers within
# any sensible probe interval.
CHECK_TIMEOUT_SECONDS = 2.0


class DependencyState(StrEnum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class DependencyReport:
    """One dependency, and why it is not usable if it is not.

    The reason is a fixed phrase this module chose, never the underlying error.
    A driver's message carries the connection string, and a readiness endpoint
    is the one thing in an application that is reachable before anything has
    authenticated.
    """

    name: str
    state: DependencyState
    reason: str | None = None


async def _bounded(name: str, check: Callable[[], Awaitable[None]]) -> DependencyReport:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await check()
    except TimeoutError:
        logger.warning("readiness check timed out", extra={"dependency": name})
        return DependencyReport(name=name, state=DependencyState.DOWN, reason="timed out")
    except Exception:
        # Logged with the traceback, reported without it.
        logger.warning("readiness check failed", extra={"dependency": name}, exc_info=True)
        return DependencyReport(name=name, state=DependencyState.DOWN, reason="unavailable")
    return DependencyReport(name=name, state=DependencyState.UP)


async def check_database(engine: AsyncEngine) -> DependencyReport:
    """Whether a connection can be taken and a statement run on it.

    `SELECT 1` rather than a table read: this asks whether the database is
    reachable and accepting work, not whether a migration has run.
    """

    async def probe() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    return await _bounded("database", probe)


async def check_storage(root: Path) -> DependencyReport:
    """Whether uploaded CVs can still be written where they are kept.

    Writing, not just existing. A directory that is present and read-only fails
    the first upload and passes any check that only looks.
    """

    def probe() -> None:
        root.mkdir(parents=True, exist_ok=True)
        marker = root / ".readiness"
        marker.write_bytes(b"")
        marker.unlink()

    return await _bounded("cv_storage", lambda: to_thread.run_sync(probe))
