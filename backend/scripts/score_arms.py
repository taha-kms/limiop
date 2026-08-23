"""Score the three candidate vocabularies against the frozen gold set.

An arm finds a gold mention when a span it matched overlaps the gold span. The
rule is label-agnostic on purpose: the annotation showed that names are not
stable between two careful readers, so scoring by label would have measured
naming convention, and would have favoured whichever arm shared an annotator's
vocabulary.

All three arms are matched the same way — tokenise the posting once, walk its
n-grams, and keep the ones the arm's vocabulary contains — so no arm gets an
advantage from a matcher written to suit it.

Confidence intervals come from a cluster bootstrap over postings. Recall is a
proportion over mentions, mentions arrive in correlated groups, and pooling
them would report an interval several times narrower than eighty postings can
support.
"""

import argparse
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-/]*")
BOOTSTRAP_RESAMPLES = 10_000
SEED = 20260823
FALSE_POSITIVE_CAP = 200


@dataclass(frozen=True)
class Match:
    posting: str
    start: int
    end: int
    term: str


def positioned_tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).lower(), m.start(), m.end()) for m in WORD.finditer(text)]


def extract(text: str, vocabulary: set[str], longest: int, posting: str) -> list[Match]:
    """Every vocabulary term present, matched on word boundaries, longest first."""
    words = positioned_tokens(text)
    found: list[Match] = []
    taken: list[tuple[int, int]] = []
    for size in range(longest, 0, -1):
        for index in range(len(words) - size + 1):
            piece = words[index : index + size]
            term = " ".join(w for w, _, _ in piece)
            if term not in vocabulary:
                continue
            start, end = piece[0][1], piece[-1][2]
            if any(start < e and s < end for s, e in taken):
                continue
            taken.append((start, end))
            found.append(Match(posting, start, end, term))
    return found


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def score(gold: list[dict[str, Any]], matches: list[Match]) -> dict[str, Any]:
    """Which gold mentions this arm found, and which of its matches were gold."""
    by_posting: dict[str, list[Match]] = {}
    for m in matches:
        by_posting.setdefault(m.posting, []).append(m)

    found: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    for mention in gold:
        spans = by_posting.get(mention["posting"], [])
        hit = any(overlaps((mention["start"], mention["end"]), (m.start, m.end)) for m in spans)
        (found if hit else missed).append(mention)

    gold_spans: dict[str, list[tuple[int, int]]] = {}
    for mention in gold:
        gold_spans.setdefault(mention["posting"], []).append((mention["start"], mention["end"]))
    on_gold: list[Match] = []
    off_gold: list[Match] = []
    for m in matches:
        hit = any(overlaps((m.start, m.end), g) for g in gold_spans.get(m.posting, []))
        (on_gold if hit else off_gold).append(m)

    return {"found": found, "missed": missed, "on_gold": on_gold, "off_gold": off_gold}


