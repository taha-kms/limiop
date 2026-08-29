"""Finding a company's board without anyone typing its name."""

import asyncio
from typing import Any

import httpx2

from job_ingestion.greenhouse.client import GreenhouseClient, GreenhouseConfig
from job_ingestion.greenhouse.discovery import (
    DiscoveryOutcome,
    belongs_to,
    candidate_slugs,
    discover,
    strip_legal_form,
)


def test_a_legal_suffix_is_not_part_of_the_name() -> None:
    """A board slug almost never carries one."""
    assert strip_legal_form("Acme GmbH") == "acme"
    assert strip_legal_form("Nordic Systems AB") == "nordic systems"
    assert strip_legal_form("Example Ltd.") == "example"


def test_a_name_that_is_only_a_legal_form_is_left_alone() -> None:
    assert strip_legal_form("GmbH") == "gmbh"


def test_slugs_are_ordered_most_likely_first() -> None:
    assert candidate_slugs("Nordic Systems AB") == ("nordicsystems", "nordic-systems", "nordic")


def test_a_single_word_company_proposes_one_slug() -> None:
    assert candidate_slugs("Hudl") == ("hudl",)


def test_a_name_with_nothing_usable_proposes_nothing() -> None:
    assert candidate_slugs("   ") == ()


def test_a_board_belongs_to_a_company_whatever_its_legal_form() -> None:
    """The aggregator says `Acme GmbH` where the board says `Acme`."""
    assert belongs_to("Acme", "Acme GmbH")
    assert belongs_to("ACME  GmbH", "acme")


def test_the_two_sides_may_disagree_about_spacing() -> None:
    """Measured: the aggregator stored `wppmedia`, the board says `WPP Media`.

    Rejecting that pair would refuse a board that is plainly the right one.
    """
    assert belongs_to("WPP Media", "wppmedia")
    assert belongs_to("Sum-Up", "SumUp")


def test_a_different_company_does_not_belong() -> None:
    """Separators are the only thing ignored, so a longer name stays different."""
    assert not belongs_to("Acme Health", "Acme")
    assert not belongs_to("Beta", "Acme")
    # Measured: a stored name carrying a stray digit is not the board's company.
    assert not belongs_to("Addepar", "Addepar1")


def board(company: str, count: int = 1) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "jobs": [
                {
                    "id": index,
                    "title": "Engineer",
                    "absolute_url": "https://example.test/apply",
                    "company_name": company,
                    "updated_at": "2026-01-01T00:00:00Z",
                    "location": {"name": "Berlin"},
                }
                for index in range(count)
            ]
        },
    )


def client_answering(*replies: httpx2.Response | Exception) -> GreenhouseClient:
    remaining = iter(replies)

    def handle(_request: httpx2.Request) -> httpx2.Response:
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def never_sleeps(_seconds: float) -> None:
        return None

    return GreenhouseClient(
        GreenhouseConfig(boards=("unused",), retry_backoff_seconds=0.0),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        sleeper=never_sleeps,
    )


def run(client: GreenhouseClient, company: str) -> Any:
    return asyncio.run(discover(client, company))


def test_a_board_stating_the_right_company_is_confirmed() -> None:
    result = run(client_answering(board("Hudl")), "Hudl")

    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.slug == "hudl"


def test_a_board_stating_somebody_else_is_rejected_rather_than_ingested() -> None:
    """The failure the hand-written list existed to prevent."""
    result = run(client_answering(board("Acme Health")), "Acme")

    assert result.outcome is DiscoveryOutcome.WRONG_COMPANY
    assert result.found_company == "Acme Health"


def test_a_missing_board_is_reported_as_not_found() -> None:
    missing = httpx2.Response(404, text="nope")
    result = run(client_answering(missing, missing, missing), "Nordic Systems AB")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND
    assert result.slug is None


def test_a_later_slug_is_tried_when_an_earlier_one_does_not_exist() -> None:
    result = run(
        client_answering(httpx2.Response(404), board("Nordic Systems")), "Nordic Systems AB"
    )

    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.slug == "nordic-systems"


def test_a_wrong_company_outranks_silence_in_the_report() -> None:
    """It names a slug that must never be polled, so it is what a reader acts on."""
    result = run(
        client_answering(board("Somebody Else"), httpx2.Response(404), httpx2.Response(404)),
        "Nordic Systems AB",
    )

    assert result.outcome is DiscoveryOutcome.WRONG_COMPANY


def test_an_unreachable_board_is_not_reported_as_absent() -> None:
    """`not found` says the company has no board. A timeout says nothing."""
    timeouts = [httpx2.TimeoutException("slow")] * 9
    result = run(client_answering(*timeouts), "Nordic Systems AB")

    assert result.outcome is DiscoveryOutcome.UNREACHABLE


def test_an_empty_board_confirms_nothing() -> None:
    """A board that states no company cannot vouch for one."""
    result = run(client_answering(board("Hudl", count=0)), "Hudl")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND


def test_a_company_with_no_usable_name_is_not_guessed_at() -> None:
    result = run(client_answering(), "   ")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND
