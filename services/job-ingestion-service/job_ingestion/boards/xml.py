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
        raise SourceResponseError(source_key, f"board {slug} is not valid XML: {error}") from error


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
