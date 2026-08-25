import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete

from app.db.session import Database
from app.modules.skills.models import SkillAliasVersion, SkillConcept, SkillSurfaceForm

BACKEND_ROOT = Path(__file__).resolve().parents[2]
V2 = "2026.08.25.1"

pytestmark = pytest.mark.integration


def run_command(database_url: PostgresDsn) -> str:
    environment = os.environ.copy()
    environment["SKILLSYNC_DATABASE_URL"] = str(database_url)
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.load_alias_table", "--vocabulary-version", V2],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_command_loads_a_version_then_reports_the_no_op(database_url: PostgresDsn) -> None:
    async def clear() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(SkillSurfaceForm))
                await session.execute(delete(SkillAliasVersion))
                await session.execute(delete(SkillConcept))
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(clear())
    try:
        assert run_command(database_url) == (
            f"loaded alias table {V2}: 56 concepts, 182 surface forms"
        )
        assert run_command(database_url) == f"alias table {V2} is already loaded"
    finally:
        asyncio.run(clear())
