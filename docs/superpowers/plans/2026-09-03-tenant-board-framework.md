# Tenant-Board Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One generic tenant-board client, pipeline, discovery module, and DAG factory, with Greenhouse migrated onto them and behaving exactly as it does today.

**Architecture:** A frozen `BoardProvider` value carries everything specific to a provider (request shape, page reading, stated company, optional detail hydration, validator, normalizer). One `BoardClient` reads it. One `ingest_board_source` runs it. A registry lists providers and an Airflow factory emits one DAG per entry. Greenhouse keeps its public names as thin shims over the framework.

**Tech Stack:** Python 3.12, httpx2, pydantic 2, SQLAlchemy async, defusedxml, pytest, mypy strict, ruff, Apache Airflow 3.2.

**Spec:** `docs/superpowers/specs/2026-09-03-tenant-board-framework-design.md`

## Global Constraints

- Issue: #319. Branch: `refactor/319-tenant-board-framework`. Never commit on `main`.
- No AI, agent, model, or vendor identity anywhere in git: no trailers, no co-author lines, no session links (AGENTS.md §12).
- Commit messages: one line, imperative, developer-sounding (AGENTS.md §9–11).
- Ingestion service: `ruff format --check .`, `ruff check .`, `mypy` (strict), `pytest` must pass. Run from `services/job-ingestion-service` with `.venv/bin/<tool>`.
- Integration tests need `SKILLSYNC_TEST_DATABASE_URL=postgresql+psycopg://skillsync_test:skillsync_test@127.0.0.1:55432/skillsync_test` (a local `skillsync-test-db` container is running on that port). Without it they skip.
- Airflow tests: run from `airflow` with `.venv/bin/pytest`, `.venv/bin/ruff format --check .`, `.venv/bin/ruff check .`.
- Existing Greenhouse tests keep their assertions. Only import paths may change.
- Error message text the Greenhouse client tests match on must be preserved verbatim: `is not valid JSON`, `is not a JSON object`, `has no jobs array`, `record {index} is not a JSON object`, `returned status {code}`, `timed out`, `could not be reached`, `was rate limited`, `must not be blank`, `list of board names`.
- Docstring style: module docstrings explain *why*; comments only where logic is non-obvious. Match the tone of `job_ingestion/greenhouse/client.py`.
- `job_ingestion/boards/__init__.py` stays a docstring only. Importing it must not import the registry, or `greenhouse.provider` → `boards.provider` → `boards/__init__` → `registry` → `greenhouse.provider` cycles.

---

## File map

Create:
- `services/job-ingestion-service/job_ingestion/boards/__init__.py` — docstring only
- `services/job-ingestion-service/job_ingestion/boards/provider.py` — `Request`, `PageRead`, `BoardProvider`
- `services/job-ingestion-service/job_ingestion/boards/reading.py` — JSON body helpers with the shared error messages
- `services/job-ingestion-service/job_ingestion/boards/xml.py` — `parse_xml`, `element_to_record`, `records_in`
- `services/job-ingestion-service/job_ingestion/boards/client.py` — `BoardConfig`, `BoardClient`
- `services/job-ingestion-service/job_ingestion/boards/discovery.py` — moved from `greenhouse/discovery.py`, plus `UNVERIFIABLE`
- `services/job-ingestion-service/job_ingestion/boards/pipeline.py` — `configured_boards`, `configured_base_url`, `default_config`, `build_run`, `with_board_failures`, `ingest_board_source`
- `services/job-ingestion-service/job_ingestion/boards/registry.py` — `PROVIDERS`, `provider_for`
- `services/job-ingestion-service/job_ingestion/greenhouse/source.py` — constants shared by every Greenhouse module
- `services/job-ingestion-service/job_ingestion/greenhouse/provider.py` — `GREENHOUSE`
- `services/job-ingestion-service/tests/boards/__init__.py`, `fakes.py`, `test_xml.py`, `test_reading.py`, `test_client.py`, `test_hydration.py`, `test_discovery.py`, `test_pipeline.py`, `test_registry.py`
- `airflow/dags/board_ingestion.py` — DAG factory
- `airflow/tests/test_board_dag_structure.py`

Modify:
- `services/job-ingestion-service/pyproject.toml` — add `defusedxml`, `types-defusedxml`
- `services/job-ingestion-service/job_ingestion/greenhouse/client.py` — becomes shim
- `services/job-ingestion-service/job_ingestion/greenhouse/discovery.py` — becomes re-export
- `services/job-ingestion-service/job_ingestion/greenhouse/pipeline.py` — becomes shim
- `services/job-ingestion-service/job_ingestion/greenhouse/records.py`, `normalizer.py` — import `SOURCE_KEY` from `source.py`
- `services/job-ingestion-service/scripts/discover_boards.py` — `--source`
- `airflow/tests/test_dag_structure.py` — `ALLOWED_CALLS`
- `docs/deployment-baseline.md` — `base_url` setting

Delete:
- `airflow/dags/greenhouse_ingestion.py`
- `airflow/tests/test_greenhouse_dag_structure.py`

---

### Task 1: XML reading

**Files:**
- Modify: `services/job-ingestion-service/pyproject.toml`
- Create: `services/job-ingestion-service/job_ingestion/boards/__init__.py`
- Create: `services/job-ingestion-service/job_ingestion/boards/xml.py`
- Test: `services/job-ingestion-service/tests/boards/__init__.py`, `services/job-ingestion-service/tests/boards/test_xml.py`

**Interfaces:**
- Produces: `parse_xml(source_key: str, slug: str, response: httpx2.Response) -> Element`, `element_to_record(element: Element) -> dict[str, Any]`, `records_in(root: Element, tag: str) -> tuple[RawRecord, ...]`

- [ ] **Step 1: Add the dependency**

In `services/job-ingestion-service/pyproject.toml`, add to `dependencies`:

```toml
  "defusedxml>=0.7.1,<1.0.0",
```

and to `dev`:

```toml
  "types-defusedxml>=0.7.0,<1.0.0",
```

Install: `cd services/job-ingestion-service && VIRTUAL_ENV=.venv uv pip install -e '.[dev]'`

- [ ] **Step 2: Create the package and test package**

`services/job-ingestion-service/job_ingestion/boards/__init__.py`:

```python
"""Ingestion for providers shaped as one board per tenant.

A tenant-board provider answers one slug with every posting that tenant has.
Everything that varies between such providers is carried by a `BoardProvider`
value; everything that does not is implemented once here.

This package exports nothing from its root on purpose. `registry` imports the
providers and the providers import `provider`, so a root that imported the
registry would import itself.
"""
```

`services/job-ingestion-service/tests/boards/__init__.py`: empty file.

- [ ] **Step 3: Write the failing tests**

`services/job-ingestion-service/tests/boards/test_xml.py`:

```python
import httpx2
import pytest

from job_ingestion.boards.xml import element_to_record, parse_xml, records_in
from job_ingestion.errors import SourceResponseError

PERSONIO_SHAPED = b"""<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>1</id>
    <name>Engineer</name>
    <office>Berlin</office>
    <jobDescriptions>
      <jobDescription>
        <name>Role</name>
        <value><![CDATA[<p>Build things</p>]]></value>
      </jobDescription>
      <jobDescription>
        <name>Profile</name>
        <value>Ship things</value>
      </jobDescription>
    </jobDescriptions>
    <keywords/>
  </position>
  <position>
    <id>2</id>
    <name>Designer</name>
    <office/>
  </position>
</workzag-jobs>
"""


def response(body: bytes) -> httpx2.Response:
    return httpx2.Response(200, content=body)


def test_a_document_yields_one_record_per_item_element() -> None:
    root = parse_xml("feed", "acme", response(PERSONIO_SHAPED))

    records = records_in(root, "position")

    assert [record["id"] for record in records] == ["1", "2"]
    assert records[0]["name"] == "Engineer"


def test_a_leaf_is_its_text_and_an_empty_leaf_is_empty_text() -> None:
    root = parse_xml("feed", "acme", response(PERSONIO_SHAPED))

    records = records_in(root, "position")

    assert records[0]["office"] == "Berlin"
    assert records[1]["office"] == ""
    assert records[0]["keywords"] == ""


def test_repeated_children_become_a_list_and_cdata_is_kept() -> None:
    root = parse_xml("feed", "acme", response(PERSONIO_SHAPED))

    descriptions = records_in(root, "position")[0]["jobDescriptions"]["jobDescription"]

    assert [item["name"] for item in descriptions] == ["Role", "Profile"]
    assert descriptions[0]["value"] == "<p>Build things</p>"


def test_a_single_child_is_not_a_list() -> None:
    root = parse_xml("feed", "acme", response(b"<root><item><id>1</id></item></root>"))

    assert records_in(root, "item") == ({"id": "1"},)


def test_namespaces_are_dropped_from_names() -> None:
    body = b'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><item><content:encoded>x</content:encoded></item></rss>'

    root = parse_xml("feed", "acme", response(body))

    assert records_in(root, "item") == ({"encoded": "x"},)


def test_attributes_are_kept_with_a_marker() -> None:
    root = parse_xml("feed", "acme", response(b'<root><item lang="en"><id>1</id></item></root>'))

    assert records_in(root, "item") == ({"@lang": "en", "id": "1"},)


def test_element_to_record_reads_one_element() -> None:
    root = parse_xml("feed", "acme", response(b"<item><id>7</id></item>"))

    assert element_to_record(root) == {"id": "7"}


def test_malformed_xml_is_a_source_response_error() -> None:
    with pytest.raises(SourceResponseError, match="board acme is not valid XML"):
        parse_xml("feed", "acme", response(b"<root><unclosed></root>"))


def test_an_entity_expansion_is_refused() -> None:
    """Untrusted XML. A document that expands entities is an attack, not a feed."""
    body = b'<!DOCTYPE x [<!ENTITY a "aaaa">]><root><item>&a;</item></root>'

    with pytest.raises(SourceResponseError, match="is not valid XML"):
        parse_xml("feed", "acme", response(body))
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_xml.py -q --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_ingestion.boards.xml'`

- [ ] **Step 5: Implement**

`services/job-ingestion-service/job_ingestion/boards/xml.py`:

