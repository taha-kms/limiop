"""Build the three candidate vocabularies the skill-model measurement compares.

Arm A is free text: no vocabulary at all, just the corpus's own n-grams inside a
document-frequency band. Arm B is a hand-curated list. Arm C is ESCO.

The one rule that matters here is disjointness. Arm B is built only from
postings outside the annotated sample, and this refuses to read a sampled
posting rather than trusting anyone to remember. A curated list tuned against
the postings it is later scored on would measure nothing.
"""

import argparse
import asyncio
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import py3langid
from platform_db.models import Job, JobProvenance
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import Database

# Fixed in the design before anything was scored: frequent enough to be more
# than noise, rare enough to tell two postings apart.
MIN_DOCUMENT_FREQUENCY = 3
MAX_DOCUMENT_SHARE = 0.25
MAX_NGRAM = 3
CURATION_BUDGET = 1000

# Matches the sampling step, so the two agree on what language a posting is in.
CLASSIFY_CHARS = 1200

WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-/]*")

# Function words plus the job-advert boilerplate that carries no skill content.
STOPWORDS = frozenset(
    [
        "a",
        "ability",
        "able",
        "about",
        "above",
        "across",
        "after",
        "again",
        "against",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "cannot",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "excellent",
        "experience",
        "few",
        "for",
        "from",
        "further",
        "good",
        "great",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "job",
        "jobs",
        "may",
        "me",
        "might",
        "more",
        "most",
        "must",
        "my",
        "myself",
        "new",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "role",
        "roles",
        "same",
        "shall",
        "she",
        "should",
        "so",
        "some",
        "strong",
        "such",
        "team",
        "teams",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "us",
        "use",
        "used",
        "using",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "within",
        "work",
        "working",
        "works",
        "would",
        "year",
        "years",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    ]
)


def tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD.finditer(text)]


def ngrams(words: list[str]) -> set[str]:
    """Every 1-to-3-gram that neither starts nor ends on a stopword."""
    found = set()
    for size in range(1, MAX_NGRAM + 1):
        for index in range(len(words) - size + 1):
            piece = words[index : index + size]
            if piece[0] in STOPWORDS or piece[-1] in STOPWORDS:
                continue
            found.add(" ".join(piece))
    return found


async def english_postings(database: Database) -> dict[str, str]:
    """Every English posting in the snapshot, keyed by provenance.

    The language is detected here rather than read from the committed sample,
    which only records the eighty postings that were drawn. `py3langid` is
    deterministic, so re-detecting reproduces the split exactly.
    """
    async with database.session() as session:
        jobs = (
            (
                await session.execute(
                    select(Job).options(
                        selectinload(Job.provenance_records).selectinload(JobProvenance.source)
                    )
                )
            )
            .scalars()
            .all()
        )
    postings = {}
    for job in jobs:
        records = sorted(job.provenance_records, key=lambda r: (r.source.key, r.source_job_id))
        key = f"{records[0].source.key}:{records[0].source_job_id}"
        code, _ = py3langid.classify(f"{job.title}\n{job.description}"[:CLASSIFY_CHARS])
        if code == "en":
            postings[key] = job.description
    return postings


def document_frequency(postings: dict[str, str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in postings.values():
        counts.update(ngrams(tokens(text)))
    return counts


def free_text_vocabulary(counts: Counter[str], corpus_size: int) -> list[str]:
    ceiling = corpus_size * MAX_DOCUMENT_SHARE
    return sorted(
        term for term, count in counts.items() if MIN_DOCUMENT_FREQUENCY <= count <= ceiling
    )


async def run(destination: Path, sample_path: Path) -> None:
    sample = {row["posting"] for row in json.loads(sample_path.read_text())["sample"]}

    database = Database(get_settings().database_url)
    try:
        scored = await english_postings(database)
    finally:
        await database.dispose()

    disjoint = {key: text for key, text in scored.items() if key not in sample}
    assert not (set(disjoint) & sample), "the curated list must not see a sampled posting"

    counts_all = document_frequency(scored)
    counts_disjoint = document_frequency(disjoint)

    payload: dict[str, Any] = {
        "corpus_postings": len(scored),
        "disjoint_postings": len(disjoint),
        "sampled_postings": len(sample),
        "free_text": {
            "min_document_frequency": MIN_DOCUMENT_FREQUENCY,
            "max_document_share": MAX_DOCUMENT_SHARE,
            "terms": free_text_vocabulary(counts_all, len(scored)),
        },
        "curation_candidates": [
            {"term": term, "documents": count}
            for term, count in counts_disjoint.most_common(CURATION_BUDGET)
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=1) + "\n")
    print(
        f"english postings={len(scored)} disjoint={len(disjoint)} "
        f"free-text terms={len(payload['free_text']['terms'])}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the free-text arm and curation candidates.")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sample", type=Path, required=True)
    arguments = parser.parse_args()
    asyncio.run(run(arguments.destination, arguments.sample))


if __name__ == "__main__":
    main()
