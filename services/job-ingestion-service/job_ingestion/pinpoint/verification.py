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
  claim, and upgrades the board to `CONFIRMED`. The same page can also name
  a board the guess never did — a different subdomain the site links or
  redirects to — and `Verification.slug` carries that back to the registry.

`BoardProvider.locate` (`locate`) is the same website walk asked a plainer
question, tried only once every guess has failed to answer at all: not
"does this page corroborate the guess", but "does this page name a board
here in the first place". Both share `_walk_website`, so the fetch rules —
three pages, `robots.txt`, redirects, what counts as a public URL — exist
in exactly one place.

Every fetch here identifies itself and is bounded: a handful of requests per
company, never more, and never posting extraction. See
`docs/job-source-policy.md`'s carve-out for exactly what this is not.
"""

import re
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
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
from job_ingestion.boards.safe_fetch import default_resolver, is_public_http_url
from job_ingestion.boards.websites import USER_AGENT
from job_ingestion.boards.xml import local_name
from job_ingestion.errors import SourceResponseError, SourceUnavailableError

if TYPE_CHECKING:
    from job_ingestion.boards.client import BoardClient

# At most three pages of a company's own website, in the order checked,
# stopping at the first one that says anything. See
# `docs/job-source-policy.md`'s carve-out: this is not a career-page crawler.
_WEBSITE_PATHS = ("", "careers", "jobs")
_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_BODY_BYTES = 2 * 1024 * 1024
# How many distinct subdomains a single page may name before probing which of
# them serve a board. A page naming more than this is a directory of tenants,
# not a company site, and probing it would be the crawl `docs/job-source-policy.md`
# forbids rather than the handful of requests one company's page is owed.
_MAX_CANDIDATE_PROBES = 5
# A link, an iframe embed, or a script tag naming the board's host — the
# three shapes a careers-site widget actually takes on a company's own page.
_LINK_TEMPLATE = r'(?:href|src)\s*=\s*["\'][^"\']*{host}[^"\']*["\']'
# A full URL, in an `href` or `src`, naming one subdomain of the provider's
# own host — what any tenant's board looks like from the outside, whichever
# tenant it is. Distinct from `_LINK_TEMPLATE` above: that one is given a
# specific tenant's host to look for, this one is given only the provider's
# host and reports back which tenant, if any, a page names.
_PINPOINT_HOST_TEMPLATE = r'(?:href|src)\s*=\s*["\']https?://([a-z0-9-]+)\.{host}(?:[/"\'?#]|$)'
# The website-fetch bookkeeping name passed to `_get` and friends when there
# is no guessed slug to attribute the fetch to (`locate`, and the shared
# walk both it and `corroborate` use). Only ever shows up in a log line or an
# error message; no board is actually named "website".
_WEBSITE_SLUG = "website"

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


def _provider_host(client: "BoardClient") -> str:
    """The provider's own host, with no tenant subdomain — `pinpointhq.com`
    in production, whatever a fake configures in tests."""
    _, _, host = client.base_url.rstrip("/").partition("://")
    return host


def _slug_host(client: "BoardClient", slug: str) -> str:
    """The tenant's own host, built the same way `board_request` builds it."""
    return f"{slug}.{_provider_host(client)}"


def linked_subdomains(content: bytes, host: str) -> tuple[str, ...]:
    """Every distinct subdomain of `host` this page links to as a full URL,
    in `href` or `src`, in first-seen order, lower-cased.

    `www` is excluded — the provider's own bare host, not a tenant — and so
    is an empty capture. The host must match exactly: `notpinpointhq.com` is
    a different host, and `pinpointhq.com.evil.test` merely has the real
    host as a prefix of a longer one; neither is `host` itself preceded by a
    subdomain. Pure and independent of any particular slug, so it is tested
    on its own here and used by both `corroborate` and `locate`.
    """
    text = content[:_MAX_BODY_BYTES].decode("utf-8", errors="replace")
    pattern = re.compile(_PINPOINT_HOST_TEMPLATE.format(host=re.escape(host)), re.IGNORECASE)
    seen: dict[str, None] = {}
    for match in pattern.finditer(text):
        subdomain = match.group(1).lower()
        if subdomain and subdomain != "www" and subdomain not in seen:
            seen[subdomain] = None
    return tuple(seen)


