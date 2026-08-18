import asyncio
from collections.abc import Awaitable, Callable

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select, text

from app.db.base import Base
from app.db.session import Database
from app.modules.jobs.domain import normalize_company_name
from app.modules.jobs.models import Company


def run_database_test(
    database_url: PostgresDsn,
    test: Callable[[Database], Awaitable[None]],
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(Company))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(Company))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_company_uses_shared_metadata() -> None:
    assert Company.metadata is Base.metadata


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Acme   GmbH  ", "acme gmbh"),
        ("\uff21\uff23\uff2d\uff25\u00a0GmbH", "acme gmbh"),
        ("Straße & Söhne", "strasse & söhne"),
    ],
)
def test_normalize_company_name(value: str, expected: str) -> None:
    assert normalize_company_name(value) == expected


def test_normalize_company_name_rejects_blank_values() -> None:
    with pytest.raises(ValueError, match="non-whitespace"):
        normalize_company_name(" \t\n ")


def test_company_updates_normalized_name() -> None:
    company = Company(display_name="Acme GmbH")

    company.display_name = "  Example   S.p.A. "

    assert company.display_name == "  Example   S.p.A. "
    assert company.normalized_name == "example s.p.a."


@pytest.mark.integration
def test_companies_with_same_normalized_name_round_trip(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        companies = [
            Company(display_name="Acme GmbH"),
            Company(
                display_name="  ACME   Gmbh ",
                website_url="https://example.com",
            ),
        ]

        async with database.session() as session:
            session.add_all(companies)
            await session.commit()

        async with database.session() as session:
            stored = list(
                await session.scalars(
                    select(Company)
                    .where(Company.normalized_name == "acme gmbh")
                    .order_by(Company.display_name)
                )
            )

        assert len(stored) == 2
        assert {company.normalized_name for company in stored} == {"acme gmbh"}
        assert {company.website_url for company in stored} == {None, "https://example.com"}
        assert all(company.created_at.tzinfo is not None for company in stored)
        assert all(company.updated_at.tzinfo is not None for company in stored)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_company_normalized_name_index_exists(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            index_definition = await session.scalar(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = 'companies'
                      AND indexname = 'ix_companies_normalized_name'
                    """
                )
            )

        assert isinstance(index_definition, str)
        assert "UNIQUE" not in index_definition

    run_database_test(database_url, exercise)