def cluster_bootstrap(
    postings: list[str],
    per_posting: dict[str, tuple[int, int]],
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> tuple[float, float, float]:
    """Percentile interval for a ratio, resampling postings rather than mentions."""
    generator = random.Random(SEED)
    point_num = sum(per_posting[p][0] for p in postings)
    point_den = sum(per_posting[p][1] for p in postings)
    point = point_num / point_den if point_den else 0.0
    draws = []
    size = len(postings)
    for _ in range(resamples):
        picked = [postings[generator.randrange(size)] for _ in range(size)]
        num = sum(per_posting[p][0] for p in picked)
        den = sum(per_posting[p][1] for p in picked)
        if den:
            draws.append(num / den)
    draws.sort()
    lo = draws[int(0.025 * len(draws))]
    hi = draws[int(0.975 * len(draws)) - 1]
    return point, lo, hi


def design_effect(postings: list[str], per_posting: dict[str, tuple[int, int]]) -> float:
    """How much the clustering inflates the variance against an independent sample."""
    total_den = sum(per_posting[p][1] for p in postings)
    if not total_den:
        return 1.0
    point = sum(per_posting[p][0] for p in postings) / total_den
    naive = point * (1 - point) / total_den if 0 < point < 1 else 0.0
    _, lo, hi = cluster_bootstrap(postings, per_posting, resamples=2000)
    clustered = ((hi - lo) / 3.92) ** 2
    return clustered / naive if naive else 1.0


def load_arms(
    arms_path: Path, curated_path: Path, esco_path: Path
) -> dict[str, tuple[set[str], int]]:
    """Each arm as a set of normalised surface forms, plus its longest term."""

    def normalise(label: str) -> str:
        return " ".join(w.lower() for w in WORD.findall(label))

    arms: dict[str, tuple[set[str], int]] = {}

    free = set(json.loads(arms_path.read_text())["free_text"]["terms"])
    arms["free text"] = (free, max(len(t.split()) for t in free))

    curated = {
        normalise(alias)
        for entry in json.loads(curated_path.read_text())["entries"]
        for alias in entry["aliases"]
    }
    curated.discard("")
    arms["curated list"] = (curated, max(len(t.split()) for t in curated))

    esco: set[str] = set()
    for concept in json.loads(esco_path.read_text())["records"]:
        for label in [concept["preferred"], *concept["alternatives"]]:
            piece = normalise(label or "")
            if piece:
                esco.add(piece)
    arms["esco"] = (esco, max(len(t.split()) for t in esco))
    return arms


def cells_for(
    values: list[tuple[str, int]], totals: dict[str, int], postings: list[str]
) -> dict[str, tuple[int, int]]:
    hits = {p: 0 for p in postings}
    for posting, count in values:
        hits[posting] += count
    return {p: (hits[p], totals.get(p, 0)) for p in postings}


def report(
    name: str, gold: list[dict[str, Any]], matches: list[Match], postings: list[str]
) -> tuple[dict[str, Any], dict[str, tuple[int, int]]]:
    outcome = score(gold, matches)
    gold_totals = {p: sum(1 for g in gold if g["posting"] == p) for p in postings}
    match_totals = {p: sum(1 for m in matches if m.posting == p) for p in postings}
    recall_cells = cells_for([(m["posting"], 1) for m in outcome["found"]], gold_totals, postings)
    precision_cells = cells_for(
        [(m.posting, 1) for m in outcome["on_gold"]], match_totals, postings
    )
    recall = cluster_bootstrap(postings, recall_cells)
    precision = cluster_bootstrap(postings, precision_cells)
    short = [m for m in matches if len(m.term) <= 3]
    on_gold_spans = {(m.posting, m.start, m.end) for m in outcome["on_gold"]}
    short_on = [m for m in short if (m.posting, m.start, m.end) in on_gold_spans]
    summary = {
        "arm": name,
        "vocabulary_terms": None,
        "matches": len(matches),
        "recall": {
            "point": round(recall[0], 4),
            "low": round(recall[1], 4),
            "high": round(recall[2], 4),
            "design_effect": round(design_effect(postings, recall_cells), 2),
        },
        "strict_precision": {
            "point": round(precision[0], 4),
            "low": round(precision[1], 4),
            "high": round(precision[2], 4),
        },
        "short_token_matches": len(short),
        "short_token_precision": round(len(short_on) / len(short), 4) if short else None,
        "found": len(outcome["found"]),
        "missed": len(outcome["missed"]),
        "off_gold": len(outcome["off_gold"]),
    }
    return summary, recall_cells


def main() -> None:
    parser = argparse.ArgumentParser(description="Score the three arms against the gold set.")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--texts", type=Path, required=True)
    parser.add_argument("--arms", type=Path, required=True)
    parser.add_argument("--curated", type=Path, required=True)
    parser.add_argument("--esco", type=Path, required=True)
    args = parser.parse_args()

    gold = json.loads(args.gold.read_text())["gold"]
    texts = {r["posting"]: r["description"] for r in json.loads(args.texts.read_text())}
    postings = sorted(texts)
    arms = load_arms(args.arms, args.curated, args.esco)

    results: list[dict[str, Any]] = []
    cells: dict[str, dict[str, tuple[int, int]]] = {}
    extracted: dict[str, list[Match]] = {}
    for name, (vocabulary, longest) in arms.items():
        matches = [m for p in postings for m in extract(texts[p], vocabulary, longest, p)]
        extracted[name] = matches
        summary, recall_cells = report(name, gold, matches, postings)
        summary["vocabulary_terms"] = len(vocabulary)
        results.append(summary)
        cells[name] = recall_cells
        print(
            f"{name}: vocabulary={len(vocabulary)} matches={len(matches)} "
            f"recall={summary['recall']['point']:.3f}",
            flush=True,
        )

    generator = random.Random(SEED)
    pairs: dict[str, dict[str, float]] = {}
    for a in arms:
        for b in arms:
            if a >= b:
                continue
            draws = []
            for _ in range(BOOTSTRAP_RESAMPLES):
                picked = [
                    postings[generator.randrange(len(postings))] for _ in range(len(postings))
                ]
                ra = sum(cells[a][p][0] for p in picked) / max(
                    1, sum(cells[a][p][1] for p in picked)
                )
                rb = sum(cells[b][p][0] for p in picked) / max(
                    1, sum(cells[b][p][1] for p in picked)
                )
                draws.append(ra - rb)
            draws.sort()
            point = sum(cells[a][p][0] for p in postings) / sum(
                cells[a][p][1] for p in postings
            ) - sum(cells[b][p][0] for p in postings) / sum(cells[b][p][1] for p in postings)
            pairs[f"{a} minus {b}"] = {
                "point": round(point, 4),
                "low": round(draws[int(0.025 * len(draws))], 4),
                "high": round(draws[int(0.975 * len(draws)) - 1], 4),
            }

    all_found = set()
    for name in arms:
        for m in score(gold, extracted[name])["found"]:
            all_found.add((m["posting"], m["start"], m["end"]))
    tail = [g for g in gold if (g["posting"], g["start"], g["end"]) not in all_found]

    payload = {
        "gold_mentions": len(gold),
        "postings": len(postings),
        "arms": results,
        "paired_recall_difference": pairs,
        "tail": {
            "count": len(tail),
            "share": round(len(tail) / len(gold), 4),
            "by_category": {
                c: sum(1 for g in tail if g["category"] == c)
                for c in sorted({g["category"] for g in tail})
            },
            "examples": [g["labels"][0] for g in tail[:80]],
        },
        "false_positive_cap_per_arm": FALSE_POSITIVE_CAP,
    }
    args.destination.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps({k: v for k, v in payload.items() if k != "tail"}, indent=1))


if __name__ == "__main__":
    main()
