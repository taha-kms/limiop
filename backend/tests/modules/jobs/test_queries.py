import asyncio
import base64
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from pydantic import PostgresDsn

from app.db.session import Database
from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType
from app.modules.jobs.models import Job
from app.modules.jobs.queries import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    InvalidCursorError,
    JobCursor,
    JobFilters,
    JobPage,
    decode_cursor,
    encode_cursor,
    list_jobs,
)
from tests.support.catalog import at, seed, with_empty_catalog

MAX_REQUESTS = 50


def run_database_test(
    database_url: PostgresDsn,
    test: Any,
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


async def titles(database: Database, **kwargs: Any) -> tuple[list[str], JobPage]:
    async with database.session() as session:
        page = await list_jobs(session, **kwargs)
    return [job.title for job in page.jobs], page


async def drain(database: Database, **kwargs: Any) -> list[str]:
    """Page all the way through and return every title in order.

    Bounded on purpose. A predicate that stopped advancing would otherwise page
    forever and hang the run instead of reporting a failure.
    """
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(MAX_REQUESTS):
        names, page = await titles(database, cursor=cursor, **kwargs)
        seen.extend(names)
        if page.next_cursor is None:
            return seen
        cursor = page.next_cursor
    pytest.fail(f"paging did not terminate within {MAX_REQUESTS} requests")


def test_a_cursor_survives_a_round_trip() -> None:
    cursor = JobCursor(published_at=at(3), job_id=uuid4())

    assert decode_cursor(encode_cursor(cursor)) == cursor


def test_a_cursor_in_the_undated_tail_survives_a_round_trip() -> None:
    cursor = JobCursor(published_at=None, job_id=uuid4())

    assert decode_cursor(encode_cursor(cursor)) == cursor


def test_re_encoding_a_decoded_cursor_reproduces_the_token() -> None:
    token = encode_cursor(JobCursor(published_at=at(1), job_id=uuid4()))

    assert encode_cursor(decode_cursor(token)) == token


def test_a_cursor_does_not_advertise_what_it_holds() -> None:
    identifier = uuid4()
    token = encode_cursor(JobCursor(published_at=at(2), job_id=identifier))

    assert str(identifier) not in token
    assert "2026" not in token


def test_a_cursor_is_safe_in_a_url() -> None:
    token = encode_cursor(JobCursor(published_at=at(2), job_id=uuid4()))

    assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("!!!!", id="outside the alphabet"),
        pytest.param("AAAA", id="decodes but says nothing"),
        pytest.param("MXwyMDI2", id="too few fields"),
        pytest.param("MXx8bm90LWEtdXVpZA", id="unreadable identifier"),
        pytest.param("MXxub3QtYS1kYXRlfDAxOTNiNGQy", id="unreadable timestamp"),
    ],
)
def test_an_unreadable_cursor_is_refused(token: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)


def test_a_cursor_from_a_different_ordering_is_refused() -> None:
    payload = f"99|{at(1).isoformat()}|{uuid4()}"
    token = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    with pytest.raises(InvalidCursorError, match="different ordering"):
        decode_cursor(token)


def test_a_cursor_without_a_time_zone_is_refused() -> None:
    payload = f"1|2026-08-01T12:00:00|{uuid4()}"
    token = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    with pytest.raises(InvalidCursorError, match="time zone"):
        decode_cursor(token)


