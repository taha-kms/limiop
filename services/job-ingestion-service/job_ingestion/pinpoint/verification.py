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
from collections.abc import Mapping
from datetime import UTC, datetime
from html import unescape
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree.ElementTree import ParseError

import httpx2
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from platform_db.models import Company

from job_ingestion.boards.discovery import DiscoveryOutcome, belongs_to
from job_ingestion.boards.provider import Request, Verification
from job_ingestion.boards.websites import USER_AGENT
from job_ingestion.boards.xml import local_name
from job_ingestion.errors import SourceUnavailableError

if TYPE_CHECKING:
    from job_ingestion.boards.client import BoardClient

# At most three pages of a company's own website, in the order checked,
# stopping at the first one that says anything. See
# `docs/job-source-policy.md`'s carve-out: this is not a career-page crawler.
_WEBSITE_PATHS = ("", "careers", "jobs")
_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_BODY_BYTES = 2 * 1024 * 1024
# A link, an iframe embed, or a script tag naming the board's host — the
# three shapes a careers-site widget actually takes on a company's own page.
_LINK_TEMPLATE = r'(?:href|src)\s*=\s*["\'][^"\']*{host}[^"\']*["\']'

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
    """An RSS feed's `<channel><title>` text, or `None` if it has none.

    Scoped to the channel's own direct children, not `root.iter()` over the
    whole document: an item's own title is also a `<title>` element, and a
    posting titled "Senior Engineer Jobs" would otherwise be read as the
    channel naming "Senior Engineer" — a wrong-company verdict this system
    then treats as permanent.
    """
    try:
        root = fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException):
        return None
    for element in root.iter():
        if local_name(element.tag) != "channel":
            continue
        for child in element:
            if local_name(child.tag) == "title":
                text = (child.text or "").strip()
                return text or None
        return None
    return None


def _slug_host(client: "BoardClient", slug: str) -> str:
    """The tenant's own host, built the same way `board_request` builds it."""
    _, _, host = client.base_url.rstrip("/").partition("://")
    return f"{slug}.{host}"


async def _get(
    client: "BoardClient", slug: str, url: str, *, headers: Mapping[str, str] | None = None
) -> httpx2.Response | None:
    """One GET that never raises: an unreachable page is evidence of
    nothing, not a reason to stop verifying."""
    try:
        return await client.request(slug, Request(url=url, headers=headers or {}))
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

    title_response = await _get(client, slug, f"{base}/", headers={"User-Agent": USER_AGENT})
    if title_response is not None and title_response.status_code == httpx2.codes.OK:
        html_title = careers_site_name(title_response.text)
        if html_title is not None:
            name = stated_name(html_title)
            if name is not None:
                return _identity_verification(name, company, source="title")

    rss_response = await _get(client, slug, f"{base}/jobs.rss", headers={"User-Agent": USER_AGENT})
    if rss_response is not None and rss_response.status_code == httpx2.codes.OK:
        rss_title = _rss_channel_title(rss_response.content)
        if rss_title is not None:
            name = stated_name(rss_title)
            if name is not None:
                return _identity_verification(name, company, source="rss")

    return None


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _robots(
    client: "BoardClient", slug: str, origin: str, cache: dict[str, RobotFileParser]
) -> RobotFileParser:
    """`origin`'s robots.txt, fetched once per `corroborate` call and cached.

    `RobotFileParser.can_fetch` refuses everything until something has been
    parsed into it — it is not, on its own, "nothing read yet means
    allowed". So this mirrors what `RobotFileParser.read()` itself does with
    a status code, entirely through `parse()`, its only public way to set
    that state: 401 or 403 disallows everything; any other failure to read
    one at all — a 404, a 5xx, or no answer — allows everything, the
    ordinary meaning of a site with no robots.txt.
    """
    if origin in cache:
        return cache[origin]
    parser = RobotFileParser()
    response = await _get(client, slug, f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT})
    if response is not None and response.status_code == httpx2.codes.OK:
        parser.parse(response.text.splitlines())
    elif response is not None and response.status_code in (
        httpx2.codes.UNAUTHORIZED,
        httpx2.codes.FORBIDDEN,
    ):
        parser.parse(["User-agent: *", "Disallow: /"])
    else:
        parser.parse(["User-agent: *", "Allow: /"])
    cache[origin] = parser
    return parser


