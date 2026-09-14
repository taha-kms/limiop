"""Resolving a company's official website without a key.

Corroboration (verifying a discovered board by looking for a link to it on
the company's own site) needs a website, and the catalogue does not hold one
today: `Company.website_url` exists but no source fills it yet.

Three strategies, in order, stopping at the first hit:

1. The catalogue's own `website_url`, once any source fills it.
2. The most frequent domain mentioned in the company's own stored postings,
   excluding ATS, aggregator, social, CDN, code-hosting, and document hosts.
3. Wikidata: search the label, keep items typed as a business whose English
   label matches, and read `P856` (official website).

Ambiguity resolves to nothing, not to a guess. A company with no resolvable
website is recorded as checked so it is not retried every run; its board, if
any, is verified some other way or stays unconfirmed.
"""

import asyncio
import json
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

import httpx2
from platform_db.models import Company, Job, JobProvenance
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from job_ingestion.boards.discovery import belongs_to
from job_ingestion.config import Settings, get_settings
from job_ingestion.database import Database
from job_ingestion.pipeline import utc_now
from job_ingestion.rate_limit import is_rate_limited, retry_delay

logger = logging.getLogger(__name__)

WIKIDATA_BASE_URL = "https://www.wikidata.org"
USER_AGENT = "SkillSync/0.1 (job board discovery; https://github.com/taha-kms/limiop)"
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

# Business-shaped Wikidata classes (P31) a company can be an instance of.
# Anything else typed under the same label — a person's surname, a given
# name — is not a hit, however exactly the label matches.
BUSINESS_CLASSES = frozenset(
    {
        "Q4830453",  # business
        "Q783794",  # company
        "Q891723",  # public company
        "Q1589009",  # private company
        "Q6881511",  # enterprise
        "Q18388277",  # technology company
        "Q210167",  # startup company
    }
)

# Hosts a stored posting mentions that are never the employer's own site: ATS
# and job-board platforms, aggregators, social networks, CDNs, code hosting,
# and generic document hosts. Matched on a dot boundary, so `notgreenhouse.io`
# is kept and only `greenhouse.io` and its subdomains are dropped.
IGNORED_HOST_SUFFIXES = (
    "greenhouse.io",
    "polymer.co",
    "pinpointhq.com",
    "arbeitnow.com",
    "lever.co",
    "ashbyhq.com",
    "workable.com",
    "recruitee.com",
    "personio.de",
    "smartrecruiters.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "glassdoor.com",
    "indeed.com",
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "amazonaws.com",
    "cloudfront.net",
    "notion.site",
    "github.com",
    "wikipedia.org",
    "w3.org",
    "schema.org",
)

# A posting must mention a domain at least this many times, across all
# postings, before it is trusted as the employer's own.
MINIMUM_DOMAIN_VOTES = 2

_URL_HOST_PATTERN = re.compile(r"https?://([a-z0-9.-]+\.[a-z]{2,})", re.IGNORECASE)


class WebsiteSource(StrEnum):
    """Which strategy answered, so a later run does not repeat a stronger one."""

    SOURCE = "source"  # a job source stated it (already stored)
    POSTINGS = "postings"  # the most frequent domain in the company's own postings
    WIKIDATA = "wikidata"


@dataclass(frozen=True, slots=True)
class WebsiteResolution:
    """What one attempt at resolving a company's website found."""

    url: str | None
    source: WebsiteSource | None


@dataclass(frozen=True, slots=True)
class WebsiteSummary:
    """What one run of website resolution accomplished."""

    # How many companies were due for resolution, before the budget slice.
    seeded: int
    # How many of those were actually looked at this run (`min(seeded, budget)`).
    processed: int
    resolved_by: dict[str, int]
    unresolved: int
    stopped_at_budget: bool


def _is_ignored_host(host: str) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in IGNORED_HOST_SUFFIXES)