```python
"""Turning an XML feed into the mappings the rest of ingestion reads.

Validation and normalization take a mapping and never learn where it came
from. Two of the tenant-board providers publish XML, so the client turns each
item element into a mapping here and nothing downstream has to know.

Feeds are untrusted. The parser refuses document type declarations, entity
expansion, and external references, because the only thing any of those has
ever carried into a job feed is an attack.
"""

from typing import Any
from xml.etree.ElementTree import Element, ParseError

import httpx2
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import SourceResponseError


def parse_xml(source_key: str, slug: str, response: httpx2.Response) -> Element:
    """Parse one board's response, or say why it is not a feed."""
    try:
        return fromstring(
            response.content, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (ParseError, DefusedXmlException) as error:
        raise SourceResponseError(
            source_key, f"board {slug} is not valid XML: {error}"
        ) from error


def local_name(tag: str) -> str:
    """The element name without its namespace, so `content:encoded` reads as `encoded`."""
    return tag.rsplit("}", 1)[-1]


def element_to_record(element: Element) -> dict[str, Any]:
    """One element as a mapping.

    A child with children becomes a nested mapping; a child without becomes its
    text, and an empty child becomes empty text rather than nothing, so a
    validator sees the field the feed sent. Children that repeat become a list.
    Attributes are kept under an `@` prefix so they cannot collide with a child
    of the same name. A leaf's attributes are dropped: nothing reads them, and
    keeping them would make a leaf a mapping some of the time.
    """
    record: dict[str, Any] = {f"@{name}": value for name, value in element.attrib.items()}
    for child in element:
        name = local_name(child.tag)
        value: Any = element_to_record(child) if len(child) else (child.text or "").strip()
        if name not in record:
            record[name] = value
        elif isinstance(record[name], list):
            record[name].append(value)
        else:
            record[name] = [record[name], value]
    return record


def records_in(root: Element, tag: str) -> tuple[RawRecord, ...]:
    """Every element named `tag`, each as a mapping."""
    return tuple(element_to_record(element) for element in root.iter(tag))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_xml.py -q --no-cov`
Expected: 9 passed

- [ ] **Step 7: Lint and type-check**

Run: `cd services/job-ingestion-service && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: no errors. If mypy cannot find `defusedxml` stubs, confirm `types-defusedxml` installed (`.venv/bin/python -c "import defusedxml"` and `ls .venv/lib/python3.12/site-packages | grep defusedxml`).

- [ ] **Step 8: Commit**

```bash
git add services/job-ingestion-service/pyproject.toml services/job-ingestion-service/job_ingestion/boards services/job-ingestion-service/tests/boards
git commit -m "Add XML feed reading for board providers"
```

---

### Task 2: Provider contract and JSON reading helpers

**Files:**
- Create: `services/job-ingestion-service/job_ingestion/boards/provider.py`
- Create: `services/job-ingestion-service/job_ingestion/boards/reading.py`
- Test: `services/job-ingestion-service/tests/boards/test_reading.py`

**Interfaces:**
- Produces:
  - `Request(url: str, params: Mapping[str, str] = {})`
  - `PageRead(records: tuple[RawRecord, ...], next_cursor: object | None = None)`
  - `BoardProvider[ProviderRecordT]` with fields `source_key`, `display_name`, `precedence`, `default_base_url`, `default_boards`, `validator`, `normalizer`, `board_request: Callable[[str, str, object | None], Request]`, `read_page: Callable[[str, httpx2.Response], PageRead]`, `stated_company: Callable[[Sequence[RawRecord]], str | None]`, `detail_request: Callable[[RawRecord], Request | None] | None = None`
  - `json_body(source_key, slug, response) -> Any`, `json_object(source_key, slug, response) -> dict[str, Any]`, `record_list(source_key, slug, value, *, name) -> tuple[RawRecord, ...]`

- [ ] **Step 1: Write the failing tests**

`services/job-ingestion-service/tests/boards/test_reading.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_reading.py -q --no-cov`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the contract**

`services/job-ingestion-service/job_ingestion/boards/provider.py`:

```python
"""What one tenant-board provider has to say about itself.

A provider is a value, not a class to inherit from. The client reads it; the
provider never sees the client. That keeps every provider-specific decision in
one place and every shared one out of it.

The stage contracts for validation and normalization are the ones in
`contracts.py`. This module adds only what the client needs to fetch and to
verify a board, which those contracts deliberately do not cover.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import httpx2

from job_ingestion.contracts import JobRecordNormalizer, JobRecordValidator, RawRecord


@dataclass(frozen=True, slots=True)
class Request:
    """One HTTP GET the client should make."""

    url: str
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageRead:
    """What one response held, and how to ask for the rest.

    `next_cursor` is whatever the provider needs to ask for the next page: an
    offset, a page number, a token. `None` means there is no next page. What
    the value is belongs to the provider and the client never inspects it.
    """

    records: tuple[RawRecord, ...]
    next_cursor: object | None = None


@dataclass(frozen=True, slots=True)
class BoardProvider[ProviderRecordT]:
    """Everything that differs between one tenant-board provider and another.

    `board_request(base_url, slug, cursor)` names the request for one page of
    one board. The first call passes `cursor=None`.

    `read_page(slug, response)` turns a successful response into records and
    the next cursor, or raises `SourceResponseError` when the body is not the
    documented shape. The client has already checked the status code. This is
    where a JSON key is chosen or an XML element is walked; it must not
    inspect job fields, which is validation's job.

    `stated_company(records)` is the company a board says its postings belong
    to, or `None` when the feed never says. Discovery reads it to confirm a
    guessed slug. A provider that cannot state one makes every guess
    unverifiable, and discovery reports that rather than confirming anything.

    `detail_request(record)`, when present, names a second request whose JSON
    object body is merged over the listing record before validation. For
    providers whose listing omits the description.
    """

    source_key: str
    display_name: str
    precedence: int
    default_base_url: str
    default_boards: tuple[str, ...]
    validator: JobRecordValidator[ProviderRecordT]
    normalizer: JobRecordNormalizer[ProviderRecordT]
    board_request: Callable[[str, str, object | None], Request]
    read_page: Callable[[str, httpx2.Response], PageRead]
    stated_company: Callable[[Sequence[RawRecord]], str | None]
    detail_request: Callable[[RawRecord], Request | None] | None = None
```

- [ ] **Step 4: Implement the JSON helpers**

`services/job-ingestion-service/job_ingestion/boards/reading.py`:

```python
"""Reading a JSON board response without trusting it.

