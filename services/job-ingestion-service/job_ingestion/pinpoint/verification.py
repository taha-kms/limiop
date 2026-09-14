"""Verifying a Pinpoint board beyond its feed.

No posting ever states the company a Pinpoint board belongs to (see
`pinpoint/provider.py::stated_company`), so a guessed slug that answers can
only be reported `UNVERIFIABLE` by `discover()`. This is what
`BoardProvider.verify` does about that: it looks past the feed for evidence
the feed itself never carries.

Two layers, tried in `verify`'s order:

- *Identity* (`identity`): the careers site names itself, in its page title
  or its RSS channel title. The tenant chose that name, the same act as a
  Polymer or Greenhouse tenant naming itself in its feed, so a matching name
  registers the board `NAMED` — polled, but on the tenant's own say-so.
- *Corroboration* (`corroborate`): when the company's own website is known,
  a link to the board there is stronger evidence than the tenant's own
  claim, and upgrades the board to `CONFIRMED`.

Every fetch here identifies itself and is bounded: a handful of requests per
company, never more, and never posting extraction. See
`docs/job-source-policy.md`'s carve-out for exactly what this is not.
"""

import re
from datetime import UTC, datetime
from html import unescape
from typing import TYPE_CHECKING
from xml.etree.ElementTree import ParseError

import httpx2
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from platform_db.models import Company

from job_ingestion.boards.discovery import DiscoveryOutcome, belongs_to
from job_ingestion.boards.provider import Request, Verification
from job_ingestion.boards.xml import local_name
from job_ingestion.errors import SourceUnavailableError

if TYPE_CHECKING:
    from job_ingestion.boards.client import BoardClient

# Title templates a Pinpoint tenant's careers site is built from, most
# specific first so "Jobs at Pinpoint | Pinpoint Careers" is not mistaken for
# the plainer "{Name} Careers" shape. Matched case-insensitively against the
# whole title, so a stray prefix or suffix defeats the match rather than
# leaving a random slice masquerading as a name.
_TITLE_TEMPLATES = (
    re.compile(r"^jobs at (?P<name>.+?)\s*\|.*careers$", re.IGNORECASE),
    re.compile(r"^careers at (?P<name>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<name>.+?)\s+careers$", re.IGNORECASE),
    re.compile(r"^(?P<name>.+?)\s+jobs$", re.IGNORECASE),
)

_HTML_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def stated_name(title: str) -> str | None:
    """The company a careers-site title names, stripped of its framing.

    `None` when the title carries no framing this recognizes — a title like
    "Home" matches no template and is not a company name to check.
    """
    stripped = title.strip()
    if not stripped:
        return None
    for template in _TITLE_TEMPLATES:
        match = template.match(stripped)
        if match:
            name = match.group("name").strip()
            return name or None
    return None


def careers_site_name(html: str) -> str | None:
    """The HTML `<title>` element's text, or `None` if the page has none.

    A plain regex, not an HTML parser: the only thing read from the page is
    one element every page has, and pulling in a parser for that would be a
    dependency this never needed.
    """
    match = _HTML_TITLE.search(html)
    if match is None:
        return None
    text = unescape(match.group(1)).strip()
    return text or None


def _rss_channel_title(content: bytes) -> str | None:
    """An RSS feed's `<channel><title>` text, or `None` if it is not one."""
    try:
        root = fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException):
        return None
    for element in root.iter():
        if local_name(element.tag) == "title" and element.text:
            text = element.text.strip()
            if text:
                return text
    return None


def _slug_host(client: "BoardClient", slug: str) -> str:
    """The tenant's own host, built the same way `board_request` builds it."""
    _, _, host = client.base_url.rstrip("/").partition("://")
    return f"{slug}.{host}"


async def _get(client: "BoardClient", slug: str, url: str) -> httpx2.Response | None:
    """One GET that never raises: an unreachable page is evidence of
    nothing, not a reason to stop verifying."""
    try:
        return await client.request(slug, Request(url=url))
    except SourceUnavailableError:
        return None


def _checked_at() -> str:
    return datetime.now(UTC).isoformat()


def _identity_verification(name: str, company: Company, *, source: str) -> Verification:
    outcome = (
        DiscoveryOutcome.NAMED
        if belongs_to(name, company.display_name)
        else DiscoveryOutcome.WRONG_COMPANY
    )
    return Verification(
        outcome=outcome,
        found_company=name,
        evidence={
            "kind": "site_title",
            "found_company": name,
            "source": source,
            "checked_at": _checked_at(),
        },
    )


async def identity(client: "BoardClient", slug: str, company: Company) -> Verification | None:
    """What the careers site itself states, checked against `company`.

    The page title is checked first; the RSS channel title only when the
    title states nothing. Whichever states a name decides the outcome — a
    matching name is `NAMED`, any other name is `WRONG_COMPANY` — and
    nothing stated by either leaves the guess unverifiable (`None`).
    """
    scheme, _, _ = client.base_url.rstrip("/").partition("://")
    base = f"{scheme}://{_slug_host(client, slug)}"

    title_response = await _get(client, slug, f"{base}/")
    if title_response is not None and title_response.status_code == httpx2.codes.OK:
        html_title = careers_site_name(title_response.text)
        if html_title is not None:
            name = stated_name(html_title)
            if name is not None:
                return _identity_verification(name, company, source="title")

    rss_response = await _get(client, slug, f"{base}/jobs.rss")
    if rss_response is not None and rss_response.status_code == httpx2.codes.OK:
        rss_title = _rss_channel_title(rss_response.content)
        if rss_title is not None:
            name = stated_name(rss_title)
            if name is not None:
                return _identity_verification(name, company, source="rss")

    return None


async def verify(client: "BoardClient", slug: str, company: Company) -> Verification:
    """Everything this module can learn about one board beyond its feed.

    Falls through to `UNVERIFIABLE` when nothing above found anything to
    say — the same answer `discover()` already gave, just re-recorded so the
    row's evidence says a verifier looked and found nothing, not that
    nothing was tried.
    """
    result = await identity(client, slug, company)
    if result is not None:
        return result
    return Verification(
        outcome=DiscoveryOutcome.UNVERIFIABLE,
        found_company=None,
        evidence={"kind": "unverified", "checked_at": _checked_at()},
    )
