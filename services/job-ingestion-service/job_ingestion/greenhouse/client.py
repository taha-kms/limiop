"""Greenhouse's client, kept as an import path over the generic one.

Everything a Greenhouse client does is what any tenant-board client does with
the Greenhouse provider. The names survive because the discovery script and
the tests use them, and because a caller that only wants Greenhouse should
not have to know about the registry.

The surface is narrower than the old dedicated client's: `board_url` is gone,
and `http_client`/`sleeper` are keyword-only.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.greenhouse.provider import GREENHOUSE
from job_ingestion.greenhouse.source import DEFAULT_BASE_URL, SOURCE_KEY


@dataclass(frozen=True, slots=True)
class GreenhouseConfig(BoardConfig):
    """`BoardConfig` that already knows Greenhouse's host.

    The generic config leaves `base_url` unset so a deployment can name a
    regional host; Greenhouse has one host, and callers that build this
    config by hand expect it filled in.
    """

    base_url: str = DEFAULT_BASE_URL


class GreenhouseClient(BoardClient):
    """A `BoardClient` that already knows it is reading Greenhouse."""

    def __init__(
        self,
        config: GreenhouseConfig | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__(
            GREENHOUSE,
            config if config is not None else GreenhouseConfig(),
            http_client=http_client,
            sleeper=sleeper,
        )


__all__ = [
    "DEFAULT_BASE_URL",
    "SOURCE_KEY",
    "GreenhouseClient",
    "GreenhouseConfig",
]
