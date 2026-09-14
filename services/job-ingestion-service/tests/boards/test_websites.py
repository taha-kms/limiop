import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest
from platform_db.models import Company, Job, JobProvenance, JobSource
from pydantic import PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.websites import (
    WebsiteResolution,
    WebsiteSource,
    WebsiteSummary,
    count_domains,
    from_postings,
    from_wikidata,
    hosts_in_payload,
    rank_domain,
    record,
    resolve_company_websites,
    resolve_website,
    resolve_websites,
)
from job_ingestion.config import Settings
from job_ingestion.database import Database
from tests.boards.fakes import never_sleeps, ok, routing
from tests.support.catalog import with_empty_catalog

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wikidata"


def fixture(name: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((FIXTURE_DIR / name).read_text())
    return body


def wikidata_response(name: str) -> httpx2.Response:
    return ok(fixture(name))


# ----------------------------------------------------------------------------
# Unit: host filtering
# ----------------------------------------------------------------------------


def payload_with(*urls: str) -> dict[str, Any]:
    return {"description": " ".join(f"Apply at {url}" for url in urls)}


def test_a_bare_host_strips_a_leading_www() -> None:
    assert hosts_in_payload(payload_with("https://www.acme.example/careers")) == {"acme.example"}


def test_an_ignored_suffix_is_dropped_on_a_dot_boundary() -> None:
    assert hosts_in_payload(payload_with("https://boards.greenhouse.io/acme")) == set()


def test_a_host_that_merely_contains_an_ignored_suffix_is_kept() -> None:
    # "notgreenhouse.io" is not "greenhouse.io", nor a subdomain of it.
    assert hosts_in_payload(payload_with("https://notgreenhouse.io/jobs")) == {"notgreenhouse.io"}


def test_a_host_mentioned_repeatedly_in_one_payload_is_one_entry() -> None:
    payload = payload_with(
        "https://acme.example/careers", "https://acme.example/careers/engineering"
    )
    assert hosts_in_payload(payload) == {"acme.example"}


def test_count_domains_gives_one_vote_per_posting() -> None:
    payloads = [
        payload_with("https://acme.example/a"),
        payload_with("https://acme.example/b", "https://acme.example/c"),
        payload_with("https://other.example/x"),
    ]
    counts = count_domains(payloads)
    assert counts == Counter({"acme.example": 2, "other.example": 1})


def test_rank_domain_needs_the_minimum_number_of_votes() -> None:
    assert rank_domain(Counter({"acme.example": 1})) is None


def test_rank_domain_is_ambiguous_on_a_tie() -> None:
    assert rank_domain(Counter({"acme.example": 2, "other.example": 2})) is None


def test_rank_domain_picks_the_clear_winner() -> None:
    assert rank_domain(Counter({"acme.example": 3, "other.example": 1})) == "acme.example"


# ----------------------------------------------------------------------------
# Unit: from_wikidata, no network
# ----------------------------------------------------------------------------


async def _from_wikidata(http_client: httpx2.AsyncClient, company_name: str) -> WebsiteResolution:
    return await from_wikidata(http_client, company_name, sleeper=never_sleeps)


def test_datadog_resolves_from_a_single_business_hit() -> None:
    client = routing(
        {
            "/w/api.php": wikidata_response("datadog-search.json"),
            "/wiki/Special:EntityData/Q16248637.json": wikidata_response("Q16248637.json"),
        }
    )
    resolution = asyncio.run(_from_wikidata(client, "Datadog"))
    assert resolution == WebsiteResolution("https://www.datadoghq.com/", WebsiteSource.WIKIDATA)


def test_hudl_resolves_to_nothing_because_the_hits_are_names_not_a_business() -> None:
    client = routing(
        {
            "/w/api.php": wikidata_response("hudl-search.json"),
            "/wiki/Special:EntityData/Q99010001.json": wikidata_response("Q99010001.json"),
            "/wiki/Special:EntityData/Q99010002.json": wikidata_response("Q99010002.json"),
        }
    )
    resolution = asyncio.run(_from_wikidata(client, "Hudl"))
    assert resolution == WebsiteResolution(None, None)


def test_pinpoint_resolves_to_nothing_because_two_businesses_share_the_label() -> None:
    client = routing(
        {
            "/w/api.php": wikidata_response("pinpoint-search.json"),
            "/wiki/Special:EntityData/Q140166436.json": wikidata_response("Q140166436.json"),
            "/wiki/Special:EntityData/Q99020002.json": wikidata_response("Q99020002.json"),
        }
    )
    resolution = asyncio.run(_from_wikidata(client, "Pinpoint"))
    assert resolution == WebsiteResolution(None, None)


def test_a_rate_limit_is_retried_and_then_succeeds() -> None:
    from tests.boards.fakes import responding

    client = responding(
        httpx2.Response(429, headers={"retry-after": "0"}),
        wikidata_response("datadog-search.json"),
        wikidata_response("Q16248637.json"),
    )
    resolution = asyncio.run(_from_wikidata(client, "Datadog"))
    assert resolution == WebsiteResolution("https://www.datadoghq.com/", WebsiteSource.WIKIDATA)


def test_a_transport_failure_is_retried_and_then_succeeds() -> None:
    from tests.boards.fakes import responding

    client = responding(
        httpx2.ConnectError("flaky"),
        wikidata_response("datadog-search.json"),
        wikidata_response("Q16248637.json"),
    )
    resolution = asyncio.run(_from_wikidata(client, "Datadog"))
    assert resolution == WebsiteResolution("https://www.datadoghq.com/", WebsiteSource.WIKIDATA)


def test_a_server_error_gives_up_without_raising() -> None:
    client = routing({"/w/api.php": httpx2.Response(500)})
    resolution = asyncio.run(_from_wikidata(client, "Datadog"))
    assert resolution == WebsiteResolution(None, None)


def test_a_non_json_body_gives_up_without_raising() -> None:
    client = routing({"/w/api.php": httpx2.Response(200, content=b"not json", headers={})})
    resolution = asyncio.run(_from_wikidata(client, "Datadog"))
    assert resolution == WebsiteResolution(None, None)


# ----------------------------------------------------------------------------
# Unit: record
# ----------------------------------------------------------------------------


def test_record_only_fills_a_missing_url() -> None:
    now = datetime(2026, 9, 14, tzinfo=UTC)
    company = Company(display_name="Acme")
    record(company, WebsiteResolution("https://acme.example/", WebsiteSource.POSTINGS), now)
    assert company.website_url == "https://acme.example/"
    assert company.website_source == "postings"
    assert company.website_checked_at == now


def test_record_never_overwrites_an_existing_url() -> None:
    now = datetime(2026, 9, 14, tzinfo=UTC)
    company = Company(display_name="Acme", website_url="https://existing.example/")
    record(company, WebsiteResolution("https://acme.example/", WebsiteSource.POSTINGS), now)
    assert company.website_url == "https://existing.example/"
    assert company.website_source == "postings"


def test_record_marks_an_unresolved_company_as_checked() -> None:
    now = datetime(2026, 9, 14, tzinfo=UTC)
    company = Company(display_name="Acme")
    record(company, WebsiteResolution(None, None), now)
    assert company.website_url is None
    assert company.website_source is None
    assert company.website_checked_at == now


def test_record_keeps_the_original_source_when_a_known_url_is_reconfirmed() -> None:
    """A recheck of a company that already has a url always resolves as
    `SOURCE` (`resolve_website` short-circuits on any stored url), but that
    must not erase where the url actually came from the first time."""
    earlier = datetime(2026, 6, 1, tzinfo=UTC)
    later = datetime(2026, 9, 14, tzinfo=UTC)
    company = Company(display_name="Acme", website_url="https://acme.example/")
    company.website_source = "postings"
    company.website_checked_at = earlier

    record(company, WebsiteResolution("https://acme.example/", WebsiteSource.SOURCE), later)

    assert company.website_url == "https://acme.example/"
    assert company.website_source == "postings"
    assert company.website_checked_at == later


# ----------------------------------------------------------------------------
# Integration: needs a real database
# ----------------------------------------------------------------------------


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


async def seed_source(database: Database, key: str = "greenhouse") -> JobSource:
    async with database.session() as session:
        source = JobSource(
            key=key,
            display_name=key.title(),
            base_url=f"https://{key}.example",
            precedence=10,
        )
        session.add(source)
        await session.commit()
        return source


async def seed_company_with_postings(
    database: Database,
    source: JobSource,
    display_name: str,
    payloads: list[dict[str, Any]],
) -> Company:
    async with database.session() as session:
        company = Company(display_name=display_name)
        session.add(company)
        await session.flush()
        for index, payload in enumerate(payloads):
            job = Job(
                company=company,
                match_key=f"{display_name}:{index}",
                title="Engineer",
                description="A job.",
                application_url="https://apply.example/",
            )
            session.add(job)
            await session.flush()
            session.add(
                JobProvenance(
                    job_id=job.id,
                    source_id=source.id,
                    source_job_id=f"{display_name}-{index}",
                    source_url="https://apply.example/",
                    raw_payload=payload,
                )
            )
        await session.commit()
        return company


async def seed_company(database: Database, display_name: str, **fields: Any) -> Company:
    async with database.session() as session:
        company = Company(display_name=display_name, **fields)
        session.add(company)
        await session.commit()
        return company


async def reload_company(database: Database, company_id: Any) -> Company:
    async with database.session() as session:
        return await session.get_one(Company, company_id)


def raising_client() -> httpx2.AsyncClient:
    def handle(_request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request should have been made")

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def always_unreachable_client() -> httpx2.AsyncClient:
    """Answers every request with a 500, so Wikidata is reached but never helps.

    Used where a run is expected to hit the network (there is nothing in
    postings to resolve from) but the test only cares about budget or
    recheck mechanics, not what Wikidata said.
    """

    def handle(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500)

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


@pytest.mark.integration
def test_resolve_website_short_circuits_on_an_existing_url(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        company = await seed_company(database, "Acme", website_url="https://acme.example/")
        async with database.session() as session:
            reloaded = await session.get_one(Company, company.id)
            resolution = await resolve_website(
                session, raising_client(), reloaded, now=datetime.now(UTC), sleeper=never_sleeps
            )
            await session.commit()
        assert resolution == WebsiteResolution("https://acme.example/", WebsiteSource.SOURCE)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_from_postings_resolves_from_seeded_provenance(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        source = await seed_source(database)
        payloads = [
            {"url": "https://acme.example/careers/1"},
            {"url": "https://acme.example/careers/2"},
            {"url": "https://boards.greenhouse.io/acme"},
        ]
        company = await seed_company_with_postings(database, source, "Acme", payloads)
        async with database.session() as session:
            reloaded = await session.get_one(Company, company.id)
            resolution = await from_postings(session, reloaded)
        assert resolution == WebsiteResolution("https://acme.example/", WebsiteSource.POSTINGS)

    run_database_test(database_url, exercise)


class RecordingSleeper:
    """A sleeper that never actually sleeps, but remembers being asked to."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.mark.integration
def test_run_respects_the_budget_and_reports_more_waiting(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        source = await seed_source(database)
        for name in ("Alpha", "Bravo", "Charlie"):
            await seed_company_with_postings(database, source, name, [])

        sleeper = RecordingSleeper()
        summary = await resolve_company_websites(
            database,
            budget=2,
            http_client=always_unreachable_client(),
            sleeper=sleeper,
            politeness_seconds=5.0,
        )

        # Three companies are due; the budget only lets two be processed.
        assert summary.seeded == 3
        assert summary.processed == 2
        assert summary.stopped_at_budget is True
        assert summary.unresolved == 2

        # Both processed companies have nothing in postings, so both reach
        # Wikidata (which always fails here): a politeness sleep belongs
        # between them, but not trailing after the last one processed.
        assert sleeper.calls == [5.0]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_run_skips_a_company_checked_recently_and_rechecks_an_old_one(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        now = datetime.now(UTC)
        recent = await seed_company(
            database,
            "Recent",
            website_checked_at=now - timedelta(days=1),
        )
        stale = await seed_company(
            database,
            "Stale",
            website_checked_at=now - timedelta(days=200),
        )

        summary = await resolve_company_websites(
            database,
            budget=10,
            recheck=timedelta(days=90),
            http_client=always_unreachable_client(),
            sleeper=never_sleeps,
            now=lambda: now,
        )

        assert summary.seeded == 1
        assert summary.processed == 1
        recent_after = await reload_company(database, recent.id)
        stale_after = await reload_company(database, stale.id)
        assert recent_after.website_checked_at == now - timedelta(days=1)
        assert stale_after.website_checked_at == now

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_run_counts_a_resolution_and_owns_its_default_client(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        source = await seed_source(database)
        payloads = [
            {"url": "https://acme.example/careers/1"},
            {"url": "https://acme.example/careers/2"},
        ]
        await seed_company_with_postings(database, source, "Acme", payloads)

        # No `http_client` passed: the run must own, and clean up, its own.
        # Postings alone resolve this company, so the client is never asked
        # to make a request.
        summary = await resolve_company_websites(
            database,
            budget=10,
            sleeper=never_sleeps,
        )

        assert summary.seeded == 1
        assert summary.processed == 1
        assert summary.resolved_by == {"postings": 1}
        assert summary.unresolved == 0

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unresolved_company_is_checked_but_gets_no_url(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        source = await seed_source(database)
        await seed_company_with_postings(database, source, "Unfindable Inc", [])

        summary = await resolve_company_websites(
            database,
            budget=10,
            http_client=routing({"/w/api.php": httpx2.Response(500)}),
            sleeper=never_sleeps,
        )

        assert summary.unresolved == 1
        assert summary.resolved_by == {}

        async with database.session() as session:
            company = (
                await session.scalars(
                    select(Company).where(Company.display_name == "Unfindable Inc")
                )
            ).one()
            assert company.website_url is None
            assert company.website_checked_at is not None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_resolve_websites_entry_point_runs_against_the_configured_database(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        source = await seed_source(database)
        await seed_company_with_postings(database, source, "Acme", [])

        settings = Settings(database_url=database_url)
        summary = await resolve_websites(
            settings=settings,
            http_client=routing({"/w/api.php": httpx2.Response(500)}),
            budget=5,
        )
        assert isinstance(summary, WebsiteSummary)
        assert summary.seeded == 1
        assert summary.processed == 1

    run_database_test(database_url, exercise)