Every JSON provider asks the same three questions of a body: is it JSON, is it
an object, is this an array of objects. The answers, and the words used when
the answer is no, are kept here so every provider reports the same failure
the same way.
"""

from typing import Any

import httpx2

from job_ingestion.contracts import RawRecord
from job_ingestion.errors import SourceResponseError


def json_body(source_key: str, slug: str, response: httpx2.Response) -> Any:
    try:
        return response.json()
    except ValueError as error:
        raise SourceResponseError(
            source_key, f"board {slug} is not valid JSON: {error}"
        ) from error


def json_object(source_key: str, slug: str, response: httpx2.Response) -> dict[str, Any]:
    body = json_body(source_key, slug, response)
    if not isinstance(body, dict):
        raise SourceResponseError(source_key, f"board {slug} is not a JSON object")
    return body


def record_list(
    source_key: str, slug: str, value: object, *, name: str
) -> tuple[RawRecord, ...]:
    """The records under one key, each of which must be an object."""
    if not isinstance(value, list):
        raise SourceResponseError(source_key, f"board {slug} has no {name} array")
    records: list[RawRecord] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise SourceResponseError(
                source_key, f"board {slug} record {index} is not a JSON object"
            )
        records.append(record)
    return tuple(records)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_reading.py -q --no-cov`
Expected: 7 passed

- [ ] **Step 6: Lint, type-check, commit**

Run: `cd services/job-ingestion-service && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: clean.

```bash
git add services/job-ingestion-service/job_ingestion/boards services/job-ingestion-service/tests/boards
git commit -m "Add the board provider contract"
```

---

### Task 3: Generic board client

**Files:**
- Create: `services/job-ingestion-service/job_ingestion/boards/client.py`
- Test: `services/job-ingestion-service/tests/boards/fakes.py`, `services/job-ingestion-service/tests/boards/test_client.py`

**Interfaces:**
- Consumes: `BoardProvider`, `Request`, `PageRead` (Task 2); `parse_xml`, `records_in` (Task 1); `json_object`, `record_list` (Task 2); `is_rate_limited`, `retry_delay` from `job_ingestion.rate_limit`
- Produces:
  - `BoardConfig(boards=(), base_url=None, timeout_seconds=20.0, max_attempts=3, retry_backoff_seconds=0.5, max_pages_per_board=100, detail_concurrency=4)`
  - `BoardClient(provider, config=BoardConfig(), http_client=None, sleeper=asyncio.sleep)` with `source_key`, `base_url`, `reached_the_end`, `failures: list[RecordFailure]`, `_http_client`, `fetch_board(slug) -> RawPage`, `fetch_pages() -> AsyncIterator[RawPage]`, `aclose()`, async context manager
  - Test fakes: `json_provider()`, `paginated_provider()`, `xml_provider()`, `responding(*replies)`, `never_sleeps`

- [ ] **Step 1: Write the fakes**

`services/job-ingestion-service/tests/boards/fakes.py`:

```python
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
    return PageRead(records=records, next_cursor=next_offset if isinstance(next_offset, int) else None)


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


def detail_request(record: RawRecord) -> Request | None:
    identifier = record.get("id")
    return None if identifier is None else Request(url=f"{FAKE_BASE_URL}/postings/{identifier}")


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
    return {"jobs": [{"id": identifier, "title": f"Job {identifier}"} for identifier in identifiers]}


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
```

- [ ] **Step 2: Write the failing client tests**

`services/job-ingestion-service/tests/boards/test_client.py`:

```python
import asyncio
from typing import Any

import httpx2
import pytest

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.contracts import IngestionStage, RawPage
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from tests.boards.fakes import (
    FAKE_BASE_URL,
    jobs,
    json_provider,
    never_sleeps,
    ok,
    paginated_provider,
    responding,
    xml_provider,
)


def client(
    *replies: httpx2.Response | Exception,
    provider: BoardProvider[Any] | None = None,
    **overrides: Any,
) -> BoardClient:
    settings: dict[str, Any] = {"boards": ("acme",), "retry_backoff_seconds": 0.0}
    settings.update(overrides)
    return BoardClient(
        provider if provider is not None else json_provider(),
        BoardConfig(**settings),
        http_client=responding(*replies),
        sleeper=never_sleeps,
    )


def fetch(fetcher: BoardClient, slug: str = "acme") -> RawPage:
    return asyncio.run(fetcher.fetch_board(slug))


def collect(fetcher: BoardClient) -> list[RawPage]:
    async def run() -> list[RawPage]:
        return [page async for page in fetcher.fetch_pages()]

    return asyncio.run(run())


def test_the_client_is_named_by_its_provider() -> None:
    fetcher = client()

    assert fetcher.source_key == "fake"
    assert fetcher.base_url == FAKE_BASE_URL


def test_a_configured_base_url_wins_over_the_provider_default() -> None:
    assert client(base_url="https://eu.example.test").base_url == "https://eu.example.test"


def test_a_board_is_one_page_of_records_stamped_with_its_slug() -> None:
    pages = collect(client(ok(jobs(1, 2))))

    assert len(pages) == 1
    assert [record["id"] for record in pages[0].records] == [1, 2]
    assert {record["board"] for record in pages[0].records} == {"acme"}
    assert pages[0].next_page is None


def test_the_provider_names_the_request() -> None:
    seen: list[httpx2.URL] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url)
        return ok(jobs(1))

    fetcher = BoardClient(
        json_provider(),
        BoardConfig(boards=("acme",)),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    collect(fetcher)

    assert str(seen[0]) == f"{FAKE_BASE_URL}/acme/jobs"


def test_every_configured_board_is_read_and_the_end_is_reached() -> None:
    fetcher = client(ok(jobs(1)), ok(jobs(2)), boards=("acme", "globex"))

    pages = collect(fetcher)

    assert {record["board"] for page in pages for record in page.records} == {"acme", "globex"}
    assert fetcher.reached_the_end is True


def test_one_unreachable_board_does_not_discard_the_others() -> None:
    fetcher = client(
        httpx2.ConnectError("no route"),
        httpx2.ConnectError("no route"),
        httpx2.ConnectError("no route"),
        ok(jobs(1)),
        boards=("gone", "acme"),
    )

    pages = collect(fetcher)

    assert len(pages) == 1
    assert len(fetcher.failures) == 1
    assert fetcher.failures[0].stage is IngestionStage.FETCH
    assert "gone" in fetcher.failures[0].reason
    assert fetcher.reached_the_end is False


def test_a_non_success_status_is_reported_not_retried() -> None:
    fetcher = client(httpx2.Response(404), boards=("retired",))

    assert collect(fetcher) == []
    assert "returned status 404" in fetcher.failures[0].reason


def test_a_transport_failure_is_retried_before_giving_up() -> None:
    fetcher = client(httpx2.ConnectError("flaky"), ok(jobs(1)))

    assert len(collect(fetcher)) == 1
    assert fetcher.failures == []


def test_a_board_that_never_answers_raises_after_its_attempts() -> None:
    fetcher = client(*[httpx2.ConnectError("down")] * 3)

    with pytest.raises(SourceUnavailableError, match="could not be reached"):
        fetch(fetcher)


def test_a_timeout_is_reported_as_a_timeout() -> None:
    fetcher = client(*[httpx2.TimeoutException("slow")] * 3)

    with pytest.raises(SourceUnavailableError, match="timed out"):
        fetch(fetcher)


def test_an_unusable_body_is_the_providers_error() -> None:
    with pytest.raises(SourceResponseError, match="has no jobs array"):
        fetch(client(ok({"data": []})))


def test_a_rate_limited_board_is_retried_after_the_asked_wait() -> None:
    slept: list[float] = []

    async def sleeper(seconds: float) -> None:
        slept.append(seconds)

    fetcher = BoardClient(
        json_provider(),
        BoardConfig(boards=("acme",), retry_backoff_seconds=0.25),
        http_client=responding(httpx2.Response(429, headers={"retry-after": "2"}), ok(jobs(1))),
        sleeper=sleeper,
    )

    assert fetch(fetcher).records
    assert slept == [2.0]


def test_a_board_that_stays_rate_limited_still_fails() -> None:
    fetcher = client(*[httpx2.Response(429)] * 3)

    with pytest.raises(SourceUnavailableError, match="rate limited"):
        fetch(fetcher)


def test_pages_are_walked_until_the_provider_says_there_are_no_more() -> None:
    seen: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.params["offset"])
        replies = {
            "0": {"jobs": [{"id": 1, "title": "One"}], "next": 1},
            "1": {"jobs": [{"id": 2, "title": "Two"}], "next": 2},
            "2": {"jobs": [{"id": 3, "title": "Three"}]},
        }
        return ok(replies[request.url.params["offset"]])

    fetcher = BoardClient(
        paginated_provider(),
        BoardConfig(boards=("acme",)),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    page = fetch(fetcher)

    assert [record["id"] for record in page.records] == [1, 2, 3]
    assert seen == ["0", "1", "2"]


def test_a_board_that_never_ends_is_refused_rather_than_walked_forever() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        offset = int(request.url.params["offset"])
        return ok({"jobs": [{"id": offset, "title": "Again"}], "next": offset + 1})

    fetcher = BoardClient(
        paginated_provider(),
        BoardConfig(boards=("acme",), max_pages_per_board=3),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    with pytest.raises(SourceResponseError, match="did not end within 3 pages"):
        fetch(fetcher)


def test_an_xml_feed_reads_like_any_other_board() -> None:
    body = b"<feed><position><id>1</id><title>One</title></position></feed>"
    fetcher = client(httpx2.Response(200, content=body), provider=xml_provider())

    page = fetch(fetcher)

    assert page.records == ({"id": "1", "title": "One", "board": "acme"},)


def test_no_boards_configured_reads_nothing_and_reaches_the_end() -> None:
    fetcher = client(boards=())

    assert collect(fetcher) == []
    assert fetcher.reached_the_end is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("timeout_seconds", 0.0, id="timeout"),
        pytest.param("max_attempts", 0, id="attempts"),
        pytest.param("retry_backoff_seconds", -1.0, id="backoff"),
        pytest.param("max_pages_per_board", 0, id="pages"),
        pytest.param("detail_concurrency", 0, id="concurrency"),
        pytest.param("boards", ("  ",), id="blank board"),
    ],
)
def test_a_setting_without_a_bound_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        BoardConfig(**{field: value})  # type: ignore[arg-type]


def test_the_client_closes_only_what_it_created() -> None:
    supplied = responding()

    async def run() -> None:
        async with BoardClient(json_provider(), http_client=supplied):
            pass

    asyncio.run(run())

    assert supplied.is_closed is False


def test_the_client_closes_what_it_created() -> None:
    async def run() -> httpx2.AsyncClient:
        fetcher = BoardClient(json_provider())
        async with fetcher:
            pass
        return fetcher._http_client

    assert asyncio.run(run()).is_closed is True
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_client.py -q --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_ingestion.boards.client'`

- [ ] **Step 4: Implement the client (without hydration; Task 4 adds it)**

`services/job-ingestion-service/job_ingestion/boards/client.py`:

```python
"""HTTP access to any provider shaped as one board per tenant.

Transport only. Returns untrusted provider payloads and never inspects a job
field, so validation and normalization stay testable without a network.

One source, many boards. A board is where a company publishes; the provider
is the system it publishes on. Each board becomes one page, whatever number
of requests it took to read, because the run and reconciliation reason about
boards rather than requests.

Which boards to read is configured. Finding them is a separate problem, because
a wrong guess ingests one company's postings under another company's name.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import httpx2

from job_ingestion.boards.provider import BoardProvider, Request
from job_ingestion.boards.reading import json_object
from job_ingestion.contracts import IngestionStage, RawPage, RawRecord, RecordFailure
from job_ingestion.errors import SourceResponseError, SourceUnavailableError
from job_ingestion.rate_limit import is_rate_limited, retry_delay


@dataclass(frozen=True, slots=True)
class BoardConfig:
    """Bounded transport settings and the boards to read.

    `base_url` of `None` means the provider's own. It is a setting at all so a
    deployment can read a provider's regional host without a code change.
    """

    boards: tuple[str, ...] = ()
    base_url: str | None = None
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    retry_backoff_seconds: float = 0.5
    # A board that keeps answering with a next page is a provider bug or a
    # loop, and either way not something to walk without end.
    max_pages_per_board: int = 100
    detail_concurrency: int = 4

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")
        if self.max_pages_per_board < 1:
            raise ValueError("max_pages_per_board must be at least 1")
        if self.detail_concurrency < 1:
            raise ValueError("detail_concurrency must be at least 1")
        for board in self.boards:
            if not board.strip():
                raise ValueError("a board name must not be blank")


@dataclass
class BoardClient:
    """Fetches untrusted postings from every configured board of one provider."""

    provider: BoardProvider[Any]
    config: BoardConfig = field(default_factory=BoardConfig)
    http_client: httpx2.AsyncClient | None = None
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep

    def __post_init__(self) -> None:
        self._owns_http_client = self.http_client is None
        self._http_client = (
            self.http_client
            if self.http_client is not None
            else httpx2.AsyncClient(timeout=self.config.timeout_seconds)
        )
        # Boards that could not be read. Collected rather than raised, so one
        # unreachable company does not discard every other company's postings,
        # and reported afterwards so it is not lost either.
        self.failures: list[RecordFailure] = []
        self._reached_the_end = False
        self._dropped_a_record = False

    @property
    def source_key(self) -> str:
        return self.provider.source_key

    @property
    def base_url(self) -> str:
        return self.config.base_url or self.provider.default_base_url

    @property
    def reached_the_end(self) -> bool:
        """Whether every configured board was read in full.

        A board that could not be read leaves that company's postings unseen,
        and an unseen posting is indistinguishable from one that is gone, so a
        single skipped board denies the whole run. So does a single posting
        whose detail could not be read.
        """
        return self._reached_the_end

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client if this client created it."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def request(self, slug: str, request: Request) -> httpx2.Response:
        """Make one request, retrying what may succeed later.

        Retries transport failures and rate limits, at most `max_attempts`
        times. Any other answer is returned as it is: a board that answers is
        answering, and asking again will not change what it said. A rate
        limit is the exception, because it is a request to wait rather than a
        refusal.
        """
        last_failure: SourceUnavailableError | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            delay = self.config.retry_backoff_seconds
            try:
                response = await self._http_client.get(
                    request.url,
                    params=dict(request.params),
                    timeout=self.config.timeout_seconds,
                )
            except httpx2.TimeoutException as error:
                last_failure = SourceUnavailableError(
                    self.source_key, f"board {slug} timed out: {error}"
                )
            except httpx2.TransportError as error:
                last_failure = SourceUnavailableError(
                    self.source_key, f"board {slug} could not be reached: {error}"
                )
            else:
                if not is_rate_limited(response):
                    return response
                last_failure = SourceUnavailableError(
                    self.source_key, f"board {slug} was rate limited"
                )
                delay = retry_delay(response, fallback=delay)

            if attempt < self.config.max_attempts:
                await self.sleeper(delay)

        raise (
            last_failure
            if last_failure is not None
            else SourceUnavailableError(self.source_key, f"board {slug} could not be fetched")
        )

    async def fetch_board(self, slug: str) -> RawPage:
        """Return every posting on one board, however many pages it takes."""
        records: list[RawRecord] = []
        cursor: object | None = None
        for _ in range(self.config.max_pages_per_board):
            response = await self.request(slug, self.provider.board_request(self.base_url, slug, cursor))
            if response.status_code != httpx2.codes.OK:
                raise SourceResponseError(
                    self.source_key,
                    f"board {slug} returned status {response.status_code}",
                    status_code=response.status_code,
                )
            page = self.provider.read_page(slug, response)
            # The board is stamped on the record because a posting identifier
            # is only unique within its own board, and provenance needs one
            # that is unique within the source.
            records.extend({**record, "board": slug} for record in page.records)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        else:
            raise SourceResponseError(
                self.source_key,
                f"board {slug} did not end within {self.config.max_pages_per_board} pages",
            )

        return RawPage(records=tuple(records), next_page=None)

    async def fetch_pages(self) -> AsyncIterator[RawPage]:
        """Yield one page per board, skipping boards that cannot be read.

        A board is an independent company. One of them going away says nothing
        about the others, so its failure is recorded and the run continues.
        """
        self._reached_the_end = False
        self._dropped_a_record = False
        skipped = False
        for board in self.config.boards:
            try:
                yield await self.fetch_board(board)
            except (SourceResponseError, SourceUnavailableError) as error:
                skipped = True
                self.failures.append(
                    RecordFailure(stage=IngestionStage.FETCH, reason=error.message)
                )
        self._reached_the_end = not skipped and not self._dropped_a_record
