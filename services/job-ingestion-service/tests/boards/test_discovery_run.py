import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from platform_db.models import Company, Job
from platform_db.models.boards import BoardStatus, JobBoard
from pydantic import PostgresDsn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.boards.client import BoardClient
from job_ingestion.boards.discovery import DiscoveryOutcome, DiscoveryResult
from job_ingestion.boards.discovery_run import (
    DiscoveryConfig,
    discover_boards,
    due_companies,
    register,
    run_discovery,
)
from job_ingestion.boards.provider import Verification
from job_ingestion.boards.registered import polled_slugs
from job_ingestion.config import Environment, Settings
from job_ingestion.database import Database
from job_ingestion.errors import SourceUnavailableError
from job_ingestion.persistence import SourceRegistration, ensure_source
from tests.boards.fakes import (
    FAKE_BASE_URL,
    json_provider,
    never_sleeps,
    never_states,
    ok,
    routing,
    xml_provider,
)
from tests.support.catalog import with_empty_catalog


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


def board(company: str, count: int = 1) -> httpx2.Response:
    return ok(
        {"jobs": [{"id": index, "title": "Engineer", "company": company} for index in range(count)]}
    )


async def make_company(session: AsyncSession, name: str, *, jobs_count: int = 0) -> Company:
    company = Company(display_name=name)
    session.add(company)
    await session.flush()
    for _ in range(jobs_count):
        session.add(
            Job(
                company=company,
                title="Engineer",
                description="A job.",
                application_url="https://example.test/apply",
            )
        )
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


# --- due_companies ----------------------------------------------------------


