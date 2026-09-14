"""A previously verified board is re-probed on its own cadence, and a
recheck of a decision already trusted is written differently from a first
guess (issue #337). See `discovery_run.register` for the full rule; these
are the integration-level cases that exercise it end to end, through
`run_discovery`, with fake providers standing in for a real one.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from platform_db.models import Company
from platform_db.models.boards import BoardStatus, JobBoard
from pydantic import PostgresDsn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.boards.client import BoardClient
from job_ingestion.boards.discovery import DiscoveryOutcome
from job_ingestion.boards.discovery_run import DiscoveryConfig, due_companies, run_discovery
from job_ingestion.boards.operator import list_boards
from job_ingestion.boards.provider import Verification
from job_ingestion.boards.registered import polled_slugs
from job_ingestion.config import Environment, Settings
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration, ensure_source
from tests.boards.fakes import FAKE_BASE_URL, json_provider, never_sleeps, never_states, ok, routing
from tests.support.catalog import with_empty_catalog


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


def board(company: str) -> httpx2.Response:
    return ok({"jobs": [{"id": 1, "title": "Engineer", "company": company}]})


async def make_company(session: AsyncSession, name: str) -> Company:
    company = Company(display_name=name)
    session.add(company)
    await session.flush()
    return company


async def add_board_row(
    session: AsyncSession, *, slug: str, company_id: Any = None, **fields: Any
) -> JobBoard:
    source = await ensure_source(
        session, SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL)
    )
    fields.setdefault("status", BoardStatus.CONFIRMED)
    row = JobBoard(source_id=source.id, slug=slug, company_id=company_id, **fields)
    session.add(row)
    await session.flush()
    return row


def verifying_provider(verify: Any) -> Any:
    """A JSON board provider whose feed states nothing, so every guess that
    answers reaches `verify` instead of confirming on its own — the shape a
    recheck against Pinpoint's identity/corroboration layer takes."""
    return json_provider(stated_company=never_states, verify=verify)


OLD = timedelta(days=45)  # comfortably past `recheck_verified` (30 days)


# --- confirmed/named rows reverified on their cadence ------------------------


@pytest.mark.integration
def test_a_confirmed_row_that_confirms_again_is_reverified(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                consecutive_failures=0,
                evidence={
                    "kind": "provider_name",
                    "found_company": "Acme",
                    "checked_at": (moment - OLD).isoformat(),
                },
            )
            await session.commit()

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.seeded == 1
        assert summary.reverified == 1
        assert summary.confirmed == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.verified_at == moment
        assert row.evidence is not None
        assert row.evidence["kind"] == "provider_name"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_named_row_that_now_confirms_is_upgraded_and_reverified(
    database_url: PostgresDsn,
) -> None:
    """A `named` row's evidence was only ever a stated name. A recheck that
    now corroborates it (a Pinpoint board's own site, in production) is
    stronger evidence, so the row is upgraded to `confirmed` rather than
    just renewed as `named`."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.NAMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={"kind": "site_title", "checked_at": (moment - OLD).isoformat()},
            )
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company="Acme",
                evidence={"kind": "website_link", "url": "https://acme.example/careers"},
            )

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.reverified == 1
        assert summary.confirmed == 0
        assert summary.named == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.evidence is not None
        assert row.evidence["kind"] == "website_link"
        assert row.verified_at == moment

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_confirmed_row_that_verify_only_names_is_not_downgraded(
    database_url: PostgresDsn,
) -> None:
    """The reverse of the upgrade above: `confirmed` evidence is stronger
    than a bare naming, so a recheck that only manages to name the company
    again keeps the row `confirmed` rather than downgrading it to `named`."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={
                    "kind": "website_link",
                    "url": "https://acme.example/careers",
                },
            )
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.NAMED,
                found_company="Acme",
                evidence={"kind": "site_title", "checked_at": moment.isoformat()},
            )

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.reverified == 1
        assert summary.named == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.evidence is not None
        assert row.evidence["kind"] == "site_title"

    run_database_test(database_url, exercise)