def hosts_in_payload(payload: object) -> frozenset[str]:
    """Distinct, non-ignored hosts mentioned anywhere in one posting's payload.

    Serialised with `json.dumps` rather than walked field by field: a link can
    turn up under any key a source happens to use, and the payload is
    untrusted JSON anyway. A host mentioned several times in one payload is
    still one vote, which is why this returns a set rather than a count.
    """
    serialized = json.dumps(payload)
    hosts: set[str] = set()
    for match in _URL_HOST_PATTERN.finditer(serialized):
        host = match.group(1).lower()
        if host.startswith("www."):
            host = host[4:]
        if not _is_ignored_host(host):
            hosts.add(host)
    return frozenset(hosts)


def count_domains(payloads: Iterable[object]) -> Counter[str]:
    """One vote per payload for each non-ignored host it mentions."""
    counts: Counter[str] = Counter()
    for payload in payloads:
        counts.update(hosts_in_payload(payload))
    return counts


def rank_domain(counts: Counter[str], *, minimum_votes: int = MINIMUM_DOMAIN_VOTES) -> str | None:
    """The single most-mentioned domain, or `None` when there is no clear winner.

    A tie at the top is ambiguous, not a coin flip: nothing here is entitled
    to prefer one company's own domain over another's.
    """
    if not counts:
        return None
    ranked = counts.most_common(2)
    top_domain, top_votes = ranked[0]
    if top_votes < minimum_votes:
        return None
    if len(ranked) > 1 and ranked[1][1] == top_votes:
        return None
    return top_domain


async def mentioned_domains(session: AsyncSession, company_id: UUID) -> Counter[str]:
    """Domains mentioned in the raw payloads of one company's stored postings."""
    statement = (
        select(JobProvenance.raw_payload)
        .join(Job, JobProvenance.job_id == Job.id)
        .where(Job.company_id == company_id, JobProvenance.raw_payload.is_not(None))
    )
    rows = (await session.execute(statement)).all()
    return count_domains(payload for (payload,) in rows if payload is not None)


async def from_postings(session: AsyncSession, company: Company) -> WebsiteResolution:
    """The company's website read from the domains its own postings mention."""
    counts = await mentioned_domains(session, company.id)
    domain = rank_domain(counts)
    if domain is None:
        return WebsiteResolution(None, None)
    return WebsiteResolution(f"https://{domain}/", WebsiteSource.POSTINGS)


async def _request_json(
    http_client: httpx2.AsyncClient,
    url: str,
    params: dict[str, Any],
    *,
    sleeper: Callable[[float], Awaitable[None]],
) -> dict[str, Any] | None:
    """One provider request, retried like `BoardClient.request` but never raising.

    Wikidata is one input among several, not something ingestion depends on
    to run: a provider answer this cannot use — a non-200 that is not a rate
    limit, or a body that is not JSON — ends the attempt with `None` rather
    than an exception. Only a rate limit or a transport failure is retried,
    at most `MAX_ATTEMPTS` times.
    """
    delay = RETRY_BACKOFF_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await http_client.get(url, params=params, headers={"User-Agent": USER_AGENT})
        except httpx2.TransportError:
            if attempt < MAX_ATTEMPTS:
                await sleeper(delay)
            continue

        if response.status_code == httpx2.codes.OK:
            try:
                body = response.json()
            except ValueError:
                return None
            return body if isinstance(body, dict) else None

        if not is_rate_limited(response):
            return None
        delay = retry_delay(response, fallback=delay)
        if attempt < MAX_ATTEMPTS:
            await sleeper(delay)

    return None


def _snak_values(claims: object, property_id: str) -> list[Any]:
    if not isinstance(claims, dict):
        return []
    statements = claims.get(property_id)
    if not isinstance(statements, list):
        return []
    values: list[Any] = []
    for statement in statements:
        if not isinstance(statement, dict):
            continue
        mainsnak = statement.get("mainsnak")
        if not isinstance(mainsnak, dict):
            continue
        datavalue = mainsnak.get("datavalue")
        if not isinstance(datavalue, dict):
            continue
        value = datavalue.get("value")
        if value is not None:
            values.append(value)
    return values