@pytest.mark.integration
def test_a_company_with_no_row_is_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await session.commit()

            due = await due_companies(
                session, source_key="fake", config=DiscoveryConfig(), now=datetime.now(UTC)
            )

        assert [row.id for row in due] == [company.id]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_fresh_confirmed_row_is_not_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                last_checked_at=now,
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert due == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_confirmed_row_older_than_30_days_is_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                last_checked_at=now - timedelta(days=31),
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert [row.id for row in due] == [company.id]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unreachable_row_from_yesterday_is_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.UNREACHABLE,
                last_checked_at=now - timedelta(days=1),
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert [row.id for row in due] == [company.id]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_freshly_checked_pinned_row_is_not_due(database_url: PostgresDsn) -> None:
    """A pinned row follows `recheck_verified` like a confirmed row, not the
    open-ended cadence its own (possibly stale) status would otherwise get:
    it is still worth a monthly recheck (see `test_reverification.py`), but
    not on every run."""

    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.NOT_FOUND,
                pinned=True,
                last_checked_at=now,
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert due == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_not_found_row_older_than_a_week_is_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.NOT_FOUND,
                last_checked_at=now - timedelta(days=8),
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert [row.id for row in due] == [company.id]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_blocked_row_is_never_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session, slug="acme", company_id=company.id, status=BoardStatus.BLOCKED
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert due == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_wrong_company_row_is_never_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session, slug="acme", company_id=company.id, status=BoardStatus.WRONG_COMPANY
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert due == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_fresh_named_row_is_not_due(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.NAMED,
                last_checked_at=now,
            )
            await session.commit()

            due = await due_companies(session, source_key="fake", config=DiscoveryConfig(), now=now)

        assert due == []

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_due_companies_are_ordered_by_job_count_then_name(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            few = await make_company(session, "Few Jobs Co", jobs_count=1)
            many = await make_company(session, "Many Jobs Co", jobs_count=3)
            zero_a = await make_company(session, "Zero Jobs A")
            zero_b = await make_company(session, "Zero Jobs B")
            await session.commit()

            due = await due_companies(
                session, source_key="fake", config=DiscoveryConfig(), now=datetime.now(UTC)
            )

        assert [row.id for row in due] == [many.id, few.id, zero_a.id, zero_b.id]

    run_database_test(database_url, exercise)


# --- register ----------------------------------------------------------------


@pytest.mark.integration
def test_register_does_not_overwrite_a_pinned_row_for_the_same_slug(
    database_url: PostgresDsn,
) -> None:
    """A pinned row is reported, not overwritten: its own `company_id`,
    `status`, and `verified_at` stay exactly as the operator left them,
    whatever this probe found. See `test_reverification.py` for the
    `evidence["last_recheck"]` this still writes."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            session.add(
                JobBoard(
                    source_id=source.id, slug="acme", status=BoardStatus.CONFIRMED, pinned=True
                )
            )
            await session.commit()

            other = await make_company(session, "Acme Two")
            await session.commit()

            result = DiscoveryResult(
                company=other.display_name,
                outcome=DiscoveryOutcome.CONFIRMED,
                slug="acme",
                found_company="Acme Two",
            )
            outcome = await register(
                session, source=source, company=other, result=result, now=datetime.now(UTC)
            )
            await session.commit()

        assert outcome == "pinned_reported"

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.company_id is None
        assert row.pinned is True
        assert row.verified_at is None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_not_found_result_is_keyed_on_a_candidate_that_was_actually_tried(
    database_url: PostgresDsn,
) -> None:
    """`Acme Health Group`'s *first* candidate, `acmehealthgroup`, is already
    `wrong_company` for a different company and so is skipped, not requested.
    A `NOT_FOUND` result carries no slug of its own; the row this company
    gets must be keyed on a candidate that was actually tried (the second
    one), not on the skipped first one — keying it there would find the
    settled row, refuse to touch it, and leave this company with no row at
    all, forever due for another probe that never lands anywhere."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            other = await make_company(session, "Somebody Else")
            session.add(
                JobBoard(
                    source_id=source.id,
                    slug="acmehealthgroup",
                    status=BoardStatus.WRONG_COMPANY,
                    company_id=other.id,
                )
            )
            await session.commit()

            company = await make_company(session, "Acme Health Group")
            await session.commit()

            result = DiscoveryResult(
                company=company.display_name, outcome=DiscoveryOutcome.NOT_FOUND
            )
            now = datetime.now(UTC)
            outcome = await register(
                session,
                source=source,
                company=company,
                result=result,
                now=now,
                skip={"acmehealthgroup"},
            )
            await session.commit()

        assert outcome == "not_found"

        async with database.session() as session:
            row = (
                await session.scalars(select(JobBoard).where(JobBoard.slug == "acme-health-group"))
            ).one()

        assert row.company_id == company.id
        assert row.status is BoardStatus.NOT_FOUND
        assert row.evidence is not None
        assert row.evidence["tried"] == ["acme-health-group", "acme"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_not_found_result_with_every_candidate_skipped_is_left_unchanged(
    database_url: PostgresDsn,
) -> None:
    """`Single`'s only candidate, `single`, is already `wrong_company` for a
    different company. There is no other slug left to key a row on for this
    company — the registry's key is the slug alone — so nothing is written."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            other = await make_company(session, "Somebody Else")
            session.add(
                JobBoard(
                    source_id=source.id,
                    slug="single",
                    status=BoardStatus.WRONG_COMPANY,
                    company_id=other.id,
                )
            )
            await session.commit()

            company = await make_company(session, "Single")
            await session.commit()

            result = DiscoveryResult(
                company=company.display_name, outcome=DiscoveryOutcome.NOT_FOUND
            )
            outcome = await register(
                session,
                source=source,
                company=company,
                result=result,
                now=datetime.now(UTC),
                skip={"single"},
            )
            await session.commit()

        assert outcome == "unchanged"

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "single"))).one()

        assert row.company_id == other.id

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_not_found_row_owned_by_another_company_may_still_be_rekeyed(
    database_url: PostgresDsn,
) -> None:
    """`not_found`, `unreachable`, `candidate`, and `inactive` are unproven:
    unlike a settled `confirmed`/`named` row, they may still be re-keyed to
    whichever company a later probe actually confirms."""

    async def exercise(database: Database) -> None:
        async with database.session() as session:
            source = await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            other = await make_company(session, "Other Co")
            session.add(
                JobBoard(
                    source_id=source.id,
                    slug="acme",
                    status=BoardStatus.NOT_FOUND,
                    company_id=other.id,
                )
            )
            company = await make_company(session, "Acme")
            await session.commit()

            result = DiscoveryResult(
                company=company.display_name,
                outcome=DiscoveryOutcome.CONFIRMED,
                slug="acme",
                found_company="Acme",
            )
            outcome = await register(
                session, source=source, company=company, result=result, now=datetime.now(UTC)
            )
            await session.commit()

        assert outcome == "confirmed"

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.company_id == company.id
        assert row.status is BoardStatus.CONFIRMED

    run_database_test(database_url, exercise)


# --- run_discovery -----------------------------------------------------------


@pytest.mark.integration
def test_a_confirmed_slug_owned_by_a_different_company_is_left_alone(
    database_url: PostgresDsn,
) -> None:
    """Two companies whose names guess the same slug must not fight over it.
    Company A is already confirmed there; company B's guess landing on the
    same slug is reported as `unchanged` and left alone, not swapped in —
    otherwise the row's `company_id` would ping-pong between the two on
    every run that probes both."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        now = datetime.now(UTC)
        async with database.session() as session:
            company_a = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company_a.id,
                status=BoardStatus.CONFIRMED,
                last_checked_at=now,
            )
            await make_company(session, "Acme Inc")
            await session.commit()

        transport = routing({"/acme/jobs": board("Acme")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: now,
        )

        # Company A's fresh confirmed row excludes it from `due`; only B is.
        assert summary.seeded == 1
        assert summary.probed == 1
        assert summary.unchanged == 1
        assert summary.confirmed == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.company_id == company_a.id
        assert row.status is BoardStatus.CONFIRMED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_three_companies_route_to_confirmed_wrong_company_and_not_found(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            confirmo = await make_company(session, "Confirmo")
            wrongco = await make_company(session, "Wrongco")
            missingco = await make_company(session, "Missingco")
            await session.commit()

        transport = routing(
            {
                "/confirmo/jobs": board("Confirmo"),
                "/wrongco/jobs": board("Globex"),
                "/missingco/jobs": httpx2.Response(404),
            }
        )
        moment = datetime.now(UTC)
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.seeded == 3
        assert summary.probed == 3
        assert summary.confirmed == 1
        assert summary.wrong_company == 1
        assert summary.not_found == 1

        async with database.session() as session:
            rows = {row.slug: row for row in (await session.scalars(select(JobBoard))).all()}

        assert rows["confirmo"].company_id == confirmo.id
        assert rows["confirmo"].status is BoardStatus.CONFIRMED
        assert rows["confirmo"].verified_at == moment
        assert rows["confirmo"].evidence is not None
        assert rows["confirmo"].evidence["kind"] == "provider_name"

        assert rows["wrongco"].company_id == wrongco.id
        assert rows["wrongco"].status is BoardStatus.WRONG_COMPANY
        assert rows["wrongco"].verified_at is None

        assert rows["missingco"].company_id == missingco.id
        assert rows["missingco"].status is BoardStatus.NOT_FOUND
        assert rows["missingco"].evidence is not None
        assert rows["missingco"].evidence["kind"] == "not_found"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_budget_stops_the_run_early(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            for index in range(5):
                await make_company(session, f"Company{index}")
            await session.commit()

        transport = routing(
            {f"/company{index}/jobs": board(f"Company{index}") for index in range(5)}
        )
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(budget=2),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.seeded == 5
        assert summary.probed == 2
        assert summary.stopped_at_budget is True

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_slug_already_wrong_company_for_another_company_is_not_requested(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            other = await make_company(session, "Acme")
            await add_board_row(
                session, slug="acme", company_id=other.id, status=BoardStatus.WRONG_COMPANY
            )
            await make_company(session, "Acme Renamed")
            await session.commit()

        transport = routing(
            {
                "/acmerenamed/jobs": httpx2.Response(404),
                "/acme-renamed/jobs": httpx2.Response(404),
                # "/acme/jobs" is deliberately absent: it must never be requested.
            }
        )
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        # "Acme" itself is excluded from `due` by its own wrong_company row.
        assert summary.seeded == 1
        assert summary.probed == 1
        assert summary.not_found == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_inactive_row_that_confirms_again_is_reactivated(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.INACTIVE,
                consecutive_failures=3,
                evidence={"kind": "provider_name", "found_company": "Acme"},
                last_checked_at=datetime.now(UTC) - timedelta(days=10),
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
            now=lambda: datetime.now(UTC),
        )

        assert summary.reactivated == 1
        assert summary.confirmed == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unverifiable_provider_is_stored_as_candidate_and_not_polled(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        body = b"<feed><position><id>1</id><title>One</title></position></feed>"
        transport = routing({"/acme/feed.xml": httpx2.Response(200, content=body)})
        summary = await run_discovery(
            database,
            xml_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.unverifiable == 1

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            slugs = await polled_slugs(session, "fake")

        assert row.status is BoardStatus.CANDIDATE
        assert row.evidence is not None
        assert row.evidence["kind"] == "unverified"
        assert slugs == ()

    run_database_test(database_url, exercise)


def verifying_provider(verify: Any) -> Any:
    """A JSON board provider whose feed states nothing, so every guess that
    answers reaches `verify` instead of confirming on its own."""
    return json_provider(stated_company=never_states, verify=verify)


@pytest.mark.integration
def test_a_verify_hook_returning_named_registers_a_named_row(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        async def verify(_client: BoardClient, slug: str, company: Company) -> Verification:
            assert slug == "acme"
            assert company.display_name == "Acme"
            return Verification(
                outcome=DiscoveryOutcome.NAMED,
                found_company="Acme",
                evidence={
                    "kind": "site_title",
                    "found_company": "Acme",
                    "source": "title",
                    "checked_at": "2026-09-14T00:00:00+00:00",
                },
            )

        transport = routing({"/acme/jobs": board("")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.named == 1
        assert summary.confirmed == 0
        assert summary.unverifiable == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()
            slugs = await polled_slugs(session, "fake")

        assert row.status is BoardStatus.NAMED
        assert row.evidence == {
            "kind": "site_title",
            "found_company": "Acme",
            "source": "title",
            "checked_at": "2026-09-14T00:00:00+00:00",
        }
        assert row.verified_at is not None
        assert slugs == ("acme",)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_verify_hook_returning_named_on_an_inactive_row_resets_the_failures(
    database_url: PostgresDsn,
) -> None:
    """A board that went inactive after repeated failures, then verifies
    `NAMED` again, must not carry its stale failure count back into the
    walk — one more failure would retire it immediately otherwise, unlike a
    `CONFIRMED` revival, which already resets it. It is also a revival, so
    it counts under both `reactivated` and `named` — undercounting either
    would misreport what the run actually did."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            company = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=company.id,
                status=BoardStatus.INACTIVE,
                consecutive_failures=3,
                evidence={"kind": "site_title", "found_company": "Acme"},
            )
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.NAMED,
                found_company="Acme",
                evidence={"kind": "site_title", "found_company": "Acme", "source": "title"},
            )

        transport = routing({"/acme/jobs": board("")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.named == 1
        assert summary.reactivated == 1

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.NAMED
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_verify_hook_returning_confirmed_registers_confirmed_with_its_evidence(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        async def verify(_client: BoardClient, slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company=None,
                evidence={
                    "kind": "website_link",
                    "website": "https://acme.example.test/careers",
                    "checked_at": "2026-09-14T00:00:00+00:00",
                },
            )

        moment = datetime.now(UTC)
        transport = routing({"/acme/jobs": board("")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.confirmed == 1
        assert summary.named == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.evidence == {
            "kind": "website_link",
            "website": "https://acme.example.test/careers",
            "checked_at": "2026-09-14T00:00:00+00:00",
        }
        assert row.verified_at == moment

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_verify_hook_returning_wrong_company_registers_wrong_company(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.WRONG_COMPANY,
                found_company="Globex",
                evidence={"kind": "site_title", "found_company": "Globex", "source": "title"},
            )

        transport = routing({"/acme/jobs": board("")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.wrong_company == 1
        assert summary.named == 0
        assert summary.confirmed == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.WRONG_COMPANY
        assert row.evidence == {
            "kind": "site_title",
            "found_company": "Globex",
            "source": "title",
        }

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_provider_without_verify_still_registers_a_candidate(database_url: PostgresDsn) -> None:
    """The same feed-states-nothing shape as the verifying tests above, but
    with no `verify` hook configured: unverifiable stays unverifiable."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        transport = routing({"/acme/jobs": board("")})
        summary = await run_discovery(
            database,
            verifying_provider(None),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.unverifiable == 1
        assert summary.named == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CANDIDATE

    run_database_test(database_url, exercise)


def locating_provider(locate: Any) -> Any:
    """A JSON board provider whose guesses never answer at all, so `locate`
    is asked instead of leaving the company simply `not_found`."""
    return json_provider(locate=locate)


@pytest.mark.integration
def test_a_locate_hook_registers_the_board_it_names_when_no_guess_answers(
    database_url: PostgresDsn,
) -> None:
    """`Pinpoint`'s only guess, `pinpoint`, does not answer at all — but its
    website links a board named `workwithus`, which `locate` reports.  Both
    rows are written: the guess as `not_found` (it really was tried), and
    the board `locate` named as `confirmed`."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, company: Company) -> Verification:
            assert company.display_name == "Pinpoint"
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company=None,
                evidence={
                    "kind": "website_link",
                    "website": "https://pinpoint.example.test/",
                    "linked": "workwithus",
                    "checked_at": "2026-09-14T00:00:00+00:00",
                },
                slug="workwithus",
            )

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.not_found == 1
        assert summary.located == 1

        async with database.session() as session:
            rows = {row.slug: row for row in (await session.scalars(select(JobBoard))).all()}
            slugs = await polled_slugs(session, "fake")

        assert rows["pinpoint"].status is BoardStatus.NOT_FOUND
        assert rows["workwithus"].status is BoardStatus.CONFIRMED
        assert rows["workwithus"].company_id is not None
        assert rows["workwithus"].verified_at is not None
        assert rows["workwithus"].evidence is not None
        assert rows["workwithus"].evidence["kind"] == "website_link"
        assert "workwithus" in slugs

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_locate_hook_returning_named_registers_a_named_row(database_url: PostgresDsn) -> None:
    """`locate` is not limited to `CONFIRMED` — a board it names can be
    `NAMED` or `WRONG_COMPANY` too, written by the same rules `verify`'s own
    answers are."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.NAMED,
                found_company="Workwithus",
                evidence={"kind": "site_title", "found_company": "Workwithus", "source": "title"},
                slug="workwithus",
            )

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.located == 1

        async with database.session() as session:
            row = (
                await session.scalars(select(JobBoard).where(JobBoard.slug == "workwithus"))
            ).one()

        assert row.status is BoardStatus.NAMED
        assert row.company_id is not None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_locate_hook_returning_wrong_company_registers_wrong_company(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.WRONG_COMPANY,
                found_company="Globex",
                evidence={"kind": "site_title", "found_company": "Globex"},
                slug="globexboard",
            )

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.located == 1

        async with database.session() as session:
            row = (
                await session.scalars(select(JobBoard).where(JobBoard.slug == "globexboard"))
            ).one()

        assert row.status is BoardStatus.WRONG_COMPANY
        assert row.company_id is not None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_locate_hook_returning_none_leaves_only_the_not_found_row(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, _company: Company) -> Verification | None:
            return None

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.not_found == 1
        assert summary.located == 0

        async with database.session() as session:
            rows = list((await session.scalars(select(JobBoard))).all())

        assert len(rows) == 1
        assert rows[0].slug == "pinpoint"
        assert rows[0].status is BoardStatus.NOT_FOUND

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_locate_hook_naming_a_slug_already_wrong_company_leaves_it_alone(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            other = await make_company(session, "Somebody Else")
            await add_board_row(
                session, slug="workwithus", company_id=other.id, status=BoardStatus.WRONG_COMPANY
            )
            await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company=None,
                evidence={"kind": "website_link", "website": "https://pinpoint.example.test/"},
                slug="workwithus",
            )

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.not_found == 1
        assert summary.located == 0

        async with database.session() as session:
            row = (
                await session.scalars(select(JobBoard).where(JobBoard.slug == "workwithus"))
            ).one()

        assert row.company_id == other.id
        assert row.status is BoardStatus.WRONG_COMPANY

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_locate_hook_naming_a_slug_not_found_for_another_company_is_rekeyed(
    database_url: PostgresDsn,
) -> None:
    """Unlike `wrong_company` above, `not_found` is unproven — the located
    slug's existing row may still be re-keyed to whoever a probe actually
    confirms, the same rule a guessed slug's own row already follows."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            other = await make_company(session, "Otherco")
            # Fresh enough that Otherco's own `not_found` recheck is not due
            # this run — it must not compete for "workwithus" independently.
            await add_board_row(
                session,
                slug="workwithus",
                company_id=other.id,
                status=BoardStatus.NOT_FOUND,
                last_checked_at=datetime.now(UTC),
            )
            pinpoint = await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company=None,
                evidence={"kind": "website_link", "website": "https://pinpoint.example.test/"},
                slug="workwithus",
            )

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.located == 1

        async with database.session() as session:
            row = (
                await session.scalars(select(JobBoard).where(JobBoard.slug == "workwithus"))
            ).one()

        assert row.company_id == pinpoint.id
        assert row.status is BoardStatus.CONFIRMED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_previously_verified_not_found_recheck_never_asks_locate(
    database_url: PostgresDsn,
) -> None:
    """A previously confirmed row's own `NOT_FOUND` recheck is not believed
    on one silent probe (it stays `unchanged`); asking the website whether
    it names some *other* board on that same recheck would contradict that,
    writing a second row while the first stands untouched. `locate` must not
    even be called."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            company = await make_company(session, "Pinpoint")
            await add_board_row(
                session,
                slug="pinpoint",
                company_id=company.id,
                status=BoardStatus.CONFIRMED,
                last_checked_at=datetime.now(UTC) - timedelta(days=31),
            )
            await session.commit()

        called = False

        async def locate(_client: BoardClient, _company: Company) -> Verification:
            nonlocal called
            called = True
            raise AssertionError("locate must not be called for a previously verified recheck")

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert called is False
        assert summary.unchanged == 1
        assert summary.located == 0
        assert summary.not_found == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "pinpoint"))).one()

        assert row.status is BoardStatus.CONFIRMED

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_locate_hook_reviving_an_inactive_board_resets_the_failures(
    database_url: PostgresDsn,
) -> None:
    """`_register_named` revives an `inactive` row the same way the guessed
    slug's own `CONFIRMED` revival does: a clean failure count, and counted
    under `reactivated` (as well as `located` and `not_found`), not just a
    plain `confirmed`."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await add_board_row(
                session,
                slug="workwithus",
                company_id=None,
                status=BoardStatus.INACTIVE,
                consecutive_failures=3,
                evidence={"kind": "website_link", "website": "https://pinpoint.example.test/"},
            )
            await make_company(session, "Pinpoint")
            await session.commit()

        async def locate(_client: BoardClient, _company: Company) -> Verification:
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company=None,
                evidence={"kind": "website_link", "website": "https://pinpoint.example.test/"},
                slug="workwithus",
            )

        transport = routing({"/pinpoint/jobs": httpx2.Response(404)})
        summary = await run_discovery(
            database,
            locating_provider(locate),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.located == 1
        assert summary.reactivated == 1
        assert summary.not_found == 1

        async with database.session() as session:
            row = (
                await session.scalars(select(JobBoard).where(JobBoard.slug == "workwithus"))
            ).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.consecutive_failures == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_verify_hook_naming_a_different_slug_confirms_it_and_leaves_the_guess_candidate(
    database_url: PostgresDsn,
) -> None:
    """The guess `acme` answers but cannot confirm itself; `verify` learns
    the board is actually `other` (a link on the website, say). `other` is
    written confirmed, and `acme` — the slug that actually answered but
    could not be verified — is written exactly as an unverifiable guess
    always is: `candidate`, with the ordinary `unverified` evidence."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        async def verify(_client: BoardClient, slug: str, _company: Company) -> Verification:
            assert slug == "acme"
            return Verification(
                outcome=DiscoveryOutcome.CONFIRMED,
                found_company=None,
                evidence={
                    "kind": "website_link",
                    "website": "https://acme.example.test/",
                    "linked": "other",
                    "checked_at": "2026-09-14T00:00:00+00:00",
                },
                slug="other",
            )

        transport = routing({"/acme/jobs": board("")})
        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        # The registry's own outcome is what `register` reports for the
        # board it actually confirmed; the guessed slug's own demotion to
        # `candidate` is visible on its row (below), not in a separate tally.
        assert summary.confirmed == 1

        async with database.session() as session:
            rows = {row.slug: row for row in (await session.scalars(select(JobBoard))).all()}

        assert rows["acme"].status is BoardStatus.CANDIDATE
        assert rows["acme"].evidence is not None
        assert rows["acme"].evidence["kind"] == "unverified"
        assert rows["other"].status is BoardStatus.CONFIRMED
        assert rows["other"].company_id is not None
        assert rows["other"].evidence is not None
        assert rows["other"].evidence["kind"] == "website_link"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_politeness_sleeps_between_probed_companies_but_not_after_the_last(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await make_company(session, "Globex")
            await make_company(session, "Initech")
            await session.commit()

        sleeps: list[float] = []

        async def recording_sleeper(seconds: float) -> None:
            sleeps.append(seconds)

        transport = routing(
            {
                "/acme/jobs": board("Acme"),
                "/globex/jobs": board("Globex"),
                "/initech/jobs": board("Initech"),
            }
        )
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(politeness_seconds=1.5),
            settings=settings,
            http_client=transport,
            sleeper=recording_sleeper,
            now=lambda: datetime.now(UTC),
        )

        # Three companies probed, and a politeness pause only ever paces one
        # probe against the next — never after the last one, with nothing
        # left to be polite before.
        assert summary.probed == 3
        assert sleeps == [1.5, 1.5]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_rerun_within_cadence_probes_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        first = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=routing({"/acme/jobs": board("Acme")}),
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert first.seeded == 1
        assert first.confirmed == 1

        second = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=routing({}),
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert second.seeded == 0
        assert second.probed == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_discover_boards_entry_point_runs_against_the_configured_database(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            await make_company(session, "Acme")
            await session.commit()

        summary = await discover_boards(
            json_provider(),
            config=DiscoveryConfig(),
            settings=Settings(environment=Environment.TEST, database_url=database_url),
            http_client=routing({"/acme/jobs": board("Acme")}),
        )

        assert summary.source_key == "fake"
        assert summary.confirmed == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_nameless_company_is_skipped_without_a_probe(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            # Legal-form and separator punctuation only: `candidate_slugs`
            # strips it all away and is left with nothing to guess.
            await make_company(session, "---")
            await session.commit()

        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            # Empty on purpose: a request here would prove the company was
            # probed when it should not have been.
            http_client=routing({}),
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.seeded == 1
        assert summary.probed == 0
        assert summary.skipped_nameless == 1

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unreachable_probe_is_recorded_and_counted(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Down")
            await session.commit()

        transport = routing({"/down/jobs": httpx2.ConnectError("could not connect")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.probed == 1
        assert summary.unreachable == 1

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "down"))).one()

        assert row.status is BoardStatus.UNREACHABLE
        assert row.evidence == {"kind": "unreachable"}

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_confirmed_guess_landing_on_a_pinned_slug_is_not_tallied(
    database_url: PostgresDsn,
) -> None:
    """A pinned row is not in `skip` (only wrong_company and blocked are), so
    an unrelated company's guess can still land on it. `register` must not
    overwrite it, and a run must not count what it did not write."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            source = await ensure_source(
                session,
                SourceRegistration(key="fake", display_name="Fake Boards", base_url=FAKE_BASE_URL),
            )
            session.add(
                JobBoard(
                    source_id=source.id, slug="acme", status=BoardStatus.CONFIRMED, pinned=True
                )
            )
            await make_company(session, "Acme Renamed")
            await session.commit()

        transport = routing(
            {
                "/acmerenamed/jobs": httpx2.Response(404),
                "/acme-renamed/jobs": httpx2.Response(404),
                "/acme/jobs": board("Acme Renamed"),
            }
        )
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.probed == 1
        assert summary.confirmed == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.pinned is True
        assert row.company_id is None

    run_database_test(database_url, exercise)


# --- probe failures ---------------------------------------------------------


@pytest.mark.integration
def test_a_probe_the_transport_cannot_send_is_that_companys_outcome_not_the_runs(
    database_url: PostgresDsn,
) -> None:
    """Measured: one company's guess reached the transport as a host it could
    not encode, and every board found before it was lost with the run."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            alpha = await make_company(session, "Alpha")
            bravo = await make_company(session, "Bravo")
            charlie = await make_company(session, "Charlie")
            await session.commit()

        transport = routing(
            {
                "/alpha/jobs": board("Alpha"),
                "/bravo/jobs": httpx2.InvalidURL("Invalid IDNA hostname: 'bravo®.example.test'"),
                "/charlie/jobs": board("Charlie"),
            }
        )
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.probed == 3
        assert summary.confirmed == 2
        assert summary.unreachable == 1

        async with database.session() as session:
            rows = {row.slug: row for row in (await session.scalars(select(JobBoard))).all()}

        assert rows["alpha"].company_id == alpha.id
        assert rows["alpha"].status is BoardStatus.CONFIRMED
        assert rows["charlie"].company_id == charlie.id
        assert rows["charlie"].status is BoardStatus.CONFIRMED
        assert rows["bravo"].company_id == bravo.id
        assert rows["bravo"].status is BoardStatus.UNREACHABLE
        assert rows["bravo"].evidence == {
            "kind": "unreachable",
            "failure": "InvalidURL: Invalid IDNA hostname: 'bravo®.example.test'",
        }

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_verifier_that_fails_is_recorded_without_the_credential_its_message_carried(
    database_url: PostgresDsn,
) -> None:
    """A provider's own `verify` may raise the transport errors `discover`
    already absorbs for the feed; they are that company's outcome too, and a
    message quoting the URL being fetched must not quote its userinfo."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            acme = await make_company(session, "Acme")
            await session.commit()

        async def verify(_client: BoardClient, _slug: str, _company: Company) -> Verification:
            raise SourceUnavailableError(
                "fake", "careers site timed out: https://token:secret@acme.example.test/jobs"
            )

        summary = await run_discovery(
            database,
            verifying_provider(verify),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=routing({"/acme/jobs": board("")}),
            sleeper=never_sleeps,
            now=lambda: datetime.now(UTC),
        )

        assert summary.probed == 1
        assert summary.unreachable == 1
        assert summary.unverifiable == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.company_id == acme.id
        assert row.status is BoardStatus.UNREACHABLE
        assert row.evidence == {
            "kind": "unreachable",
            "failure": (
                "SourceUnavailableError: careers site timed out: https://acme.example.test/jobs"
            ),
        }

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_programming_error_in_a_probe_still_ends_the_run(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        async with database.session() as session:
            await make_company(session, "Alpha")
            await make_company(session, "Bravo")
            await session.commit()

        transport = routing({"/alpha/jobs": board("Alpha"), "/bravo/jobs": RuntimeError("bug")})
        with pytest.raises(RuntimeError, match="bug"):
            await run_discovery(
                database,
                json_provider(),
                config=DiscoveryConfig(),
                settings=settings,
                http_client=transport,
                sleeper=never_sleeps,
                now=lambda: datetime.now(UTC),
            )

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_failed_recheck_of_a_confirmed_row_only_notes_the_failure(
    database_url: PostgresDsn,
) -> None:
    """The same rule a silent recheck gets: one failed probe is not evidence
    the board moved, so the row stands and only the attempt is recorded."""

    async def exercise(database: Database) -> None:
        settings = Settings(environment=Environment.TEST, database_url=database_url)
        moment = datetime.now(UTC)
        async with database.session() as session:
            acme = await make_company(session, "Acme")
            await add_board_row(
                session,
                slug="acme",
                company_id=acme.id,
                status=BoardStatus.CONFIRMED,
                evidence={"kind": "provider_name"},
                last_checked_at=moment - timedelta(days=31),
            )
            await session.commit()

        transport = routing({"/acme/jobs": httpx2.InvalidURL("Invalid IDNA hostname: 'acme'")})
        summary = await run_discovery(
            database,
            json_provider(),
            config=DiscoveryConfig(),
            settings=settings,
            http_client=transport,
            sleeper=never_sleeps,
            now=lambda: moment,
        )

        assert summary.probed == 1
        assert summary.unchanged == 1
        assert summary.unreachable == 0

        async with database.session() as session:
            row = (await session.scalars(select(JobBoard).where(JobBoard.slug == "acme"))).one()

        assert row.status is BoardStatus.CONFIRMED
        assert row.evidence == {
            "kind": "provider_name",
            "last_recheck": {
                "kind": "unreachable",
                "checked_at": moment.isoformat(),
                "failure": "InvalidURL: Invalid IDNA hostname: 'acme'",
            },
        }

    run_database_test(database_url, exercise)