# --- a silent recheck does not demote a verified row -------------------------


@pytest.mark.integration
def test_a_confirmed_row_that_404s_is_left_alone_but_noted(database_url: PostgresDsn) -> None:
    """One recheck that cannot reach the board is not evidence it moved; the
    poll lifecycle (#332), not discovery, is what retires a board that
    actually stops answering."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={
                    "kind": "provider_name",
                    "found_company": "Acme",
                    "checked_at": (moment - OLD).isoformat(),
                },
            )
            await session.commit()

        transport = routing({"/acme/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.unchanged == 1
        assert summary.not_found == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            slugs = await polled_slugs(session, "fake")

        assert row.status is BoardStatus.CONFIRMED
        assert row.evidence is not None
        assert row.evidence["kind"] == "provider_name"  # the original evidence, untouched
        assert row.evidence["last_recheck"] == {
            "kind": "not_found",
            "checked_at": moment.isoformat(),
        }
        assert slugs == ("acme",)

    run_database_test(database_url, exercise)


# --- a board that now answers for somebody else is believed immediately ----


@pytest.mark.integration
def test_a_confirmed_row_that_now_answers_for_somebody_else_is_demoted(
    database_url: PostgresDsn,
) -> None:
    """A board answering for somebody else is the one outcome the registry
    exists to catch, however settled the row looked a moment ago: it is
    believed immediately, not given the benefit of the doubt a silent
    recheck gets."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={
                    "kind": "provider_name",
                    "found_company": "Acme",
                    "checked_at": (moment - OLD).isoformat(),
                },
            )
            await session.commit()

        transport = routing({"/acme/jobs": board("Globex")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.demoted == 1
        assert summary.wrong_company == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            slugs = await polled_slugs(session, "fake")

        assert row.status is BoardStatus.WRONG_COMPANY
        assert row.company_id == company.id
        assert row.evidence is not None
        assert row.evidence["found_company"] == "Globex"
        assert slugs == ()

    run_database_test(database_url, exercise)


# --- a feed that stops stating a company demotes what it can no longer back -


@pytest.mark.integration
def test_a_confirmed_row_gone_unverifiable_is_demoted_to_named(database_url: PostgresDsn) -> None:
    """`provider_name` evidence is itself just a stated name: if the feed
    stops stating one, the row is only as good as `named` was ever going to
    be, not thrown all the way back to an unverified guess."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={
                    "kind": "provider_name",
                    "found_company": "Acme",
                    "checked_at": (moment - OLD).isoformat(),
                },
            )
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.UNVERIFIABLE,
                found_company=None,
                evidence={"kind": "unverified", "checked_at": moment.isoformat()},
            )

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.demoted == 1

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.NAMED
        assert row.evidence is not None
        assert row.evidence["kind"] == "unverified"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_confirmed_row_gone_unverifiable_with_no_stated_name_is_demoted_to_candidate(
    database_url: PostgresDsn,
) -> None:
    """The other half of the demotion rule: evidence that was never just a
    stated name (`website_link`, from corroboration) gives up nothing worth
    keeping once the feed and `verify` both come up empty, so the row goes
    all the way back to `candidate` and drops out of the walk."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={"kind": "website_link", "url": "https://acme.example/careers"},
            )
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.UNVERIFIABLE,
                found_company=None,
                evidence={"kind": "unverified", "checked_at": moment.isoformat()},
            )

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.demoted == 1

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            slugs = await polled_slugs(session, "fake")

        assert row.status is BoardStatus.CANDIDATE
        assert row.evidence is not None
        assert row.evidence["kind"] == "unverified"
        assert slugs == ()

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_confirmed_row_that_becomes_unreachable_is_left_alone_but_noted(
    database_url: PostgresDsn,
) -> None:
    """The `unreachable` twin of the 404 case above: a connection failure on
    a recheck is just as silent as a 404 one, and must not demote the row
    either."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - OLD,
                last_checked_at=moment - OLD,
                evidence={
                    "kind": "provider_name",
                    "found_company": "Acme",
                    "checked_at": (moment - OLD).isoformat(),
                },
            )
            await session.commit()

        transport = routing({"/acme/jobs": httpx2.ConnectError("could not connect")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.unchanged == 1
        assert summary.unreachable == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            slugs = await polled_slugs(session, "fake")

        assert row.status is BoardStatus.CONFIRMED
        assert row.evidence is not None
        assert row.evidence["last_recheck"] == {
            "kind": "unreachable",
            "checked_at": moment.isoformat(),
        }
        assert slugs == ("acme",)

    run_database_test(database_url, exercise)


# --- a pinned row is reported, never rewritten -------------------------------


@pytest.mark.integration
def test_a_pinned_row_is_reported_monthly_and_never_modified(database_url: PostgresDsn) -> None:
    """A pinned row is due on `recheck_verified` like a confirmed row (so it
    is not silently left unchecked forever), but whatever the probe finds —
    even a board that now answers for somebody else — only
    `evidence["last_recheck"]` and `last_checked_at` are written."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        original_verified_at = moment - OLD
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                pinned=True,
                verified_at=original_verified_at,
                last_checked_at=moment - OLD,
                evidence={"kind": "operator", "checked_at": (moment - OLD).isoformat()},
            )
            await session.commit()

            due = await due_companies(
                session, source_key="fake", config=DiscoveryConfig(), now=moment
            )
        assert [row.id for row in due] == [company.id]

        transport = routing({"/acme/jobs": board("Somebody Else")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.seeded == 1
        assert summary.pinned_reported == 1
        assert summary.wrong_company == 0
        assert summary.confirmed == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.pinned is True
        assert row.company_id == company.id
        assert row.verified_at == original_verified_at
        assert row.last_checked_at == moment
        assert row.evidence is not None
        assert row.evidence["last_recheck"] == {
            "kind": "wrong_company",
            "checked_at": moment.isoformat(),
        }

    run_database_test(database_url, exercise)


# --- inactive rows: requirement #2 --------------------------------------------


@pytest.mark.integration
def test_an_inactive_row_older_than_a_week_that_confirms_is_reactivated(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.INACTIVE,
                consecutive_failures=3,
                evidence={"kind": "provider_name", "found_company": "Acme"},
                last_checked_at=moment - timedelta(days=10),
            )
            await session.commit()

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.reactivated == 1

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_inactive_row_older_than_a_week_that_404s_is_not_found(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.INACTIVE,
                consecutive_failures=3,
                evidence={"kind": "provider_name", "found_company": "Acme"},
                last_checked_at=moment - timedelta(days=10),
            )
            await session.commit()

        transport = routing({"/acme/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.not_found == 1
        assert summary.reactivated == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.NOT_FOUND

    run_database_test(database_url, exercise)


# --- a fresh row is left alone entirely --------------------------------------


@pytest.mark.integration
def test_a_one_day_old_confirmed_row_is_not_seeded(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        moment = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                verified_at=moment - timedelta(days=1),
                last_checked_at=moment - timedelta(days=1),
            )
            await session.commit()

            due = await due_companies(
                session, source_key="fake", config=DiscoveryConfig(), now=moment
            )

        assert due == []

    run_database_test(database_url, exercise)


# --- operator visibility: filtering the listing by status -------------------


@pytest.mark.integration
def test_list_boards_filtered_by_status_returns_only_that_status(
    database_url: PostgresDsn,
) -> None:
    """An operator checking on `named` boards — the ones re-verification can
    still upgrade — should not have to read past every `confirmed` row to
    find them."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            named = await make_company(session, "Named Co")
            confirmed = await make_company(session, "Confirmed Co")
            await add_board_row(
                session, slug="named-co", company_id=named.id, status=BoardStatus.NAMED
            )
            await add_board_row(
                session,
                slug="confirmed-co",
                company_id=confirmed.id,
                status=BoardStatus.CONFIRMED,
            )
            await session.commit()

            rows = await list_boards(session, json_provider(), status=BoardStatus.NAMED)

        assert [row["slug"] for row in rows] == ["named-co"]

    run_database_test(database_url, exercise)