```

Leave the `json_object` import in place even though nothing uses it yet; Task 4 does. If ruff flags it as unused (F401), remove it now and re-add in Task 4.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_client.py -q --no-cov`
Expected: 21 passed

- [ ] **Step 6: Lint, type-check, commit**

Run: `cd services/job-ingestion-service && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: clean.

```bash
git add services/job-ingestion-service/job_ingestion/boards/client.py services/job-ingestion-service/tests/boards
git commit -m "Add a generic tenant-board client"
```

---

### Task 4: Detail hydration

**Files:**
- Modify: `services/job-ingestion-service/job_ingestion/boards/client.py`
- Test: `services/job-ingestion-service/tests/boards/test_hydration.py`

**Interfaces:**
- Consumes: `BoardClient`, `BoardConfig` (Task 3); `hydrated_provider`, `routing`, `ok`, `never_sleeps` (Task 3 fakes)
- Produces: `BoardClient.hydrate(slug, records) -> list[RawRecord]`, called by `fetch_board` when `provider.detail_request` is set

- [ ] **Step 1: Write the failing tests**

`services/job-ingestion-service/tests/boards/test_hydration.py`:

```python
import asyncio

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.contracts import IngestionStage, RawPage
from tests.boards.fakes import hydrated_provider, never_sleeps, ok, routing


def listing(*identifiers: int) -> httpx2.Response:
    return ok({"content": [{"id": identifier, "title": f"Job {identifier}"} for identifier in identifiers]})


def detail(identifier: int) -> httpx2.Response:
    return ok({"id": identifier, "description": f"Details of {identifier}"})


def client(routes: dict[str, httpx2.Response | Exception]) -> BoardClient:
    return BoardClient(
        hydrated_provider(),
        BoardConfig(boards=("acme",), retry_backoff_seconds=0.0),
        http_client=routing(routes),
        sleeper=never_sleeps,
    )


def collect(fetcher: BoardClient) -> list[RawPage]:
    async def run() -> list[RawPage]:
        return [page async for page in fetcher.fetch_pages()]

    return asyncio.run(run())


def test_each_record_is_merged_with_its_detail_in_listing_order() -> None:
    fetcher = client(
        {"/acme/jobs": listing(1, 2), "/postings/1": detail(1), "/postings/2": detail(2)}
    )

    pages = collect(fetcher)

    assert [record["id"] for record in pages[0].records] == [1, 2]
    assert pages[0].records[0]["description"] == "Details of 1"
    assert pages[0].records[0]["board"] == "acme"
    assert fetcher.reached_the_end is True


def test_a_record_whose_detail_cannot_be_read_is_dropped_and_denies_the_end() -> None:
    """A posting the run could not read looks exactly like one that is gone."""
    fetcher = client(
        {
            "/acme/jobs": listing(1, 2),
            "/postings/1": detail(1),
            "/postings/2": httpx2.Response(500),
        }
    )

    pages = collect(fetcher)

    assert [record["id"] for record in pages[0].records] == [1]
    assert len(fetcher.failures) == 1
    assert fetcher.failures[0].stage is IngestionStage.FETCH
    assert fetcher.failures[0].source_job_id == "acme:2"
    assert "returned status 500" in fetcher.failures[0].reason
    assert fetcher.reached_the_end is False


def test_an_unreachable_detail_is_retried_then_dropped() -> None:
    attempts: list[str] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        attempts.append(request.url.path)
        if request.url.path == "/acme/jobs":
            return listing(1)
        raise httpx2.ConnectError("down")

    fetcher = BoardClient(
        hydrated_provider(),
        BoardConfig(boards=("acme",), retry_backoff_seconds=0.0, max_attempts=2),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        sleeper=never_sleeps,
    )

    pages = collect(fetcher)

    assert pages[0].records == ()
    assert attempts.count("/postings/1") == 2
    assert "could not be reached" in fetcher.failures[0].reason


def test_a_detail_that_is_not_an_object_is_dropped() -> None:
    fetcher = client({"/acme/jobs": listing(1), "/postings/1": ok([1])})

    pages = collect(fetcher)

    assert pages[0].records == ()
    assert "is not a JSON object" in fetcher.failures[0].reason


def test_a_record_the_provider_has_no_detail_for_passes_through() -> None:
    fetcher = client({"/acme/jobs": ok({"content": [{"title": "No id"}]})})

    pages = collect(fetcher)

    assert pages[0].records == ({"title": "No id", "board": "acme"},)
    assert fetcher.reached_the_end is True


def test_details_are_fetched_at_most_concurrency_at_a_time() -> None:
    in_flight = 0
    peak = 0

    async def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal in_flight, peak
        if request.url.path == "/acme/jobs":
            return listing(1, 2, 3, 4, 5)
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return detail(int(request.url.path.rsplit("/", 1)[-1]))

    fetcher = BoardClient(
        hydrated_provider(),
        BoardConfig(boards=("acme",), detail_concurrency=2),
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )

    pages = collect(fetcher)

    assert len(pages[0].records) == 5
    assert peak <= 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_hydration.py -q --no-cov`
Expected: FAIL — records lack `description`, `reached_the_end` wrong, or `AttributeError`

- [ ] **Step 3: Implement hydration**

In `services/job-ingestion-service/job_ingestion/boards/client.py`, replace the `return RawPage(...)` at the end of `fetch_board` with:

```python
        if self.provider.detail_request is not None:
            records = await self.hydrate(slug, records)
        return RawPage(records=tuple(records), next_page=None)
```

and add these methods to `BoardClient` after `fetch_board`:

```python
    async def hydrate(self, slug: str, records: list[RawRecord]) -> list[RawRecord]:
        """Merge each record with the detail the provider asks for.

        Order is the listing's. A record whose detail cannot be read is
        dropped rather than passed on without it, because a posting without
        its text cannot be normalized and would only fail later with a less
        useful reason. The drop is recorded as a fetch failure, and the board
        is no longer fully read: reconciliation must not conclude the posting
        is gone.
        """
        detail_request = self.provider.detail_request
        assert detail_request is not None
        semaphore = asyncio.Semaphore(self.config.detail_concurrency)

        async def one(record: RawRecord) -> RawRecord | RecordFailure:
            request = detail_request(record)
            if request is None:
                return record
            async with semaphore:
                try:
                    response = await self.request(slug, request)
                    if response.status_code != httpx2.codes.OK:
                        raise SourceResponseError(
                            self.source_key,
                            f"board {slug} returned status {response.status_code}",
                            status_code=response.status_code,
                        )
                    detail = json_object(self.source_key, slug, response)
                except (SourceResponseError, SourceUnavailableError) as error:
                    return RecordFailure(
                        stage=IngestionStage.FETCH,
                        reason=f"posting detail could not be read: {error.message}",
                        source_job_id=self._identifier(slug, record),
                    )
            return {**record, **detail}

        hydrated: list[RawRecord] = []
        for outcome in await asyncio.gather(*(one(record) for record in records)):
            if isinstance(outcome, RecordFailure):
                self._dropped_a_record = True
                self.failures.append(outcome)
            else:
                hydrated.append(outcome)
        return hydrated

    @staticmethod
    def _identifier(slug: str, record: RawRecord) -> str | None:
        identifier = record.get("id")
        if isinstance(identifier, int | str) and str(identifier).strip():
            return f"{slug}:{identifier}"
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards -q --no-cov`
Expected: all pass (test_hydration: 6 passed)

- [ ] **Step 5: Lint, type-check, commit**

Run: `cd services/job-ingestion-service && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: clean.

```bash
git add services/job-ingestion-service/job_ingestion/boards/client.py services/job-ingestion-service/tests/boards/test_hydration.py
git commit -m "Hydrate listings whose provider omits the description"
```

---

### Task 5: Provider-agnostic discovery

**Files:**
- Create: `services/job-ingestion-service/job_ingestion/boards/discovery.py`
- Modify: `services/job-ingestion-service/job_ingestion/greenhouse/discovery.py` (becomes re-export)
- Test: `services/job-ingestion-service/tests/boards/test_discovery.py`

**Interfaces:**
- Consumes: `BoardClient` (Task 3); `json_provider`, `xml_provider`, `responding`, `never_sleeps`, `ok`, `jobs` (fakes)
- Produces: `DiscoveryOutcome` (`CONFIRMED`, `WRONG_COMPANY`, `UNVERIFIABLE`, `NOT_FOUND`, `UNREACHABLE`), `DiscoveryResult`, `LEGAL_SUFFIXES`, `strip_legal_form`, `candidate_slugs`, `belongs_to`, `discover(client: BoardClient, company_name: str) -> DiscoveryResult`

- [ ] **Step 1: Write the failing tests**

`services/job-ingestion-service/tests/boards/test_discovery.py`:

```python
import asyncio
from typing import Any

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome, discover
from job_ingestion.boards.provider import BoardProvider
from tests.boards.fakes import json_provider, never_sleeps, ok, responding, xml_provider


def board(company: str, count: int = 1) -> httpx2.Response:
    return ok({"jobs": [{"id": index, "title": "Engineer", "company": company} for index in range(count)]})


def client(*replies: httpx2.Response | Exception, provider: BoardProvider[Any] | None = None) -> BoardClient:
    return BoardClient(
        provider if provider is not None else json_provider(),
        BoardConfig(boards=(), retry_backoff_seconds=0.0),
        http_client=responding(*replies),
        sleeper=never_sleeps,
    )


def run(fetcher: BoardClient, company: str) -> Any:
    return asyncio.run(discover(fetcher, company))


def test_the_provider_says_whose_board_answered() -> None:
    result = run(client(board("Acme")), "Acme GmbH")

    assert result.outcome is DiscoveryOutcome.CONFIRMED
    assert result.slug == "acme"
    assert result.found_company == "Acme"


def test_a_board_stating_somebody_else_is_rejected() -> None:
    result = run(client(board("Globex"), board("Globex"), board("Globex")), "Acme")

    assert result.outcome is DiscoveryOutcome.WRONG_COMPANY
    assert result.found_company == "Globex"


def test_a_feed_that_never_states_a_company_is_unverifiable() -> None:
    """A board answered. Nothing says whose, so nothing is confirmed."""
    body = b"<feed><position><id>1</id><title>One</title></position></feed>"
    fetcher = client(httpx2.Response(200, content=body), provider=xml_provider())

    result = run(fetcher, "Acme")

    assert result.outcome is DiscoveryOutcome.UNVERIFIABLE
    assert result.slug == "acme"
    assert result.found_company is None


def test_an_unverifiable_board_stops_the_search() -> None:
    """Every later guess would be as unverifiable, and each costs a request."""
    body = b"<feed><position><id>1</id><title>One</title></position></feed>"
    fetcher = client(httpx2.Response(200, content=body), provider=xml_provider())

    result = run(fetcher, "Acme Health Group")

    assert result.outcome is DiscoveryOutcome.UNVERIFIABLE
    assert result.slug == "acmehealthgroup"


def test_an_empty_board_confirms_nothing() -> None:
    result = run(client(ok({"jobs": []}), ok({"jobs": []}), ok({"jobs": []})), "Acme Health Group")

    assert result.outcome is DiscoveryOutcome.NOT_FOUND
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_discovery.py -q --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'job_ingestion.boards.discovery'`

- [ ] **Step 3: Move discovery**

Create `services/job-ingestion-service/job_ingestion/boards/discovery.py` by moving the whole of `job_ingestion/greenhouse/discovery.py` and applying these changes:

1. Replace the `TYPE_CHECKING` import block with:

```python
from typing import TYPE_CHECKING

from platform_db.models.catalog import normalize_company_name

from job_ingestion.contracts import RawPage
from job_ingestion.errors import SourceResponseError, SourceUnavailableError

if TYPE_CHECKING:
    from job_ingestion.boards.client import BoardClient
```

2. In the module docstring, replace the two occurrences of `Greenhouse board` with `board` and add this paragraph at the end:

```text
Not every feed states a company. Where it does not, a guess that answers can
be reported and cannot be confirmed, and that is its own outcome rather than
a weaker confirmation. Adding such a board stays a deliberate act by someone
who looked at the careers page.
```

3. In `DiscoveryOutcome`, add after `WRONG_COMPANY`:

```python
    # The board answered with postings and the feed states no company, so
    # nothing here can say whose they are.
    UNVERIFIABLE = "unverifiable"
```

4. Change the `discover` signature to `async def discover(client: "BoardClient", company_name: str) -> DiscoveryResult:` and replace its body from `mismatch: DiscoveryResult | None = None` to the end with:

```python
    mismatch: DiscoveryResult | None = None
    unreachable: DiscoveryResult | None = None
    for slug in slugs:
        try:
            page = await client.fetch_board(slug)
        except SourceResponseError:
            # The board does not exist, which is the ordinary answer for a
            # guess and says nothing about the next one.
            continue
        except SourceUnavailableError:
            unreachable = DiscoveryResult(
                company=company_name, outcome=DiscoveryOutcome.UNREACHABLE, slug=slug
            )
            continue

        if not page.records:
            # An empty board states nothing, and a board that states nothing
            # cannot confirm anything.
            continue
        found = client.provider.stated_company(page.records)
        if found is None:
            # Nothing further can be learned from this provider about any
            # slug, so the search ends where it is.
            return DiscoveryResult(
                company=company_name, outcome=DiscoveryOutcome.UNVERIFIABLE, slug=slug
            )
        if belongs_to(found, company_name):
            return DiscoveryResult(
                company=company_name,
                outcome=DiscoveryOutcome.CONFIRMED,
                slug=slug,
                found_company=found,
            )
        mismatch = DiscoveryResult(
            company=company_name,
            outcome=DiscoveryOutcome.WRONG_COMPANY,
            slug=slug,
            found_company=found,
        )

    # A wrong company outranks silence in the report: it is the one outcome a
    # reader has to act on, because it names a slug that must never be polled.
    return (
        mismatch
        or unreachable
        or DiscoveryResult(company=company_name, outcome=DiscoveryOutcome.NOT_FOUND)
    )
```

5. Delete the `_stated_company` function and the `RawPage` import if nothing else uses it.

Then replace `services/job-ingestion-service/job_ingestion/greenhouse/discovery.py` with:

```python
"""Greenhouse board discovery, kept as an import path.

The mechanism is provider-agnostic and lives in `boards.discovery`. Nothing
here is Greenhouse's own; the module survives so existing callers keep
working.
"""

from job_ingestion.boards.discovery import (
    LEGAL_SUFFIXES,
    DiscoveryOutcome,
    DiscoveryResult,
    belongs_to,
    candidate_slugs,
    discover,
    strip_legal_form,
)

__all__ = [
    "LEGAL_SUFFIXES",
    "DiscoveryOutcome",
    "DiscoveryResult",
    "belongs_to",
    "candidate_slugs",
    "discover",
    "strip_legal_form",
]
```

The Greenhouse discovery tests will fail until Task 6 makes `GreenhouseClient` a `BoardClient`. That is expected here; run only the boards tests.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards -q --no-cov`
Expected: all pass

- [ ] **Step 5: Type-check and commit**

Run: `cd services/job-ingestion-service && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: mypy may report `tests/greenhouse/test_discovery.py` passing `GreenhouseClient` where `BoardClient` is expected. That is resolved in Task 6; commit anyway.

```bash
git add services/job-ingestion-service/job_ingestion/boards/discovery.py services/job-ingestion-service/job_ingestion/greenhouse/discovery.py services/job-ingestion-service/tests/boards/test_discovery.py
git commit -m "Make board discovery provider-agnostic"
```

---

### Task 6: Greenhouse onto the framework

**Files:**
- Create: `services/job-ingestion-service/job_ingestion/greenhouse/source.py`
- Create: `services/job-ingestion-service/job_ingestion/greenhouse/provider.py`
- Modify: `services/job-ingestion-service/job_ingestion/greenhouse/client.py` (rewrite as shim)
- Modify: `services/job-ingestion-service/job_ingestion/greenhouse/records.py:16`, `normalizer.py:14` (import path)
- Modify: `services/job-ingestion-service/job_ingestion/greenhouse/pipeline.py:26-39` (constants come from `source.py`)
- Test: existing `tests/greenhouse/test_client.py`, `test_discovery.py`, `test_normalizer.py` unchanged

**Interfaces:**
- Consumes: `BoardClient`, `BoardConfig` (Task 3); `BoardProvider`, `Request`, `PageRead` (Task 2); `json_object`, `record_list` (Task 2)
- Produces: `GREENHOUSE: BoardProvider[GreenhouseJobRecord]`; `GreenhouseConfig` (alias of `BoardConfig`); `GreenhouseClient(config=None, *, http_client=None, sleeper=asyncio.sleep)` subclass of `BoardClient`; `greenhouse.source.SOURCE_KEY`, `DISPLAY_NAME`, `PRECEDENCE`, `DEFAULT_BASE_URL`, `DEFAULT_BOARDS`

- [ ] **Step 1: Confirm the Greenhouse tests currently fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/greenhouse/test_discovery.py -q --no-cov`
Expected: FAIL — `GreenhouseClient` has no `provider` attribute

- [ ] **Step 2: Create the constants module**

`services/job-ingestion-service/job_ingestion/greenhouse/source.py`:

```python
"""What every Greenhouse module agrees on.

Held apart so the validator, the normalizer, the provider, and the client can
all import it without importing each other.
"""

SOURCE_KEY = "greenhouse"
DISPLAY_NAME = "Greenhouse"
DEFAULT_BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

# Above the aggregator. An employer's own board is the better account of its own
# posting, which is what source precedence exists to express.
PRECEDENCE = 20

# Boards are listed rather than discovered. A guessed board name that resolves
# to a different company would ingest its postings under the wrong employer, so
# adding one is a deliberate act. Discovery finds and verifies candidates; a
# deployment decides which of them to read, through configuration.
DEFAULT_BOARDS = (
    "anthropic",
    "datadog",
    "hudl",
)
```

- [ ] **Step 3: Point records and normalizer at it**

In `job_ingestion/greenhouse/records.py`, replace `from job_ingestion.greenhouse.client import SOURCE_KEY` with `from job_ingestion.greenhouse.source import SOURCE_KEY`.

In `job_ingestion/greenhouse/normalizer.py`, replace `from job_ingestion.greenhouse.client import SOURCE_KEY` with `from job_ingestion.greenhouse.source import SOURCE_KEY`.

- [ ] **Step 4: Write the provider**

`services/job-ingestion-service/job_ingestion/greenhouse/provider.py`:

```python
"""Greenhouse as a tenant-board provider.

A board answers a single request with everything it has, so there is no
pagination. Descriptions come only when asked for, and a posting without one
cannot be normalized. Every posting states the company its board belongs to,
which is what lets discovery confirm a guessed slug.
"""

from collections.abc import Sequence

import httpx2

from job_ingestion.boards.provider import BoardProvider, PageRead, Request
from job_ingestion.boards.reading import json_object, record_list
from job_ingestion.contracts import RawRecord
from job_ingestion.greenhouse.normalizer import GreenhouseNormalizer
from job_ingestion.greenhouse.records import GreenhouseJobRecord, GreenhouseValidator
from job_ingestion.greenhouse.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)


def board_request(base_url: str, slug: str, _cursor: object | None) -> Request:
    return Request(url=f"{base_url.rstrip('/')}/{slug}/jobs", params={"content": "true"})


def read_page(slug: str, response: httpx2.Response) -> PageRead:
    body = json_object(SOURCE_KEY, slug, response)
    return PageRead(records=record_list(SOURCE_KEY, slug, body.get("jobs"), name="jobs"))


def stated_company(records: Sequence[RawRecord]) -> str | None:
    """The company a board says its postings belong to."""
    for record in records:
        stated = record.get("company_name")
        if isinstance(stated, str) and stated.strip():
            return stated
    return None


