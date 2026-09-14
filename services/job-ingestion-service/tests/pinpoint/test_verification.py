"""Verifying a Pinpoint board beyond its feed.

`stated_name` is tested against every title template on its own. `identity`
and `verify` are tested against a routing transport, the same way discovery
is elsewhere in this suite.
"""

import asyncio

import httpx2
from platform_db.models import Company

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome
from job_ingestion.pinpoint.provider import PINPOINT
from job_ingestion.pinpoint.verification import identity, stated_name, verify
from tests.boards.fakes import FAKE_BASE_URL, never_sleeps, routing


def client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    return BoardClient(
        PINPOINT,
        BoardConfig(boards=(), base_url=FAKE_BASE_URL, retry_backoff_seconds=0.0),
        http_client=routing(routes),
        sleeper=never_sleeps,
    )


def html(title: str) -> httpx2.Response:
    return httpx2.Response(200, text=f"<html><head><title>{title}</title></head></html>")


def rss(title: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        content=f"<rss><channel><title>{title}</title></channel></rss>".encode(),
    )


def company(name: str, *, website_url: str | None = None) -> Company:
    return Company(display_name=name, website_url=website_url)


# --- stated_name --------------------------------------------------------------


def test_jobs_at_name_pipe_name_careers_strips_to_the_name() -> None:
    assert stated_name("Jobs at Pinpoint | Pinpoint Careers") == "Pinpoint"


def test_careers_at_name_strips_to_the_name() -> None:
    assert stated_name("Careers at Acme") == "Acme"


def test_name_careers_strips_to_the_name() -> None:
    assert stated_name("Acme Careers") == "Acme"


def test_name_jobs_strips_to_the_name() -> None:
    assert stated_name("Acme Jobs") == "Acme"


def test_a_title_naming_nothing_returns_none() -> None:
    assert stated_name("Welcome to our site") is None


def test_a_blank_title_returns_none() -> None:
    assert stated_name("   ") is None


# --- identity -------------------------------------------------------------


def test_a_matching_title_is_named() -> None:
    fetcher = client({"/": html("Jobs at Pinpoint | Pinpoint Careers")})

    result = asyncio.run(identity(fetcher, "workwithus", company("Pinpoint Ltd")))

    assert result is not None
    assert result.outcome is DiscoveryOutcome.NAMED
    assert result.evidence["kind"] == "site_title"
    assert result.evidence["source"] == "title"
    assert result.found_company == "Pinpoint"


def test_a_title_naming_someone_else_is_wrong_company() -> None:
    fetcher = client({"/": html("Jobs at Globex | Globex Careers")})

    result = asyncio.run(identity(fetcher, "workwithus", company("Pinpoint Ltd")))

    assert result is not None
    assert result.outcome is DiscoveryOutcome.WRONG_COMPANY
    assert result.found_company == "Globex"


def test_an_empty_title_falls_back_to_the_rss_channel_title() -> None:
    fetcher = client(
        {
            "/": html(""),
            "/jobs.rss": rss("Careers at Acme"),
        }
    )

    result = asyncio.run(identity(fetcher, "acme", company("Acme")))

    assert result is not None
    assert result.outcome is DiscoveryOutcome.NAMED
    assert result.evidence["source"] == "rss"


def test_both_silent_is_none() -> None:
    fetcher = client(
        {
            "/": html("Home"),
            "/jobs.rss": httpx2.Response(200, content=b"<rss><channel></channel></rss>"),
        }
    )

    result = asyncio.run(identity(fetcher, "acme", company("Acme")))

    assert result is None


def test_a_404_site_is_none() -> None:
    fetcher = client(
        {
            "/": httpx2.Response(404),
            "/jobs.rss": httpx2.Response(404),
        }
    )

    result = asyncio.run(identity(fetcher, "acme", company("Acme")))

    assert result is None


# --- verify -----------------------------------------------------------------


def test_verify_reports_named_from_identity_when_there_is_no_website() -> None:
    fetcher = client({"/": html("Acme Careers")})

    result = asyncio.run(verify(fetcher, "acme", company("Acme")))

    assert result.outcome is DiscoveryOutcome.NAMED


def test_verify_falls_through_to_unverifiable() -> None:
    fetcher = client(
        {
            "/": httpx2.Response(404),
            "/jobs.rss": httpx2.Response(404),
        }
    )

    result = asyncio.run(verify(fetcher, "acme", company("Acme")))

    assert result.outcome is DiscoveryOutcome.UNVERIFIABLE
    assert result.evidence["kind"] == "unverified"