def _is_business(claims: object) -> bool:
    for value in _snak_values(claims, "P31"):
        if isinstance(value, dict) and value.get("id") in BUSINESS_CLASSES:
            return True
    return False


def _official_website(claims: object) -> str | None:
    for value in _snak_values(claims, "P856"):
        if isinstance(value, str) and value.strip():
            return value
    return None


def _english_label(entity: object) -> str | None:
    if not isinstance(entity, dict):
        return None
    labels = entity.get("labels")
    if not isinstance(labels, dict):
        return None
    english = labels.get("en")
    if not isinstance(english, dict):
        return None
    value = english.get("value")
    return value if isinstance(value, str) else None


def _qualifying_url(entity_body: dict[str, Any], entity_id: str, company_name: str) -> str | None:
    """The official website of one entity, if it is unambiguously this company.

    All three conditions gate a hit: typed as a business, an English label
    that matches after the same normalization `belongs_to` uses elsewhere,
    and an official-website claim to read.
    """
    entities = entity_body.get("entities")
    if not isinstance(entities, dict):
        return None
    entity = entities.get(entity_id)
    if not isinstance(entity, dict):
        return None

    label = _english_label(entity)
    if label is None or not belongs_to(label, company_name):
        return None

    claims = entity.get("claims")
    if not _is_business(claims):
        return None
    return _official_website(claims)


