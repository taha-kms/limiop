from typing import Any

import httpx2
import pytest

from job_ingestion.boards.provider import BoardProvider, PageRead, Request
from job_ingestion.boards.reading import json_body, json_object, record_list
from job_ingestion.errors import SourceResponseError


def ok(body: Any) -> httpx2.Response:
    return httpx2.Response(200, json=body)


def test_a_json_body_is_returned_as_sent() -> None:
    assert json_body("src", "acme", ok([1, 2])) == [1, 2]


def test_a_body_that_is_not_json_is_refused() -> None:
    with pytest.raises(SourceResponseError, match="board acme is not valid JSON"):
        json_body("src", "acme", httpx2.Response(200, text="not json"))


def test_an_object_is_required_where_one_is_expected() -> None:
    assert json_object("src", "acme", ok({"jobs": []})) == {"jobs": []}
    with pytest.raises(SourceResponseError, match="board acme is not a JSON object"):
        json_object("src", "acme", ok([1, 2]))


def test_a_record_list_must_be_a_list_of_objects() -> None:
    assert record_list("src", "acme", [{"id": 1}], name="jobs") == ({"id": 1},)
    with pytest.raises(SourceResponseError, match="board acme has no jobs array"):
        record_list("src", "acme", None, name="jobs")
    with pytest.raises(SourceResponseError, match="board acme record 1 is not a JSON object"):
        record_list("src", "acme", [{"id": 1}, "nope"], name="jobs")


def test_a_request_defaults_to_no_parameters() -> None:
    assert Request(url="https://example.test").params == {}


def test_a_page_read_defaults_to_no_next_cursor() -> None:
    assert PageRead(records=()).next_cursor is None


def test_a_provider_is_a_frozen_value() -> None:
    provider: BoardProvider[Any] = BoardProvider(
        source_key="fake",
        display_name="Fake",
        precedence=1,
        default_base_url="https://example.test",
        default_boards=("acme",),
        validator=None,  # type: ignore[arg-type]
        normalizer=None,  # type: ignore[arg-type]
        board_request=lambda base, slug, cursor: Request(url=f"{base}/{slug}"),
        read_page=lambda slug, response: PageRead(records=()),
        stated_company=lambda records: None,
    )

    assert provider.detail_request is None
    with pytest.raises(AttributeError):
        provider.source_key = "other"  # type: ignore[misc]
