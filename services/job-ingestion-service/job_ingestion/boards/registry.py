"""Every tenant-board provider the service can read.

Listed rather than discovered by import, so adding a provider is one visible
line and the scheduler emits exactly the DAGs this tuple names.
"""

from typing import Any

from job_ingestion.boards.provider import BoardProvider
from job_ingestion.greenhouse.provider import GREENHOUSE

PROVIDERS: tuple[BoardProvider[Any], ...] = (GREENHOUSE,)


def provider_for(source_key: str) -> BoardProvider[Any]:
    for provider in PROVIDERS:
        if provider.source_key == source_key:
            return provider
    raise ValueError(f"no board provider named {source_key}")