async def _disallowed(
    client: "BoardClient", slug: str, url: str, cache: dict[str, RobotFileParser]
) -> bool:
    """Whether `robots.txt` refuses `url` to `*` or to `SkillSync` by name."""
    parser = await _robots(client, slug, _origin(url), cache)
    return not (parser.can_fetch("*", url) and parser.can_fetch("SkillSync", url))


async def _follow(client: "BoardClient", slug: str, url: str) -> tuple[httpx2.Response, str] | None:
    """GET `url`, following up to `_MAX_REDIRECTS` redirects by hand.

    Returns the final response together with the URL it actually answered
    at, or `None` when the page could not be reached, or redirected more
    times than the cap allows.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        response = await _get(client, slug, current, headers={"User-Agent": USER_AGENT})
        if response is None:
            return None
        if response.status_code not in _REDIRECT_STATUSES:
            return response, current
        location = response.headers.get("location")
        if not location:
            return response, current
        current = urljoin(current, location)
    return None


def _links_to(content: bytes, host: str) -> bool:
    text = content[:_MAX_BODY_BYTES].decode("utf-8", errors="replace").lower()
    pattern = re.compile(_LINK_TEMPLATE.format(host=re.escape(host.lower())))
    return pattern.search(text) is not None


def _website_evidence(*, kind: str, website: str) -> Verification:
    return Verification(
        outcome=DiscoveryOutcome.CONFIRMED,
        found_company=None,
        evidence={"kind": kind, "website": website, "checked_at": _checked_at()},
    )


async def corroborate(client: "BoardClient", slug: str, company: Company) -> Verification | None:
    """A link to the board on the company's own website, if one exists.

    Tried only when `company.website_url` is known — nothing here guesses at
    a website. At most three pages (the site's home, `/careers`, `/jobs`),
    stopping at the first one that says anything; a path `robots.txt`
    disallows is skipped outright, never fetched anyway to see.
    """
    if not company.website_url:
        return None

    target_host = _slug_host(client, slug).lower()
    robots_cache: dict[str, RobotFileParser] = {}
    base = company.website_url if company.website_url.endswith("/") else f"{company.website_url}/"

    for path in _WEBSITE_PATHS:
        page_url = urljoin(base, path)
        if await _disallowed(client, slug, page_url, robots_cache):
            continue
        fetched = await _follow(client, slug, page_url)
        if fetched is None:
            continue
        response, final_url = fetched
        if urlparse(final_url).hostname == target_host:
            return _website_evidence(kind="website_redirect", website=final_url)
        if response.status_code == httpx2.codes.OK and _links_to(response.content, target_host):
            return _website_evidence(kind="website_link", website=final_url)

    return None


async def verify(client: "BoardClient", slug: str, company: Company) -> Verification:
    """Everything this module can learn about one board beyond its feed.

    Corroboration is tried first, and wins, whenever the company's website
    is known — a link the company itself published is stronger evidence
    than the tenant's own claim. Identity is the fallback: tried when there
    is no website, or when the website said nothing usable. Falls through to
    `UNVERIFIABLE` when neither found anything to say — the same answer
    `discover()` already gave, just re-recorded so the row's evidence says a
    verifier looked and found nothing, not that nothing was tried.
    """
    if company.website_url:
        corroborated = await corroborate(client, slug, company)
        if corroborated is not None:
            return corroborated

    result = await identity(client, slug, company)
    if result is not None:
        return result
    return Verification(
        outcome=DiscoveryOutcome.UNVERIFIABLE,
        found_company=None,
        evidence={"kind": "unverified", "checked_at": _checked_at()},
    )
