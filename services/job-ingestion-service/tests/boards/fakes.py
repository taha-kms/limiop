"""Providers that exist only to exercise the framework.

Each has the shape of one real provider class without any real provider's
fields, so a framework test cannot pass by accident of Greenhouse's schema.
"""

from collections.abc import Iterator, Sequence
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, ValidationError

from job_ingestion.boards.provider import BoardProvider, PageRead, Request
from job_ingestion.boards.reading import json_body, json_object, record_list
from job_ingestion.boards.xml import parse_xml, records_in
from job_ingestion.contracts import RawRecord
from job_ingestion.errors import RecordValidationError
from job_ingestion.schemas import NormalizedJob

FAKE_BASE_URL = "https://boards.example.test"


class FakeRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    board: str
    id: str
    title: str
    description: str = "A job."
    company: str = "Acme"
    url: str = "https://example.test/apply"


class FakeValidator:
    def validate(self, record: RawRecord) -> FakeRecord:
        try:
            return FakeRecord.model_validate({**record, "id": str(record.get("id", ""))})
        except ValidationError as error:
            raise RecordValidationError("fake", str(error)) from error


class FakeNormalizer:
    def normalize(self, record: FakeRecord, raw: RawRecord) -> NormalizedJob:
        return NormalizedJob.model_validate(
            {
                "company": {"display_name": record.company},
                "title": record.title,
                "description": record.description,
                "application_url": record.url,
                "provenance": {
                    "source_key": "fake",
                    "source_job_id": f"{record.board}:{record.id}",
                    "source_url": record.url,
                    "raw_payload": dict(raw),
                },
            }
        )


def stated_company(records: Sequence[RawRecord]) -> str | None:
    for record in records:
        company = record.get("company")
        if isinstance(company, str) and company.strip():
            return company
    return None


def never_states(_records: Sequence[RawRecord]) -> str | None:
    return None


def single_request(base_url: str, slug: str, _cursor: object | None) -> Request:
    return Request(url=f"{base_url}/{slug}/jobs")


def read_jobs(slug: str, response: httpx2.Response) -> PageRead:
    body = json_object("fake", slug, response)
    return PageRead(records=record_list("fake", slug, body.get("jobs"), name="jobs"))


def json_provider(**overrides: Any) -> BoardProvider[FakeRecord]:
    """One request per board, JSON `jobs` array, states its company."""
    fields: dict[str, Any] = {
        "source_key": "fake",
        "display_name": "Fake Boards",
        "precedence": 15,
        "default_base_url": FAKE_BASE_URL,
        "default_boards": ("acme",),
        "validator": FakeValidator(),
        "normalizer": FakeNormalizer(),
        "board_request": single_request,
        "read_page": read_jobs,
        "stated_company": stated_company,
    }
    fields.update(overrides)
    return BoardProvider(**fields)


def paged_request(base_url: str, slug: str, cursor: object | None) -> Request:
    offset = cursor if isinstance(cursor, int) else 0
    return Request(url=f"{base_url}/{slug}/jobs", params={"offset": str(offset)})


def read_paged(slug: str, response: httpx2.Response) -> PageRead:
    body = json_object("fake", slug, response)
    records = record_list("fake", slug, body.get("jobs"), name="jobs")
    next_offset = body.get("next")
    return PageRead(
        records=records, next_cursor=next_offset if isinstance(next_offset, int) else None
    )


def paginated_provider() -> BoardProvider[FakeRecord]:
    """`offset` in the query, `next` in the body, `None` at the end."""
    return json_provider(board_request=paged_request, read_page=read_paged)


def xml_request(base_url: str, slug: str, _cursor: object | None) -> Request:
    return Request(url=f"{base_url}/{slug}/feed.xml")


def read_positions(slug: str, response: httpx2.Response) -> PageRead:
    return PageRead(records=records_in(parse_xml("fake", slug, response), "position"))


def xml_provider() -> BoardProvider[FakeRecord]:
    """An XML feed with one `position` element per posting, stating no company."""
    return json_provider(
        board_request=xml_request, read_page=read_positions, stated_company=never_states
    )


def detail_request(base_url: str, record: RawRecord) -> Request | None:
    identifier = record.get("id")
    return None if identifier is None else Request(url=f"{base_url}/postings/{identifier}")


def read_listing(slug: str, response: httpx2.Response) -> PageRead:
    """A listing without descriptions, as SmartRecruiters sends."""
    body = json_object("fake", slug, response)
    return PageRead(records=record_list("fake", slug, body.get("content"), name="content"))


def hydrated_provider() -> BoardProvider[FakeRecord]:
    return json_provider(read_page=read_listing, detail_request=detail_request)


def responding(*replies: httpx2.Response | Exception) -> httpx2.AsyncClient:
    """A client answering each request with the next reply, in order."""
    remaining: Iterator[httpx2.Response | Exception] = iter(replies)

    def handle(request: httpx2.Request) -> httpx2.Response:
        reply = next(remaining)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def routing(routes: dict[str, httpx2.Response | Exception]) -> httpx2.AsyncClient:
    """A client answering by URL path, for requests whose order is not fixed."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        reply = routes[request.url.path]
        if isinstance(reply, Exception):
            raise reply
        return reply

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


async def never_sleeps(_seconds: float) -> None:
    return None


def ok(body: Any) -> httpx2.Response:
    return httpx2.Response(200, json=body)


def jobs(*identifiers: int) -> dict[str, Any]:
    return {
        "jobs": [{"id": identifier, "title": f"Job {identifier}"} for identifier in identifiers]
    }


__all__ = [
    "FAKE_BASE_URL",
    "FakeRecord",
    "hydrated_provider",
    "jobs",
    "json_body",
    "json_provider",
    "never_sleeps",
    "ok",
    "paginated_provider",
    "responding",
    "routing",
    "xml_provider",
]
