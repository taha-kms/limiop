"""Load one published alias-table version into PostgreSQL."""

import argparse
import asyncio

from app.core.config import get_settings
from app.db.session import Database
from app.modules.skills.loading import AliasTableLoadResult, load_published_alias_table
from app.modules.skills.resolution import DEFAULT_VOCABULARY_VERSION


async def load(vocabulary_version: str) -> AliasTableLoadResult:
    database = Database(get_settings().database_url)
    try:
        async with database.session() as session:
            result = await load_published_alias_table(session, vocabulary_version)
            await session.commit()
            return result
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load an immutable published alias table into PostgreSQL."
    )
    parser.add_argument("--vocabulary-version", default=DEFAULT_VOCABULARY_VERSION)
    arguments = parser.parse_args()

    result = asyncio.run(load(arguments.vocabulary_version))
    if result.loaded:
        print(
            f"loaded alias table {result.vocabulary_version}: "
            f"{result.concepts_inserted} concepts, "
            f"{result.surface_forms_inserted} surface forms"
        )
    else:
        print(f"alias table {result.vocabulary_version} is already loaded")


if __name__ == "__main__":
    main()