async def from_wikidata(
    http_client: httpx2.AsyncClient,
    company_name: str,
    *,
    sleeper: Callable[[float], Awaitable[None]],
) -> WebsiteResolution:
    """The company's website read from Wikidata, or nothing if it is ambiguous.

    Two same-labelled businesses are indistinguishable from here — "Pinpoint"
    names both a recruiting platform and an unrelated Romanian consultancy —
    so more than one qualifying hit resolves to nothing rather than a guess.
    That is a real limitation: a wrong website is never worse than a missed
    one, because the only use made of it (issue #335) is as evidence for a
    link to a board, never as proof on its own — a wrong website costs a
    missed confirmation, never a false one.
    """
    search_body = await _request_json(
        http_client,
        f"{WIKIDATA_BASE_URL}/w/api.php",
        {
            "action": "wbsearchentities",
            "search": company_name,
            "language": "en",
            "type": "item",
            "limit": 5,
            "format": "json",
        },
        sleeper=sleeper,
    )
    if search_body is None:
        return WebsiteResolution(None, None)

    hits = search_body.get("search")
    if not isinstance(hits, list):
        return WebsiteResolution(None, None)

    qualifying_urls: list[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        entity_id = hit.get("id")
        if not isinstance(entity_id, str) or not entity_id:
            continue
        entity_body = await _request_json(
            http_client,
            f"{WIKIDATA_BASE_URL}/wiki/Special:EntityData/{entity_id}.json",
            {},
            sleeper=sleeper,
        )
        if entity_body is None:
            continue
        url = _qualifying_url(entity_body, entity_id, company_name)
        if url is not None:
            qualifying_urls.append(url)

    if len(qualifying_urls) != 1:
        return WebsiteResolution(None, None)
    return WebsiteResolution(qualifying_urls[0], WebsiteSource.WIKIDATA)


def record(company: Company, resolution: WebsiteResolution, now: datetime) -> None:
    """Write one resolution onto its company.

    `website_url` is set only when the row does not already have one — this
    strategy list only ever adds evidence, it never overwrites what a source
    stated. `website_source` follows the url it describes, not the most
    recent attempt: a company whose url was already known and is merely
    reconfirmed (`resolve_website`'s `SOURCE` short-circuit fires on every
    recheck once a url exists, however it first got there) must keep
    describing where that url actually came from. So `website_source` is set
    only the first time a url exists — when this call is the one that finds
    it, or when the row already had a url but no recorded source yet.
    `website_checked_at` is set unconditionally, including when nothing was
    found, which is what keeps an unresolved company from being retried
    every run.
    """
    newly_found = company.website_url is None and resolution.url is not None
    if newly_found:
        company.website_url = resolution.url
    if newly_found or (company.website_source is None and resolution.source is not None):
        company.website_source = resolution.source.value if resolution.source is not None else None
    company.website_checked_at = now


async def resolve_website(
    session: AsyncSession,
    http_client: httpx2.AsyncClient,
    company: Company,
    *,
    now: datetime,
    sleeper: Callable[[float], Awaitable[None]],
) -> WebsiteResolution:
    """Resolve and record one company's website, stopping at the first hit."""
    if company.website_url:
        resolution = WebsiteResolution(company.website_url, WebsiteSource.SOURCE)
    else:
        resolution = await from_postings(session, company)
        if resolution.url is None:
            resolution = await from_wikidata(http_client, company.display_name, sleeper=sleeper)
    record(company, resolution, now)
    return resolution


async def resolve_company_websites(
    database: Database,
    *,
    budget: int = 100,
    recheck: timedelta = timedelta(days=90),
    http_client: httpx2.AsyncClient | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    politeness_seconds: float = 1.0,
    now: Callable[[], datetime] = utc_now,
) -> WebsiteSummary:
    """Resolve up to `budget` companies with no website, oldest-checked first.

    Candidates are companies with no `website_url` that were never checked or
    were last checked before `recheck` ago, ordered by job count so the
    companies with the most postings to lose are looked at first. `seeded`
    counts every company that matched, before the budget cuts the list down
    to `processed`, so a run can say how much of the queue is left without
    pretending a run that exactly emptied it stopped early.
    """
    moment = now()
    cutoff = moment - recheck
    owns_client = http_client is None
    client = http_client if http_client is not None else httpx2.AsyncClient()
    try:
        async with database.session() as session:
            due = (
                Company.website_url.is_(None),
                or_(
                    Company.website_checked_at.is_(None),
                    Company.website_checked_at < cutoff,
                ),
            )
            seeded = await session.scalar(select(func.count()).select_from(Company).where(*due))
            seeded = seeded or 0

            job_counts = (
                select(Job.company_id, func.count(Job.id).label("job_count"))
                .group_by(Job.company_id)
                .subquery()
            )
            statement = (
                select(Company)
                .outerjoin(job_counts, job_counts.c.company_id == Company.id)
                .where(*due)
                .order_by(func.coalesce(job_counts.c.job_count, 0).desc(), Company.display_name)
                .limit(budget)
            )
            candidates = list((await session.scalars(statement)).all())

            resolved_by: Counter[str] = Counter()
            unresolved = 0
            for index, company in enumerate(candidates):
                resolution = await resolve_website(
                    session, client, company, now=moment, sleeper=sleeper
                )
                if resolution.source is not None:
                    resolved_by[resolution.source.value] += 1
                else:
                    unresolved += 1

                # Every candidate here was seeded with no `website_url`, so
                # `resolve_website` can only have reached this point through
                # postings or Wikidata; only the latter touches the network,
                # so only it needs a politeness delay before the next one.
                hit_network = resolution.source is not WebsiteSource.POSTINGS
                if hit_network and index < len(candidates) - 1:
                    await sleeper(politeness_seconds)

            await session.commit()
    finally:
        if owns_client:
            await client.aclose()

    return WebsiteSummary(
        seeded=seeded,
        processed=len(candidates),
        resolved_by=dict(resolved_by),
        unresolved=unresolved,
        stopped_at_budget=seeded > len(candidates),
    )


async def resolve_websites(
    *,
    settings: Settings | None = None,
    http_client: httpx2.AsyncClient | None = None,
    budget: int = 100,
) -> WebsiteSummary:
    """Run one complete website-resolution pass against the configured database."""
    app_settings = settings if settings is not None else get_settings()
    database = Database(app_settings.database_url)
    try:
        summary = await resolve_company_websites(database, budget=budget, http_client=http_client)
        logger.info("resolved company websites: %s", summary)
        return summary
    finally:
        await database.dispose()