GREENHOUSE: BoardProvider[GreenhouseJobRecord] = BoardProvider(
    source_key=SOURCE_KEY,
    display_name=DISPLAY_NAME,
    precedence=PRECEDENCE,
    default_base_url=DEFAULT_BASE_URL,
    default_boards=DEFAULT_BOARDS,
    validator=GreenhouseValidator(),
    normalizer=GreenhouseNormalizer(),
    board_request=board_request,
    read_page=read_page,
    stated_company=stated_company,
)
```

- [ ] **Step 5: Rewrite the client module as a shim**

Replace the whole of `services/job-ingestion-service/job_ingestion/greenhouse/client.py` with:

```python
"""Greenhouse's client, kept as an import path over the generic one.

Everything a Greenhouse client does is what any tenant-board client does with
the Greenhouse provider. The names survive because the discovery script and
the tests use them, and because a caller that only wants Greenhouse should
not have to know about the registry.
"""

import asyncio
from collections.abc import Awaitable, Callable

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.greenhouse.provider import GREENHOUSE
from job_ingestion.greenhouse.source import DEFAULT_BASE_URL, SOURCE_KEY

GreenhouseConfig = BoardConfig


class GreenhouseClient(BoardClient):
    """A `BoardClient` that already knows it is reading Greenhouse."""

    def __init__(
        self,
        config: BoardConfig | None = None,
        *,
        http_client: httpx2.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        super().__init__(
            GREENHOUSE,
            config if config is not None else BoardConfig(),
            http_client=http_client,
            sleeper=sleeper,
        )


__all__ = [
    "DEFAULT_BASE_URL",
    "SOURCE_KEY",
    "GreenhouseClient",
    "GreenhouseConfig",
]
```

- [ ] **Step 6: Point the pipeline module at the constants**

In `services/job-ingestion-service/job_ingestion/greenhouse/pipeline.py`:

- Replace the import `from job_ingestion.greenhouse.client import (DEFAULT_BASE_URL, SOURCE_KEY, GreenhouseClient, GreenhouseConfig)` with:

```python
from job_ingestion.greenhouse.client import GreenhouseClient, GreenhouseConfig
from job_ingestion.greenhouse.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)
```

- Delete the module-level definitions of `DISPLAY_NAME`, `PRECEDENCE`, and `DEFAULT_BOARDS` together with their comments (lines 26–39 of the current file). Keep `BOARDS_SETTING = "boards"`.
- In `build_run`, change `base_url=client.config.base_url,` to `base_url=client.base_url,`.

Task 7 rewrites the rest of this module; this step only keeps it importable.

- [ ] **Step 7: Run every Greenhouse test**

Run: `cd services/job-ingestion-service && SKILLSYNC_TEST_DATABASE_URL=postgresql+psycopg://skillsync_test:skillsync_test@127.0.0.1:55432/skillsync_test .venv/bin/pytest tests/greenhouse -q --no-cov`
Expected: all pass, none skipped. If `test_greenhouse/test_client.py::test_a_setting_without_a_bound_is_refused[blank board]` fails, `BoardConfig.__post_init__` lost the blank-board check.

- [ ] **Step 8: Run the whole suite, lint, type-check**

Run: `cd services/job-ingestion-service && SKILLSYNC_TEST_DATABASE_URL=postgresql+psycopg://skillsync_test:skillsync_test@127.0.0.1:55432/skillsync_test .venv/bin/pytest -q && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: all pass; coverage ≥ 80%; lint and mypy clean.

- [ ] **Step 9: Commit**

```bash
git add services/job-ingestion-service/job_ingestion/greenhouse
git commit -m "Read Greenhouse through the generic board client"
```

---

### Task 7: Generic pipeline and registry

**Files:**
- Create: `services/job-ingestion-service/job_ingestion/boards/pipeline.py`
- Create: `services/job-ingestion-service/job_ingestion/boards/registry.py`
- Modify: `services/job-ingestion-service/job_ingestion/greenhouse/pipeline.py` (rewrite as shim)
- Test: `services/job-ingestion-service/tests/boards/test_pipeline.py`, `tests/boards/test_registry.py`; existing `tests/greenhouse/test_pipeline.py` unchanged

**Interfaces:**
- Consumes: `BoardClient`, `BoardConfig` (Task 3); `BoardProvider` (Task 2); `GREENHOUSE` (Task 6); `IngestionRun`, `DEFAULT_MAX_RECORDS` from `job_ingestion.pipeline`; `SourceRegistration` from `job_ingestion.persistence`; `recorded_run`, `complete_run` from `job_ingestion.runs`; `reconcile` from `job_ingestion.reconciliation`
- Produces:
  - `BOARDS_SETTING = "boards"`, `BASE_URL_SETTING = "base_url"`
  - `configured_boards(provider, settings) -> tuple[str, ...]`
  - `configured_base_url(provider, settings) -> str`
  - `default_config(provider, settings=None) -> BoardConfig`
  - `build_run(client, max_records, *, skill_alias_version=None) -> IngestionRun[Any]`
  - `with_board_failures(summary, client) -> IngestionSummary`
  - `ingest_board_source(provider, *, config=None, max_records=DEFAULT_MAX_RECORDS, settings=None, http_client=None) -> IngestionSummary`
  - `reconcile_after(database, summary, *, run_started_at) -> ReconciliationResult`
  - `PROVIDERS: tuple[BoardProvider[Any], ...]`, `provider_for(source_key: str) -> BoardProvider[Any]`

- [ ] **Step 1: Write the failing tests**

`services/job-ingestion-service/tests/boards/test_pipeline.py`:

```python
import asyncio
from typing import Any

import httpx2
import pytest
from platform_db.models import Job, JobSource
from pydantic import JsonValue, PostgresDsn
from sqlalchemy import select

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.pipeline import (
    build_run,
    configured_base_url,
    configured_boards,
    default_config,
    ingest_board_source,
    with_board_failures,
)
from job_ingestion.config import Environment, Settings
from job_ingestion.contracts import IngestionStage, IngestionSummary, RecordFailure
from job_ingestion.database import Database
from tests.boards.fakes import FAKE_BASE_URL, jobs, json_provider, ok, responding
from tests.support.catalog import with_empty_catalog


def configured(**block: JsonValue) -> Settings:
    return Settings(environment=Environment.TEST, source_config={"fake": block})


def test_the_default_configuration_reads_the_providers_boards() -> None:
    config = default_config(json_provider(), Settings(environment=Environment.TEST))

    assert config.boards == ("acme",)
    assert config.base_url == FAKE_BASE_URL


def test_configured_boards_replace_the_shipped_ones() -> None:
    assert configured_boards(json_provider(), configured(boards=["globex"])) == ("globex",)


def test_no_configured_boards_means_the_shipped_ones() -> None:
    assert configured_boards(json_provider(), configured(boards=[])) == ("acme",)
    assert configured_boards(json_provider(), configured()) == ("acme",)


@pytest.mark.parametrize(
    "boards",
    [
        pytest.param("acme", id="one name rather than a list"),
        pytest.param([1], id="a list of something other than names"),
    ],
)
def test_a_board_list_that_is_not_one_is_refused(boards: JsonValue) -> None:
    with pytest.raises(ValueError, match="fake.boards must be a list of board names"):
        configured_boards(json_provider(), configured(boards=boards))


def test_a_configured_base_url_replaces_the_providers() -> None:
    """A regional host is a deployment fact, not a code change."""
    assert (
        configured_base_url(json_provider(), configured(base_url="https://eu.example.test"))
        == "https://eu.example.test"
    )
    assert default_config(json_provider(), configured(base_url="https://eu.example.test")).base_url == (
        "https://eu.example.test"
    )


def test_an_absent_base_url_means_the_providers() -> None:
    assert configured_base_url(json_provider(), configured()) == FAKE_BASE_URL


@pytest.mark.parametrize("value", [pytest.param(1, id="not text"), pytest.param("  ", id="blank")])
def test_a_base_url_that_is_not_one_is_refused(value: JsonValue) -> None:
    with pytest.raises(ValueError, match="fake.base_url must be a URL"):
        configured_base_url(json_provider(), configured(base_url=value))


def test_board_failures_are_added_to_what_the_run_reports() -> None:
    summary = IngestionSummary(source_key="fake", fetched=2, created=2)
    client = BoardClient(json_provider(), http_client=responding())
    client.failures.append(RecordFailure(stage=IngestionStage.FETCH, reason="board gone"))

    combined = with_board_failures(summary, client)

    assert combined.failures[0].reason == "board gone"
    assert combined.processing_complete is False


def test_a_run_with_every_board_read_reports_nothing_extra() -> None:
    summary = IngestionSummary(source_key="fake", fetched=2, created=2)
    client = BoardClient(json_provider(), http_client=responding())

    assert with_board_failures(summary, client) is summary


def run_database_test(database_url: PostgresDsn, test: Any) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            await with_empty_catalog(database, test)
        finally:
            await database.dispose()

    asyncio.run(run())


@pytest.mark.integration
def test_a_fake_provider_ingests_under_its_own_source(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        client = BoardClient(
            json_provider(),
            BoardConfig(boards=("acme",)),
            http_client=responding(ok(jobs(1, 2))),
        )
        summary = await build_run(client, 50).execute(database)

        assert summary.fetched == 2
        assert summary.created == 2

        async with database.session() as session:
            source = (await session.scalars(select(JobSource))).one()
            stored = (await session.scalars(select(Job))).all()

        assert source.key == "fake"
        assert source.display_name == "Fake Boards"
        assert source.base_url == FAKE_BASE_URL
        assert source.precedence == 15
        assert len(stored) == 2

    run_database_test(database_url, exercise)


@pytest.mark.integration
def test_the_entry_point_runs_any_provider(database_url: PostgresDsn) -> None:
    async def exercise(database: Database) -> None:
        summary = await ingest_board_source(
            json_provider(),
            config=BoardConfig(boards=("acme",)),
            settings=Settings(environment=Environment.TEST, database_url=database_url),
            http_client=responding(httpx2.Response(200, json=jobs(1))),
        )

        assert summary.source_key == "fake"
        assert summary.created == 1

    run_database_test(database_url, exercise)
```

`services/job-ingestion-service/tests/boards/test_registry.py`:

```python
import pytest

from job_ingestion.boards.registry import PROVIDERS, provider_for


def test_every_provider_has_a_distinct_source_key() -> None:
    keys = [provider.source_key for provider in PROVIDERS]

    assert len(keys) == len(set(keys))


def test_greenhouse_is_registered() -> None:
    assert provider_for("greenhouse").display_name == "Greenhouse"


def test_an_unknown_source_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="no board provider named nope"):
        provider_for("nope")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd services/job-ingestion-service && .venv/bin/pytest tests/boards/test_pipeline.py tests/boards/test_registry.py -q --no-cov`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the generic pipeline**

`services/job-ingestion-service/job_ingestion/boards/pipeline.py`:

```python
"""Wiring and entry point for any tenant-board provider's ingestion run.

Everything reusable lives in `ingestion.pipeline`. This module names the
concrete parts for one provider, owns their lifecycles, and folds in the
boards that could not be read, which the generic run has no way to learn
about.
"""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx2

