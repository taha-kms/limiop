"""Fetch the ESCO skills pillar, for the taxonomy arm of the skill-model measurement.

ESCO is published by the European Commission and may be reused freely under
Commission Decision 2011/833/EU, with attribution under CC BY 4.0. The bulk
download is behind a form that asks for an email address, which is not ours to
give to a third party, so this walks the public keyless API instead.

The walk is breadth-first over `narrowerConcept`, which is the only way to
enumerate the pillar: a parent lists its children's preferred labels, and a
concept's own record is the only place its alternative labels appear. Both are
needed, because alternative labels are most of what a taxonomy offers a
matcher — `Py3K` is not going to appear in a job posting under its preferred
name.

Rate limiting is treated as a wait rather than a failure. That is the same
mistake #129 records in the Arbeitnow client, and it would be a poor showing to
repeat it against someone else's API while holding the issue open.

The walk checkpoints to disk and resumes from it. A first attempt lost ninety
minutes to a killed process holding everything in memory, which is a bad trade
against a few seconds of writing a file every few hundred concepts.
"""

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2

BASE = "https://ec.europa.eu/esco/api/resource/concept"
SCHEME = "http://data.europa.eu/esco/concept-scheme/skills"
TAXONOMY = "https://ec.europa.eu/esco/api/resource/taxonomy"

# Enough to finish, not enough to be rude. A first attempt at 6 spent ninety
# minutes CPU-bound on TLS handshakes rather than waiting on the network, so
# the connection pool is now sized to match and the walk reports progress
# instead of going silent for an hour.
CONCURRENCY = 16
CHECKPOINT_EVERY = 400
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 2.0
TIMEOUT_SECONDS = 30.0


@dataclass
class Walk:
    """State of one breadth-first pass over the pillar."""

    seen: set[str] = field(default_factory=set)
    concepts: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    frontier: list[str] = field(default_factory=list)


async def get(
    client: httpx2.AsyncClient, url: str, params: dict[str, str]
) -> dict[str, Any] | None:
    """One request, waiting out rate limits rather than giving up on them."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except httpx2.TransportError:
            if attempt == MAX_ATTEMPTS:
                return None
            await asyncio.sleep(BACKOFF_SECONDS * attempt)
            continue
        if response.status_code == httpx2.codes.OK:
            decoded: dict[str, Any] = response.json()
            return decoded
        if response.status_code in {429, 500, 502, 503, 504}:
            retry_after = response.headers.get("Retry-After")
            stated = retry_after if retry_after and retry_after.isdigit() else None
            delay = float(stated) if stated is not None else BACKOFF_SECONDS * attempt
            await asyncio.sleep(delay)
            continue
        return None
    return None


def children_of(payload: dict[str, Any]) -> list[str]:
    links = payload.get("_links", {})
    narrower = links.get("narrowerConcept") or links.get("narrowerSkill") or []
    return [child["uri"] for child in narrower if "uri" in child]


def record(payload: dict[str, Any]) -> dict[str, Any]:
    preferred = payload.get("preferredLabel", {}).get("en")
    alternatives = payload.get("alternativeLabel", {}).get("en") or []
    return {
        "uri": payload.get("uri", ""),
        "preferred": preferred,
        "alternatives": [label for label in alternatives if isinstance(label, str)],
        "code": payload.get("code"),
    }


def load_checkpoint(path: Path) -> Walk:
    """Whatever a previous run got through, or an empty walk."""
    if not path.exists():
        return Walk()
    saved = json.loads(path.read_text())
    return Walk(
        seen=set(saved["seen"]),
        concepts=saved["concepts"],
        failures=saved["failures"],
        frontier=saved["frontier"],
    )


def save_checkpoint(path: Path, state: Walk, frontier: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "seen": sorted(state.seen),
                "concepts": state.concepts,
                "failures": state.failures,
                "frontier": frontier,
            }
        )
    )


async def walk(client: httpx2.AsyncClient, roots: list[str], checkpoint: Path) -> Walk:
    state = load_checkpoint(checkpoint)
    frontier = state.frontier or list(roots)
    if state.concepts:
        print(f"resuming: {len(state.concepts)} concepts already fetched", flush=True)
    limiter = asyncio.Semaphore(CONCURRENCY)

    async def visit(uri: str) -> list[str]:
        async with limiter:
            payload = await get(client, BASE, {"uri": uri, "language": "en"})
        if payload is None:
            state.failures.append(uri)
            return []
        state.concepts[uri] = record(payload)
        return children_of(payload)

    while frontier:
        pending = [uri for uri in frontier if uri not in state.seen]
        discovered: list[str] = []
        # In slices, so a kill costs one slice rather than the whole level. The
        # widest level of the pillar is thirteen thousand concepts across.
        for start in range(0, len(pending), CHECKPOINT_EVERY):
            slice_ = pending[start : start + CHECKPOINT_EVERY]
            state.seen.update(slice_)
            results = await asyncio.gather(*(visit(uri) for uri in slice_))
            discovered.extend(child for group in results for child in group)
            remaining = pending[start + CHECKPOINT_EVERY :]
            save_checkpoint(checkpoint, state, remaining + discovered)
            print(f"  {len(state.concepts)} concepts, {len(remaining)} left in level", flush=True)
        frontier = [uri for uri in discovered if uri not in state.seen]
    return state


async def run(destination: Path) -> None:
    limits = httpx2.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    async with httpx2.AsyncClient(limits=limits) as client:
        top = await get(client, TAXONOMY, {"uri": SCHEME, "language": "en"})
        if top is None:
            raise SystemExit("could not read the ESCO skills concept scheme")
        roots = [c["uri"] for c in top["_links"].get("hasTopConcept", [])]
        print(f"top concepts: {len(roots)}")
        state = await walk(client, roots, destination.with_suffix(".checkpoint.json"))

    usable = [c for c in state.concepts.values() if c["preferred"]]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "source": "ESCO, European Commission, reused under CC BY 4.0",
                "scheme": SCHEME,
                "concepts": len(usable),
                "with_alternatives": sum(1 for c in usable if c["alternatives"]),
                "labels": sum(1 + len(c["alternatives"]) for c in usable),
                "failures": state.failures,
                "records": sorted(usable, key=lambda c: c["uri"]),
            },
            indent=1,
        )
        + "\n"
    )
    print(f"concepts={len(usable)} failures={len(state.failures)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch the ESCO skills pillar.")
    parser.add_argument("destination", type=Path)
    asyncio.run(run(parser.parse_args().destination))


if __name__ == "__main__":
    main()
