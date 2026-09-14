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
from job_ingestion.pinpoint.verification import corroborate, identity, stated_name, verify
from tests.boards.fakes import FAKE_BASE_URL, never_sleeps, routing


def client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    return BoardClient(
        PINPOINT,
        BoardConfig(boards=(), base_url=FAKE_BASE_URL, retry_backoff_seconds=0.0),
        http_client=routing(routes),
        sleeper=never_sleeps,
    )


def url_client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    """Routes by the exact URL requested, not just its path — corroboration
    reaches two different hosts (the company's website, and Pinpoint's own
    subdomain) that can share a path like `/`."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        reply = routes.get(str(request.url), httpx2.Response(404))
        if isinstance(reply, Exception):
            raise reply
        return reply

    return BoardClient(
        PINPOINT,
        BoardConfig(boards=(), base_url=FAKE_BASE_URL, retry_backoff_seconds=0.0),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        sleeper=never_sleeps,
    )


def html(title: str) -> httpx2.Response:
    return httpx2.Response(200, text=f"<html><head><title>{title}</title></head></html>")


def rss(title: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        content=f"<rss><channel><title>{title}</title></channel></rss>".encode(),
    )


def rss_with_item(channel_title: str, item_title: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        content=(
            f"<rss><channel><title>{channel_title}</title>"
            f"<item><title>{item_title}</title></item></channel></rss>"
        ).encode(),
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


def test_an_rss_item_title_is_never_mistaken_for_the_channel_title() -> None:
    """A posting titled "Senior Engineer Jobs" is not the channel naming
    "Senior Engineer" — reading the first `<title>` anywhere in the document,
    rather than only the channel's own, would make that mistake, and a
    `WRONG_COMPANY` verdict from it is permanent."""
    fetcher = client(
        {
            "/": html(""),
            "/jobs.rss": rss_with_item("", "Senior Engineer Jobs"),
        }
    )

    result = asyncio.run(identity(fetcher, "acme", company("Acme")))

    assert result is None


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


# --- corroborate --------------------------------------------------------------


def test_no_website_is_none_without_any_request() -> None:
    def explode(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    fetcher = BoardClient(
        PINPOINT,
        BoardConfig(boards=(), base_url=FAKE_BASE_URL),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(explode)),
        sleeper=never_sleeps,
    )

    result = asyncio.run(corroborate(fetcher, "acme", company("Acme", website_url=None)))

    assert result is None


def test_home_page_linking_the_subdomain_is_confirmed_website_link() -> None:
    fetcher = url_client(
        {
            "https://acme.example.test/": httpx2.Response(
                200, text='<a href="https://acme.boards.example.test/">Careers</a>'
            ),
        }
    )

    result = asyncio.run(
        corroborate(fetcher, "acme", company("Acme", website_url="https://acme.example.test/"))
    )

    assert result is not None
    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.evidence["kind"] == "website_link"
    assert result.evidence["website"] == "https://acme.example.test/"


def test_careers_page_redirecting_to_the_subdomain_is_confirmed_website_redirect() -> None:
    fetcher = url_client(
        {
            "https://acme.example.test/": httpx2.Response(200, text="<html>Welcome</html>"),
            "https://acme.example.test/careers": httpx2.Response(
                302, headers={"location": "https://acme.boards.example.test/"}
            ),
            "https://acme.boards.example.test/": httpx2.Response(200, text="Jobs"),
        }
    )

    result = asyncio.run(
        corroborate(fetcher, "acme", company("Acme", website_url="https://acme.example.test/"))
    )

    assert result is not None
    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.evidence["kind"] == "website_redirect"
    assert result.evidence["website"] == "https://acme.boards.example.test/"


def test_robots_disallowing_a_path_skips_it_without_fetching() -> None:
    robots_txt = "User-agent: *\nDisallow: /careers\n"
    fetcher = url_client(
        {
            "https://acme.example.test/robots.txt": httpx2.Response(200, text=robots_txt),
            "https://acme.example.test/": httpx2.Response(200, text="<html>Welcome</html>"),
            "https://acme.example.test/careers": AssertionError("careers must not be fetched"),
            "https://acme.example.test/jobs": httpx2.Response(200, text="<html>Openings</html>"),
        }
    )

    result = asyncio.run(
        corroborate(fetcher, "acme", company("Acme", website_url="https://acme.example.test/"))
    )

    assert result is None


def test_a_500_home_page_contributes_nothing() -> None:
    fetcher = url_client(
        {
            "https://acme.example.test/": httpx2.Response(500),
            "https://acme.example.test/careers": httpx2.Response(404),
            "https://acme.example.test/jobs": httpx2.Response(404),
        }
    )

    result = asyncio.run(
        corroborate(fetcher, "acme", company("Acme", website_url="https://acme.example.test/"))
    )

    assert result is None


def test_more_than_three_redirects_is_none() -> None:
    origin = "https://acme.example.test"
    fetcher = url_client(
        {
            f"{origin}/": httpx2.Response(302, headers={"location": f"{origin}/r1"}),
            f"{origin}/r1": httpx2.Response(302, headers={"location": f"{origin}/r2"}),
            f"{origin}/r2": httpx2.Response(302, headers={"location": f"{origin}/r3"}),
            f"{origin}/r3": httpx2.Response(302, headers={"location": f"{origin}/r4"}),
            f"{origin}/careers": httpx2.Response(404),
            f"{origin}/jobs": httpx2.Response(404),
        }
    )

    result = asyncio.run(corroborate(fetcher, "acme", company("Acme", website_url=f"{origin}/")))

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


def test_verify_prefers_corroboration_over_identity_when_both_apply() -> None:
    fetcher = url_client(
        {
            "https://acme.example.test/": httpx2.Response(
                200, text='<a href="https://acme.boards.example.test/">Careers</a>'
            ),
        }
    )

    result = asyncio.run(
        verify(fetcher, "acme", company("Acme", website_url="https://acme.example.test/"))
    )

    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.evidence["kind"] == "website_link"


def test_verify_falls_back_to_identity_when_the_website_has_no_evidence() -> None:
    fetcher = url_client(
        {
            "https://acme.example.test/": httpx2.Response(404),
            "https://acme.example.test/careers": httpx2.Response(404),
            "https://acme.example.test/jobs": httpx2.Response(404),
            "https://acme.boards.example.test/": httpx2.Response(
                200, text="<title>Acme Careers</title>"
            ),
        }
    )

    result = asyncio.run(
        verify(fetcher, "acme", company("Acme", website_url="https://acme.example.test/"))
    )

    assert result.outcome is DiscoveryOutcome.NAMED
    assert result.evidence["kind"] == "site_title"
