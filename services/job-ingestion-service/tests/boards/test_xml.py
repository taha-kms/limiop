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


def test_a_default_namespace_does_not_hide_the_item_elements() -> None:
    """`records_in` matches on local name, so a feed whose elements sit in a
    default namespace is still found rather than yielding zero records."""
    body = b'<feed xmlns="http://example.test/ns"><position><id>1</id></position></feed>'

    root = parse_xml("feed", "acme", response(body))

    assert records_in(root, "position") == ({"id": "1"},)


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