async def serving_subdomains(
    client: "BoardClient",
    candidates: Sequence[str],
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> tuple[str, ...]:
    """Which of `candidates` actually serve a Pinpoint board, in first-seen
    order, deduplicated.

    A page linking several distinct subdomains is ambiguous on its own — one
    of them may be the vendor's own marketing host, not a tenant — so this
    asks each candidate for its board feed and keeps only the ones that
    answer. "Answer" means `client.fetch_board(candidate)` returns a
    `RawPage` without raising, whatever its record count: an empty board is
    still a board, and only an unusable answer (a non-200 status, or a body
    that is not the documented shape — `SourceResponseError`) or a transport
    failure (`SourceUnavailableError`) counts as not serving. Neither is
    raised past this function; a candidate that fails to answer is evidence
    of nothing, not a reason to stop checking the others.

    Each probe is `client.fetch_board(candidate)`, the exact call — and so
    the exact `client.request` code path, with its bounded retries — every
    ordinary configured board already goes through; nothing here asks more
    of the transport, or less, than a real board fetch. `client.request`
    itself performs no host-reachability check of its own (confirmed by
    reading it: it retries transport failures and rate limits and otherwise
    returns whatever the transport gives back). What keeps a probe from ever
    reaching an address a page merely claims is upstream of this function:
    `candidate` came from `linked_subdomains`, whose capture group is
    `[a-z0-9-]+` — no dot, no scheme — so the URL `client.fetch_board` builds
    can only ever be `{candidate}.{the provider's own configured host}`,
    never a host a malicious page chose outright. `resolve` is accepted
    only so this function's signature matches every other one in this module
    that a caller forwards `resolve` through uniformly; it is not used here,
    because `fetch_board` takes no resolver of its own.

    More than `_MAX_CANDIDATE_PROBES` distinct candidates probes none of them
    and returns `()` instead: a page naming that many tenant subdomains is a
    directory, not a company's own site, and asking each one for its board
    feed would be exactly the crawl `docs/job-source-policy.md` carves this
    module out from being. The cap is checked before any request is made,
    counting distinct candidates — a repeated one is not two entries against
    the budget.
    """
    distinct: dict[str, None] = {}
    for candidate in candidates:
        distinct.setdefault(candidate, None)
    if len(distinct) > _MAX_CANDIDATE_PROBES:
        return ()

    serving: list[str] = []
    for candidate in distinct:
        try:
            await client.fetch_board(candidate)
        except (SourceResponseError, SourceUnavailableError):
            continue
        serving.append(candidate)
    return tuple(serving)


_SUBDOMAIN_LABEL = re.compile(r"^[a-z0-9-]+$")


def _subdomain_of(hostname: str | None, host: str) -> str | None:
    """The single label if `hostname` is exactly `{label}.{host}`, excluding
    `www`, or `None` when it names no subdomain of `host` at all.

    `label` is held to the same `[a-z0-9-]+` charset `linked_subdomains`
    requires of a link — a redirect's final URL is not something this
    controls, and a hostname is not guaranteed to keep to that charset
    (`a_b`, a percent-escape that survived unescaped) the way a same-process
    check might assume.
    """
    if hostname is None:
        return None
    suffix = f".{host.lower()}"
    lowered = hostname.lower()
    if not lowered.endswith(suffix):
        return None
    label = lowered[: -len(suffix)]
    if label == "www" or not _SUBDOMAIN_LABEL.match(label):
        return None
    return label


async def _get(
    client: "BoardClient",
    slug: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> httpx2.Response | None:
    """One GET that never raises: an unreachable page is evidence of
    nothing, not a reason to stop verifying.

    Every URL this module ever fetches — the careers site, its RSS feed,
    robots.txt, a company's website, and every redirect hop off any of
    those — passes through here, and here refuses first, before any request
    is made, when `url` does not resolve to the public internet. A redirect
    that lands on a private address is treated the same as an unreachable
    page: refused, not followed.

    A URL that passed that check can still be one `client.request` itself
    cannot send: a redirect `Location` carrying a non-printable character
    raises `httpx2.InvalidURL`, and an IDNA edge case in the hostname raises
    `ValueError` or `UnicodeError`. Those are caught here, not in
    `client.request` itself — every other caller of that method sends a URL
    this module built, never one read out of someone else's response.
    """
    if not is_public_http_url(url, resolve=resolve):
        return None
    try:
        return await client.request(slug, Request(url=url, headers=headers or {}))
    except (SourceUnavailableError, httpx2.InvalidURL, ValueError, UnicodeError):
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


async def identity(
    client: "BoardClient",
    slug: str,
    company: Company,
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> Verification | None:
    """What the careers site itself states, checked against `company`.

    The page title is checked first; the RSS channel title only when the
    title states nothing. Whichever states a name decides the outcome — a
    matching name is `NAMED`, any other name is `WRONG_COMPANY` — and
    nothing stated by either leaves the guess unverifiable (`None`).
    """
    scheme, _, _ = client.base_url.rstrip("/").partition("://")
    base = f"{scheme}://{_slug_host(client, slug)}"

    title_response = await _get(
        client, slug, f"{base}/", headers={"User-Agent": USER_AGENT}, resolve=resolve
    )
    if title_response is not None and title_response.status_code == httpx2.codes.OK:
        html_title = careers_site_name(title_response.text)
        if html_title is not None:
            name = stated_name(html_title)
            if name is not None:
                return _identity_verification(name, company, source="title")

    rss_response = await _get(
        client, slug, f"{base}/jobs.rss", headers={"User-Agent": USER_AGENT}, resolve=resolve
    )
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
    client: "BoardClient",
    slug: str,
    origin: str,
    cache: dict[str, RobotFileParser],
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
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
    response = await _get(
        client,
        slug,
        f"{origin}/robots.txt",
        headers={"User-Agent": USER_AGENT},
        resolve=resolve,
    )
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
    client: "BoardClient",
    slug: str,
    url: str,
    cache: dict[str, RobotFileParser],
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> bool:
    """Whether `robots.txt` refuses `url` to `*` or to `SkillSync` by name."""
    parser = await _robots(client, slug, _origin(url), cache, resolve=resolve)
    return not (parser.can_fetch("*", url) and parser.can_fetch("SkillSync", url))


async def _follow(
    client: "BoardClient",
    slug: str,
    url: str,
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> tuple[httpx2.Response, str] | None:
    """GET `url`, following up to `_MAX_REDIRECTS` redirects by hand.

    Returns the final response together with the URL it actually answered
    at, or `None` when the page could not be reached, redirected more times
    than the cap allows, or a hop landed on a URL that does not resolve to
    the public internet — `_get` refuses that the same way it refuses the
    first request, so a redirect into a private network is treated as
    unreachable rather than followed.
    """
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        response = await _get(
            client, slug, current, headers={"User-Agent": USER_AGENT}, resolve=resolve
        )
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


def _website_evidence(
    *,
    kind: str,
    website: str,
    slug: str | None = None,
    linked: str | None = None,
    probed: list[str] | None = None,
) -> Verification:
    evidence: dict[str, object] = {"kind": kind, "website": website, "checked_at": _checked_at()}
    if linked is not None:
        evidence["linked"] = linked
    if probed is not None:
        evidence["probed"] = probed
    return Verification(
        outcome=DiscoveryOutcome.CONFIRMED, found_company=None, evidence=evidence, slug=slug
    )


async def _walk_website(
    client: "BoardClient",
    company: Company,
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> AsyncIterator[tuple[httpx2.Response, str, str]]:
    """The company's own three pages, in order, that could actually be
    fetched — skipping any a `robots.txt` disallows, and any that could not
    be reached at all. Yields nothing when `company.website_url` is unknown
    or is not a public HTTP(S) address, before a single request is made.

    Each item is `(response, final_url, page_url)`: the response and where
    it actually answered, alongside the page that was requested before any
    redirect — a caller comparing the two is how "this page redirected
    somewhere" is told apart from "this page already was that URL".

    This is only the fetch rules: which pages exist to look at, and under
    what conditions. What a page says is entirely up to the caller —
    `corroborate` and `locate` each read the same walk differently.
    """
    if not company.website_url:
        return
    if not is_public_http_url(company.website_url, resolve=resolve):
        return

    robots_cache: dict[str, RobotFileParser] = {}
    base = company.website_url if company.website_url.endswith("/") else f"{company.website_url}/"

    for path in _WEBSITE_PATHS:
        page_url = urljoin(base, path)
        if await _disallowed(client, _WEBSITE_SLUG, page_url, robots_cache, resolve=resolve):
            continue
        fetched = await _follow(client, _WEBSITE_SLUG, page_url, resolve=resolve)
        if fetched is None:
            continue
        response, final_url = fetched
        yield response, final_url, page_url


async def corroborate(
    client: "BoardClient",
    slug: str,
    company: Company,
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> Verification | None:
    """A link to a board on the company's own website, if one exists.

    Tried only when `company.website_url` is known — nothing here guesses at
    a website. At most three pages (the site's home, `/careers`, `/jobs`),
    stopping at the first one that says anything; a path `robots.txt`
    disallows is skipped outright, never fetched anyway to see.

    Each page is read in order: a redirect landing on `{slug}.{host}`
    confirms the guess unchanged; landing on any *other* `{sub}.{host}` —
    whether by redirect or because `company.website_url` already was that
    URL — confirms `sub` instead, carried on `Verification.slug`, evidence
    kind `website_redirect` when at least one hop actually happened and
    `website_self` when the page answered directly; a page linking
    `{slug}.{host}` confirms the guess unchanged; a page whose only other
    Pinpoint link is to exactly one subdomain confirms that one, evidence
    noting what was `linked`. A page linking several distinct other
    subdomains is narrowed first, by `serving_subdomains`, to the ones that
    actually answer with a board feed — a vendor's own marketing subdomain
    linked alongside the tenant's does not get to make the page ambiguous —
    and evidence then records every candidate tried as `probed`; only when
    exactly one of them serves does the page confirm it. Still more than one
    serving, or none, says nothing about any of them — a site listing many
    tenants (a group of companies) must not have one of them picked for it
    — and the walk moves on to the next page rather than giving up.

    `company.website_url` came from a posting payload or Wikidata, neither
    trustworthy, so it is checked against the public internet before
    anything is fetched from it at all — not left to `_get`'s own check on
    the first page, which would still refuse the request but only after
    computing an origin and a robots-cache entry for a URL already known to
    be no good.
    """
    host = _provider_host(client)
    target_host = _slug_host(client, slug).lower()

    async for response, final_url, page_url in _walk_website(client, company, resolve=resolve):
        final_host = urlparse(final_url).hostname
        if final_host == target_host:
            return _website_evidence(kind="website_redirect", website=final_url)
        other = _subdomain_of(final_host, host)
        if other is not None:
            kind = "website_redirect" if final_url != page_url else "website_self"
            return _website_evidence(kind=kind, website=final_url, slug=other)
        if response.status_code != httpx2.codes.OK:
            continue
        if _links_to(response.content, target_host):
            return _website_evidence(kind="website_link", website=final_url)
        candidates = tuple(sub for sub in linked_subdomains(response.content, host) if sub != slug)
        linked = candidates
        if len(candidates) > 1:
            linked = await serving_subdomains(client, candidates, resolve=resolve)
        if len(linked) == 1:
            probed = list(candidates) if len(candidates) > 1 else None
            return _website_evidence(
                kind="website_link",
                website=final_url,
                slug=linked[0],
                linked=linked[0],
                probed=probed,
            )

    return None


async def locate(
    client: "BoardClient",
    company: Company,
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> Verification | None:
    """Whether the company's own website names a Pinpoint board at all, with
    no guessed slug to check against — asked only once every guess has
    failed to answer (`discover()` reported `NOT_FOUND`).

    Runs the same three-page walk as `corroborate`, but only the two rules
    that make sense without a guess: landing on `{sub}.{host}` — by
    redirect, or because `company.website_url` already was that URL — names
    `sub` (evidence kind `website_redirect` when a hop actually happened,
    `website_self` when the page answered directly), and a page whose only
    Pinpoint link is to exactly one subdomain names that one. A page linking
    several distinct subdomains is narrowed first, the same way
    `corroborate` narrows one, to the subdomains that actually answer with a
    board feed, with every candidate tried recorded as `probed`; only when
    exactly one of them serves does the page name it. Still more than one
    serving, or none, names none of them, for the same reason `corroborate`
    skips it — a website listing many tenants must not have one of them
    picked for it — and the walk moves on rather than giving up. Never
    raises for a website answer, and rejects a private
    `company.website_url` before a single request is made, the same
    guarantees `corroborate` gives.
    """
    host = _provider_host(client)

    async for response, final_url, page_url in _walk_website(client, company, resolve=resolve):
        other = _subdomain_of(urlparse(final_url).hostname, host)
        if other is not None:
            kind = "website_redirect" if final_url != page_url else "website_self"
            return _website_evidence(kind=kind, website=final_url, slug=other)
        if response.status_code != httpx2.codes.OK:
            continue
        candidates = linked_subdomains(response.content, host)
        linked = candidates
        if len(candidates) > 1:
            linked = await serving_subdomains(client, candidates, resolve=resolve)
        if len(linked) == 1:
            probed = list(candidates) if len(candidates) > 1 else None
            return _website_evidence(
                kind="website_link",
                website=final_url,
                slug=linked[0],
                linked=linked[0],
                probed=probed,
            )

    return None


async def verify(
    client: "BoardClient",
    slug: str,
    company: Company,
    *,
    resolve: Callable[[str], list[str]] = default_resolver,
) -> Verification:
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
        corroborated = await corroborate(client, slug, company, resolve=resolve)
        if corroborated is not None:
            return corroborated

    result = await identity(client, slug, company, resolve=resolve)
    if result is not None:
        return result
    return Verification(
        outcome=DiscoveryOutcome.UNVERIFIABLE,
        found_company=None,
        evidence={"kind": "unverified", "checked_at": _checked_at()},
    )