from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.persistence import SourceRegistration
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun
from job_ingestion.reconciliation import ReconciliationResult, reconcile
from job_ingestion.runs import complete_run, recorded_run

BOARDS_SETTING = "boards"
BASE_URL_SETTING = "base_url"


def build_run(
    client: BoardClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[Any]:
    """Assemble the stages around an already-built client."""
    provider = client.provider
    return IngestionRun(
        client=client,
        validator=provider.validator,
        normalizer=provider.normalizer,
        source=SourceRegistration(
            key=provider.source_key,
            display_name=provider.display_name,
            base_url=client.base_url,
            precedence=provider.precedence,
        ),
        max_records=max_records,
        skill_alias_version=skill_alias_version,
    )


def configured_boards(provider: BoardProvider[Any], settings: Settings) -> tuple[str, ...]:
    """The boards to read, from configuration when it names any.

    An absent or empty list means the shipped default rather than no boards. A
    run that reads nothing looks exactly like a run whose every board went away,
    and only one of those is a deployment mistake worth reporting as one.

    A setting that is present but not a list of names is refused. Falling back
    would turn a typo into a run that quietly ingests the shipped list while the
    operator believes it is reading the boards they configured.
    """
    key = provider.source_key
    configured = settings.source_config.get(key, {}).get(BOARDS_SETTING)
    if configured is None:
        return provider.default_boards
    if not isinstance(configured, list):
        raise ValueError(f"{key}.{BOARDS_SETTING} must be a list of board names")
    names = tuple(name for name in configured if isinstance(name, str))
    if len(names) != len(configured):
        raise ValueError(f"{key}.{BOARDS_SETTING} must be a list of board names")
    # Blank names are left for BoardConfig to refuse, so what a board name may
    # be is decided in one place.
    return names or provider.default_boards


def configured_base_url(provider: BoardProvider[Any], settings: Settings) -> str:
    """The host to read from, when a deployment names one.

    A provider with regional hosts answers a tenant on only one of them, and
    which one is a fact about the deployment rather than about the code.
    """
    key = provider.source_key
    configured = settings.source_config.get(key, {}).get(BASE_URL_SETTING)
    if configured is None:
        return provider.default_base_url
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError(f"{key}.{BASE_URL_SETTING} must be a URL")
    return configured.strip()


def default_config(provider: BoardProvider[Any], settings: Settings | None = None) -> BoardConfig:
    """The configuration a run uses when the caller supplies none."""
    resolved = settings if settings is not None else get_settings()
    return BoardConfig(
        boards=configured_boards(provider, resolved),
        base_url=configured_base_url(provider, resolved),
    )


def with_board_failures(summary: IngestionSummary, client: BoardClient) -> IngestionSummary:
    """Add the boards that could not be read to what the run reports.

    The generic run only sees the pages it was handed, so a board skipped by the
    client would otherwise vanish from the summary and the run would look
    complete while a company was missing entirely.
    """
    if not client.failures:
        return summary
    return replace(summary, failures=summary.failures + tuple(client.failures))


async def ingest_board_source(
    provider: BoardProvider[Any],
    *,
    config: BoardConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete ingestion of one provider against the configured database."""
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    resolved = config if config is not None else default_config(provider, app_settings)
    started_at = datetime.now(UTC)
    try:
        async with recorded_run(database, provider.source_key) as run_id:
            async with BoardClient(provider, resolved, http_client=http_client) as client:
                summary = with_board_failures(
                    await build_run(
                        client,
                        max_records,
                        skill_alias_version=app_settings.skill_alias_version,
                    ).execute(database),
                    client,
                )
            await reconcile_after(database, summary, run_started_at=started_at)
        await complete_run(database, run_id, summary)
        return summary
    finally:
        await database.dispose()


async def reconcile_after(
    database: Database,
    summary: IngestionSummary,
    *,
    run_started_at: datetime,
) -> ReconciliationResult:
    """Conclude what this run is entitled to conclude, if anything.

    Run against the assembled summary rather than inside the run, so a failure
    recorded after the last page still denies the conclusion.
    """
    async with database.session() as session:
        result = await reconcile(session, summary, run_started_at=run_started_at)
        await session.commit()
    return result
```

- [ ] **Step 4: Write the registry**

`services/job-ingestion-service/job_ingestion/boards/registry.py`:

```python
"""Every tenant-board provider the service can read.

Listed rather than discovered by import, so adding a provider is one visible
line and the scheduler emits exactly the DAGs this tuple names.
"""

from typing import Any

from job_ingestion.boards.provider import BoardProvider
from job_ingestion.greenhouse.provider import GREENHOUSE

PROVIDERS: tuple[BoardProvider[Any], ...] = (GREENHOUSE,)


def provider_for(source_key: str) -> BoardProvider[Any]:
    for provider in PROVIDERS:
        if provider.source_key == source_key:
            return provider
    raise ValueError(f"no board provider named {source_key}")
```

- [ ] **Step 5: Rewrite the Greenhouse pipeline module as a shim**

Replace the whole of `services/job-ingestion-service/job_ingestion/greenhouse/pipeline.py` with:

```python
"""Greenhouse's entry point, kept as an import path over the generic one.

The wiring is the same for every tenant-board provider and lives in
`boards.pipeline`. These names survive because the DAG, the tests, and a
caller that only wants Greenhouse use them.
"""

from typing import Any

import httpx2

from job_ingestion.boards import pipeline as boards
from job_ingestion.boards.client import BoardClient
from job_ingestion.boards.pipeline import BOARDS_SETTING, with_board_failures
from job_ingestion.config import Settings, get_settings
from job_ingestion.contracts import IngestionSummary
from job_ingestion.greenhouse.client import GreenhouseConfig
from job_ingestion.greenhouse.provider import GREENHOUSE
from job_ingestion.greenhouse.source import (
    DEFAULT_BASE_URL,
    DEFAULT_BOARDS,
    DISPLAY_NAME,
    PRECEDENCE,
    SOURCE_KEY,
)
from job_ingestion.pipeline import DEFAULT_MAX_RECORDS, IngestionRun


def build_run(
    client: BoardClient,
    max_records: int,
    *,
    skill_alias_version: str | None = None,
) -> IngestionRun[Any]:
    return boards.build_run(client, max_records, skill_alias_version=skill_alias_version)


def configured_boards(settings: Settings) -> tuple[str, ...]:
    return boards.configured_boards(GREENHOUSE, settings)


def default_config(settings: Settings | None = None) -> GreenhouseConfig:
    resolved = settings if settings is not None else get_settings()
    return boards.default_config(GREENHOUSE, resolved)


async def ingest_greenhouse(
    *,
    config: GreenhouseConfig | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
) -> IngestionSummary:
    """Run one complete Greenhouse ingestion against the configured database."""
    return await boards.ingest_board_source(
        GREENHOUSE,
        config=config,
        max_records=max_records,
        settings=settings,
        http_client=http_client,
    )


__all__ = [
    "BOARDS_SETTING",
    "DEFAULT_BASE_URL",
    "DEFAULT_BOARDS",
    "DISPLAY_NAME",
    "PRECEDENCE",
    "SOURCE_KEY",
    "build_run",
    "configured_boards",
    "default_config",
    "ingest_greenhouse",
    "with_board_failures",
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd services/job-ingestion-service && SKILLSYNC_TEST_DATABASE_URL=postgresql+psycopg://skillsync_test:skillsync_test@127.0.0.1:55432/skillsync_test .venv/bin/pytest tests/boards tests/greenhouse -q --no-cov`
Expected: all pass. `tests/greenhouse/test_pipeline.py::test_the_default_configuration_names_the_boards_it_reads` checks `config.base_url.startswith("https://")`; `default_config` always sets `base_url`, so it passes.

- [ ] **Step 7: Full suite, lint, type-check, commit**

Run: `cd services/job-ingestion-service && SKILLSYNC_TEST_DATABASE_URL=postgresql+psycopg://skillsync_test:skillsync_test@127.0.0.1:55432/skillsync_test .venv/bin/pytest -q && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: all pass; clean.

```bash
git add services/job-ingestion-service/job_ingestion/boards services/job-ingestion-service/job_ingestion/greenhouse/pipeline.py services/job-ingestion-service/tests/boards
git commit -m "Run any board provider through one entry point"
```

---

### Task 8: Discovery script takes a source

**Files:**
- Modify: `services/job-ingestion-service/scripts/discover_boards.py:22`, `:88-92`, `:117-121`

**Interfaces:**
- Consumes: `provider_for` (Task 7); `BoardClient`, `BoardConfig` (Task 3); `discover`, `DiscoveryOutcome` (Task 5)

- [ ] **Step 1: Change the imports**

Replace

```python
from job_ingestion.greenhouse.client import GreenhouseClient, GreenhouseConfig
from job_ingestion.greenhouse.discovery import DiscoveryOutcome, discover
```

with

```python
from job_ingestion.boards.client import BoardClient, BoardConfig
from job_ingestion.boards.discovery import DiscoveryOutcome, discover
from job_ingestion.boards.registry import provider_for
```

- [ ] **Step 2: Take the provider in `report`**

Replace

```python
async def report(names: list[str]) -> dict[str, object]:
    async with GreenhouseClient(GreenhouseConfig(boards=())) as client:
        results = [await discover(client, name) for name in names]
```

with

```python
async def report(names: list[str], source_key: str) -> dict[str, object]:
    provider = provider_for(source_key)
    async with BoardClient(provider, BoardConfig(boards=())) as client:
        results = [await discover(client, name) for name in names]
```

and add `"source": source_key,` as the first key of the returned dictionary.

- [ ] **Step 3: Add the argument**

In `main`, after `parser.add_argument("--limit", ...)` add:

```python
    parser.add_argument("--source", default="greenhouse", help="registered board provider key")
```

and change `json.dump(asyncio.run(report(names)), ...)` to `json.dump(asyncio.run(report(names, arguments.source)), ...)`.

- [ ] **Step 4: Update the module docstring's first line**

Replace `Report which stored companies have a findable Greenhouse board.` with `Report which stored companies have a findable board on one provider.`

- [ ] **Step 5: Check it parses and lint**

Run: `cd services/job-ingestion-service && .venv/bin/python scripts/discover_boards.py --help && .venv/bin/ruff format . && .venv/bin/ruff check . && .venv/bin/mypy`
Expected: help text shows `--source`; lint and mypy clean.

- [ ] **Step 6: Commit**

```bash
git add services/job-ingestion-service/scripts/discover_boards.py
git commit -m "Let board discovery name its provider"
```

---

### Task 9: Airflow DAG factory

**Files:**
- Create: `airflow/dags/board_ingestion.py`
- Delete: `airflow/dags/greenhouse_ingestion.py`
- Delete: `airflow/tests/test_greenhouse_dag_structure.py`
- Create: `airflow/tests/test_board_dag_structure.py`
- Modify: `airflow/tests/test_dag_structure.py:19-32` (`ALLOWED_CALLS`)

**Interfaces:**
- Consumes: `PROVIDERS` (Task 7), `ingest_board_source` (Task 7), `BoardProvider` (Task 2)

- [ ] **Step 1: Write the failing tests**

`airflow/tests/test_board_dag_structure.py`:

```python
"""Structure tests for the DAGs emitted per tenant-board provider."""

from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG
from job_ingestion.boards.registry import PROVIDERS

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_IDS = [f"{provider.source_key}_ingestion" for provider in PROVIDERS]


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_every_registered_provider_has_a_dag(dagbag: DagBag, dag_id: str) -> None:
    assert dag_id in dagbag.dags


def test_greenhouse_keeps_its_schedule(dagbag: DagBag) -> None:
    """Migrated, not rescheduled."""
    dag: DAG = dagbag.dags["greenhouse_ingestion"]

    assert dag.schedule == "30 * * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_failure_behavior_is_explicit(dagbag: DagBag, dag_id: str) -> None:
    task = dagbag.dags[dag_id].get_task("ingest")

    assert task.retries == 2
    assert task.retry_delay == timedelta(minutes=5)
    assert task.execution_timeout == timedelta(minutes=15)


@pytest.mark.parametrize("dag_id", DAG_IDS)
def test_each_dag_stays_a_single_thin_task(dagbag: DagBag, dag_id: str) -> None:
    assert [task.task_id for task in dagbag.dags[dag_id].tasks] == ["ingest"]


def test_no_two_providers_start_on_the_same_minute(dagbag: DagBag) -> None:
    schedules = [dagbag.dags[dag_id].schedule for dag_id in DAG_IDS]

    assert len(schedules) == len(set(schedules))


def test_the_factory_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / "board_ingestion.py").read_text()

    assert "from job_ingestion.boards.pipeline import ingest_board_source" in source
    assert "from job_ingestion.boards.registry import PROVIDERS" in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd airflow && .venv/bin/pytest tests/test_board_dag_structure.py -q`
Expected: FAIL — `board_ingestion.py` not found, `greenhouse_ingestion` still from the old file

- [ ] **Step 3: Write the factory and delete the old DAG**

`airflow/dags/board_ingestion.py`:

```python
"""Scheduled ingestion for every tenant-board provider.

This file is orchestration only. Fetching, validation, normalization,
deduplication, reconciliation, and persistence live in `job_ingestion` and are
called through one entry point, so the pipeline stays testable without Airflow
and Airflow stays free of business logic.

One DAG per registered provider, each on its own minute of the hour so the
runs do not all start together. Greenhouse keeps the minute it had before the
factory existed.
"""

import asyncio
from datetime import datetime, timedelta

from airflow.sdk import DAG, dag, task
from job_ingestion.boards.pipeline import ingest_board_source
from job_ingestion.boards.provider import BoardProvider
from job_ingestion.boards.registry import PROVIDERS

START_DATE = datetime(2026, 1, 1)
MAX_RECORDS = 500
FIRST_MINUTE = 30
MINUTE_STEP = 5


def schedule_for(index: int) -> str:
    return f"{(FIRST_MINUTE + index * MINUTE_STEP) % 60} * * * *"


def board_ingestion(provider: BoardProvider, index: int) -> DAG:
    @dag(
        dag_id=f"{provider.source_key}_ingestion",
        description=f"Fetch {provider.display_name} postings into the canonical job catalog",
        schedule=schedule_for(index),
        start_date=START_DATE,
        catchup=False,
        max_active_runs=1,
        default_args={
            "retries": 2,
            "retry_delay": timedelta(minutes=5),
            "execution_timeout": timedelta(minutes=15),
        },
        tags=["ingestion", "jobs"],
    )
    def ingestion() -> None:
        @task
        def ingest() -> dict[str, int | str]:
            """Run one bounded ingestion and publish its summary.

            A run that reports failures still succeeds as a task: the records
            it did store are already committed, and the next scheduled run
            retries the rest. Provider outages are expected, not exceptional.
            """
            summary = asyncio.run(ingest_board_source(provider, max_records=MAX_RECORDS))
            return {
                "source_key": summary.source_key,
                "fetched": summary.fetched,
                "created": summary.created,
                "updated": summary.updated,
                "skipped": summary.skipped,
                "failed": summary.failed,
            }

        ingest()

    return ingestion()


for index, provider in enumerate(PROVIDERS):
    # Assigned into the module so the DAG processor finds each one by name.
    globals()[f"{provider.source_key}_ingestion"] = board_ingestion(provider, index)
```

Then:

```bash
git rm airflow/dags/greenhouse_ingestion.py airflow/tests/test_greenhouse_dag_structure.py
```

- [ ] **Step 4: Update the allowed-call list**

In `airflow/tests/test_dag_structure.py`, replace the `ALLOWED_CALLS` set with:

```python
ALLOWED_CALLS = frozenset(
    {
        "dag",
        "task",
        "ingest",
        "ingestion",
        "arbeitnow_ingestion",
        "board_ingestion",
        "schedule_for",
        "globals",
        "enumerate",
        "asyncio.run",
        "ingest_arbeitnow",
        "ingest_board_source",
        "datetime",
        "timedelta",
    }
)
```

- [ ] **Step 5: Run the airflow tests**

Run: `cd airflow && .venv/bin/pytest -q`
Expected: all pass, including `test_every_dag_imports_cleanly`. If `greenhouse_ingestion` is missing from the DagBag, the `@dag`-decorated call did not register: confirm `board_ingestion` returns the value of `ingestion()` and that the `globals()` assignment runs at module level.

- [ ] **Step 6: Lint and commit**

Run: `cd airflow && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: clean.

```bash
git add airflow/dags/board_ingestion.py airflow/tests/test_board_dag_structure.py airflow/tests/test_dag_structure.py
git commit -m "Emit one ingestion DAG per board provider"
```

---

### Task 10: Documentation and final verification

**Files:**
- Modify: `docs/deployment-baseline.md:58-61`

- [ ] **Step 1: Document the base URL setting**

In `docs/deployment-baseline.md`, replace

```text
`SKILLSYNC_SOURCE_CONFIG` (per-source JSON; `{"greenhouse":{"boards":["hudl"]}}`
polls those boards instead of the shipped list, and an absent or empty list
means the shipped one rather than no boards).
```

with

```text
`SKILLSYNC_SOURCE_CONFIG` (per-source JSON; `{"greenhouse":{"boards":["hudl"]}}`
polls those boards instead of the shipped list, and an absent or empty list
means the shipped one rather than no boards; a `base_url` key in the same
block reads a provider's regional host, for example
`{"lever":{"base_url":"https://api.eu.lever.co/v0/postings"}}`, and is
absent otherwise).
```

- [ ] **Step 2: Run everything one last time**

```bash
cd services/job-ingestion-service && SKILLSYNC_TEST_DATABASE_URL=postgresql+psycopg://skillsync_test:skillsync_test@127.0.0.1:55432/skillsync_test .venv/bin/pytest -q && .venv/bin/ruff format --check . && .venv/bin/ruff check . && .venv/bin/mypy
cd ../../airflow && .venv/bin/pytest -q && .venv/bin/ruff format --check . && .venv/bin/ruff check .
```

Expected: every command exits 0. Ingestion coverage stays at or above 80%.

- [ ] **Step 3: Confirm the discovery script still reports Greenhouse**

```bash
cd services/job-ingestion-service && .venv/bin/python -c "
import asyncio, json
from scripts.discover_boards import report
print(json.dumps(asyncio.run(report(['Hudl'], 'greenhouse')), indent=2))
"
```

Expected: JSON with `"source": "greenhouse"` and one result for Hudl. Outcome depends on the live board (`confirmed` when reachable, `unreachable` offline); either is fine. This makes one live request.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment-baseline.md
git commit -m "Document the per-source base URL setting"
```

- [ ] **Step 5: Push and open the pull request**

```bash
git push -u origin refactor/319-tenant-board-framework
gh pr create --title "Share the tenant-board ingestion shape across providers" --body "$(cat <<'EOF'
Closes #319.

Greenhouse's transport, retry, board loop, slug discovery, pipeline wiring, and DAG were the only copy of the tenant-board shape. Eight more providers on the candidate list share it. This pulls that shape into `job_ingestion/boards` and migrates Greenhouse onto it with its public names intact.

- `BoardProvider` carries what differs per provider; `BoardClient`, `boards.discovery`, and `ingest_board_source` are written once.
- Pagination, JSON or XML page reading, and per-posting detail hydration are hooks on the provider, because Lever, SmartRecruiters, and Personio need them.
- Discovery gains an `unverifiable` outcome for feeds that never state the company.
- A `base_url` key under `SKILLSYNC_SOURCE_CONFIG` reads a regional host.
- One DAG per registered provider, emitted by a factory; `greenhouse_ingestion` keeps its schedule.

No new provider in this change. Design: `docs/superpowers/specs/2026-09-03-tenant-board-framework-design.md`.
EOF
)"
```

---

## Self-review

**Spec coverage.** Package layout → Tasks 1–7. Contract (`Request`, `PageRead`, `BoardProvider`, four hooks) → Task 2. Client with retry, pagination, page cap, hydration with dropped-record semantics → Tasks 3–4. Discovery moved, `UNVERIFIABLE`, `stated_company` via provider → Task 5. Greenhouse shims (`GreenhouseClient`, `GreenhouseConfig`, `ingest_greenhouse`, `greenhouse.discovery` re-export) → Tasks 6–7. `configured_boards` rules from #249 and `base_url` override → Task 7. Registry → Task 7. Discovery script `--source` → Task 8. DAG factory, staggered minute, Greenhouse keeps `30 * * * *`, old DAG deleted, tests parametrised → Task 9. Docs → Task 10. Untouched modules: no task edits `contracts.py`, `pipeline.py`, `persistence.py`, `deduplication.py`, `matching.py`, `reconciliation.py`, `runs.py`, `skills.py`, `vocabulary.py`, or anything under `arbeitnow/`.

**Placeholders.** None. Every code step carries its code.

**Type consistency.** `BoardProvider.read_page` takes `(slug, response)` in Task 2, the fakes, Greenhouse's provider, and the client. `stated_company` takes `Sequence[RawRecord]` everywhere. `BoardClient.request(slug, request)` is the name used by `fetch_board` and `hydrate`. `client.base_url` is what `build_run` reads in both Task 6 Step 6 and Task 7. `provider_for` raises `ValueError` with `no board provider named {key}` and the registry test matches that.