@pytest.mark.integration
def test_jobs_are_listed_newest_first(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Older", "published_at": at(1)},
            {"title": "Newest", "published_at": at(3)},
            {"title": "Middle", "published_at": at(2)},
        )

        names, page = await titles(database)

        assert names == ["Newest", "Middle", "Older"]
        assert page.next_cursor is None
        assert page.has_more is False

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_undated_jobs_sort_after_every_dated_job(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Undated", "published_at": None},
            {"title": "Oldest", "published_at": at(1)},
            {"title": "Also undated", "published_at": None},
            {"title": "Newest", "published_at": at(9)},
        )

        names, _ = await titles(database)

        assert names[:2] == ["Newest", "Oldest"]
        assert set(names[2:]) == {"Undated", "Also undated"}

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_paging_returns_every_job_exactly_once(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        expected = [f"Job {index:02d}" for index in range(7)]
        await seed(
            database,
            *({"title": title, "published_at": at(index)} for index, title in enumerate(expected)),
        )

        seen = await drain(database, page_size=3)

        assert seen == list(reversed(expected))

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_paging_through_the_undated_tail_terminates(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Dated", "published_at": at(1)},
            *({"title": f"Undated {index}", "published_at": None} for index in range(4)),
        )

        seen = await drain(database, page_size=2)

        assert seen[0] == "Dated"
        assert len(seen) == 5
        assert len(set(seen)) == 5

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_job_ingested_mid_scroll_never_duplicates_a_seen_job(
    database_url: PostgresDsn,
) -> None:
    """The reason paging is keyset rather than offset."""

    async def exercise(database: Database) -> None:
        await seed(
            database,
            *({"title": f"Job {index}", "published_at": at(index)} for index in range(4)),
        )

        first, page = await titles(database, page_size=2)
        assert first == ["Job 3", "Job 2"]

        await seed(database, {"title": "Arrived late", "published_at": at(99)})

        second, _ = await titles(database, cursor=page.next_cursor, page_size=2)

        assert second == ["Job 1", "Job 0"]
        assert "Arrived late" not in second

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_paging_breaks_ties_on_identical_publication_times(
    database_url: PostgresDsn,
) -> None:
    """Bulk-posted jobs share a timestamp, so the boundary can land inside a tie.

    Ids are random, so the property under test is that every job appears once
    across the boundary, not that they appear in a fixed order.
    """

    async def exercise(database: Database) -> None:
        await seed(
            database,
            *({"title": f"Job {index}", "published_at": at(1)} for index in range(5)),
        )

        seen = await drain(database, page_size=2)

        assert sorted(seen) == [f"Job {index}" for index in range(5)]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_tie_spanning_a_page_boundary_is_stable_across_requests(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            *({"title": f"Tied {index}", "published_at": at(2)} for index in range(4)),
            {"title": "Older", "published_at": at(1)},
        )

        assert await drain(database, page_size=2) == await drain(database, page_size=3)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_only_active_jobs_are_listed(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Listable", "published_at": at(1)},
            {"title": "Expired", "published_at": at(2), "status": JobStatus.EXPIRED},
            {"title": "Removed", "published_at": at(3), "status": JobStatus.REMOVED},
        )

        names, _ = await titles(database)

        assert names == ["Listable"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_each_job_carries_its_company_without_a_second_query(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await seed(database, {"title": "Listable", "published_at": at(1)})

        async with database.session() as session:
            page = await list_jobs(session)

        assert page.jobs[0].company.display_name == "Acme GmbH"

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_company_filter_narrows_to_one_employer(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        identifiers = await seed(
            database,
            {"title": "At Acme", "company": "Acme GmbH", "published_at": at(1)},
            {"title": "At Globex", "company": "Globex AG", "published_at": at(2)},
        )

        async with database.session() as session:
            wanted = await session.get(Job, identifiers["At Acme"])
            assert wanted is not None
            company_id = wanted.company_id

        names, _ = await titles(database, filters=JobFilters(company_id=company_id))

        assert names == ["At Acme"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_location_filter_matches_part_of_a_location(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "In Berlin", "location": "Berlin, Germany", "published_at": at(1)},
            {"title": "In Munich", "location": "Munich, Germany", "published_at": at(2)},
            {"title": "Nowhere", "location": None, "published_at": at(3)},
        )

        names, _ = await titles(database, filters=JobFilters(location="berlin"))

        assert names == ["In Berlin"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_workplace_filter_accepts_several_arrangements(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Remote", "workplace_type": WorkplaceType.REMOTE, "published_at": at(3)},
            {"title": "Hybrid", "workplace_type": WorkplaceType.HYBRID, "published_at": at(2)},
            {"title": "Onsite", "workplace_type": WorkplaceType.ONSITE, "published_at": at(1)},
        )

        names, _ = await titles(
            database,
            filters=JobFilters(
                workplace_types=frozenset({WorkplaceType.REMOTE, WorkplaceType.HYBRID})
            ),
        )

        assert names == ["Remote", "Hybrid"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_employment_filter_accepts_several_relationships(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {
                "title": "Permanent",
                "employment_type": EmploymentType.FULL_TIME,
                "published_at": at(2),
            },
            {
                "title": "Placement",
                "employment_type": EmploymentType.INTERNSHIP,
                "published_at": at(1),
            },
        )

        names, _ = await titles(
            database,
            filters=JobFilters(employment_types=frozenset({EmploymentType.INTERNSHIP})),
        )

        assert names == ["Placement"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_empty_filter_set_narrows_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Remote", "workplace_type": WorkplaceType.REMOTE, "published_at": at(2)},
            {"title": "Onsite", "workplace_type": WorkplaceType.ONSITE, "published_at": at(1)},
        )

        names, _ = await titles(database, filters=JobFilters(workplace_types=frozenset()))

        assert names == ["Remote", "Onsite"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_title_search_matches_part_of_a_title(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "Senior Data Engineer", "published_at": at(2)},
            {"title": "Platform Engineer", "published_at": at(1)},
            {"title": "Product Designer", "published_at": at(3)},
        )

        names, _ = await titles(database, filters=JobFilters(title_query="engineer"))

        assert names == ["Senior Data Engineer", "Platform Engineer"]

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        pytest.param("C_", ["C_ Developer"], id="underscore is not any character"),
        pytest.param("100%", ["100% Remote Lead"], id="percent is not a wildcard"),
        pytest.param("\\", ["Back\\slash Engineer"], id="backslash is literal"),
    ],
)
def test_search_wildcards_are_treated_as_text(
    database_url: PostgresDsn,
    query: str,
    expected: Sequence[str],
) -> None:
    """Untrusted text becomes a term, never a pattern."""

    async def exercise(database: Database) -> None:
        await seed(
            database,
            {"title": "C_ Developer", "published_at": at(4)},
            {"title": "CX Developer", "published_at": at(3)},
            {"title": "100% Remote Lead", "published_at": at(2)},
            {"title": "Back\\slash Engineer", "published_at": at(1)},
        )

        names, _ = await titles(database, filters=JobFilters(title_query=query))

        assert names == list(expected)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_filters_compose_without_changing_the_result(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            {
                "title": "Remote Data Engineer",
                "location": "Berlin",
                "workplace_type": WorkplaceType.REMOTE,
                "employment_type": EmploymentType.FULL_TIME,
                "published_at": at(3),
            },
            {
                "title": "Onsite Data Engineer",
                "location": "Berlin",
                "workplace_type": WorkplaceType.ONSITE,
                "employment_type": EmploymentType.FULL_TIME,
                "published_at": at(2),
            },
            {
                "title": "Remote Designer",
                "location": "Berlin",
                "workplace_type": WorkplaceType.REMOTE,
                "employment_type": EmploymentType.FULL_TIME,
                "published_at": at(1),
            },
        )

        names, page = await titles(
            database,
            filters=JobFilters(
                location="berlin",
                workplace_types=frozenset({WorkplaceType.REMOTE}),
                employment_types=frozenset({EmploymentType.FULL_TIME}),
                title_query="engineer",
            ),
        )

        assert names == ["Remote Data Engineer"]
        assert page.next_cursor is None

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_paging_a_filtered_listing_stays_inside_the_filter(
    database_url: PostgresDsn,
) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            *(
                {
                    "title": f"Engineer {index}",
                    "workplace_type": WorkplaceType.REMOTE,
                    "published_at": at(index),
                }
                for index in range(5)
            ),
            *(
                {
                    "title": f"Designer {index}",
                    "workplace_type": WorkplaceType.ONSITE,
                    "published_at": at(index + 10),
                }
                for index in range(5)
            ),
        )

        seen = await drain(
            database,
            page_size=2,
            filters=JobFilters(workplace_types=frozenset({WorkplaceType.REMOTE})),
        )

        assert seen == [f"Engineer {index}" for index in reversed(range(5))]

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_unreadable_cursor_stops_the_request(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(database, {"title": "Listable", "published_at": at(1)})

        async with database.session() as session:
            with pytest.raises(InvalidCursorError):
                await list_jobs(session, cursor="not-a-cursor!")

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_a_page_larger_than_the_ceiling_is_capped(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            *(
                {"title": f"Job {index:03d}", "published_at": at(index)}
                for index in range(MAX_PAGE_SIZE + 1)
            ),
        )

        names, page = await titles(database, page_size=MAX_PAGE_SIZE + 500)

        assert len(names) == MAX_PAGE_SIZE
        assert page.has_more is True

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_an_empty_catalog_pages_to_nothing(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        names, page = await titles(database)

        assert names == []
        assert page.next_cursor is None

    run_database_test(database_url, exercise)


@pytest.mark.integration
@pytest.mark.parametrize("page_size", [0, -1])
def test_a_page_size_below_one_is_refused(
    database_url: PostgresDsn,
    page_size: int,
) -> None:
    async def exercise(database: Database) -> None:
        async with database.session() as session:
            with pytest.raises(ValueError, match="page_size"):
                await list_jobs(session, page_size=page_size)

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_default_batch_is_twenty(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        await seed(
            database,
            *({"title": f"Job {index:02d}", "published_at": at(index)} for index in range(25)),
        )

        names, page = await titles(database)

        assert len(names) == DEFAULT_PAGE_SIZE
        assert page.has_more is True

    run_database_test(database_url, exercise)
