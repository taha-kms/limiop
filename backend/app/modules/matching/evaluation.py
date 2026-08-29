"""Scoring the skill-overlap baseline against a committed evaluation corpus.

Running is not working. The baseline is the gate every later matcher has to
beat, so its number has to exist and be reproducible before anything is
compared to it.

Two kinds of metric, because the product promises two things.

**Ranking.** NDCG@5 over hand-assigned graded relevance, and precision@1 —
whether the first posting shown was one the candidate should see at all.

**Explanation.** Correctness of the explanation is exact by construction here:
the corpus states both skill sets, so matched and missing are arithmetic. What
is worth measuring is whether the explanation is usable. A result listing one
matched skill and thirty missing ones is complete and tells a candidate
nothing, so the reported figure is how many skills a shown explanation carries
and how often it names at least one thing the candidate already has.
"""

import json
from dataclasses import dataclass
from math import log2
from pathlib import Path
from typing import cast
from uuid import UUID

from app.modules.matching.overlap import SkillMatch, match_skills

RANK_CUTOFF = 5


@dataclass(frozen=True, slots=True)
class Ranked:
    """One posting as the baseline ranked it, for one candidate."""

    job: str
    match: SkillMatch
    relevance: int


def load_corpus(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def rank(
    candidate_skills: set[UUID],
    jobs: dict[str, set[UUID]],
    relevance: dict[str, int],
) -> list[Ranked]:
    """Every posting scored and ordered as the endpoint would order it.

    Ties break on the job key. Any total order will do — what matters is that it
    is fixed, because an unstable one makes a ranking metric measure the sort.
    """
    scored = [
        Ranked(
            job=key,
            match=match_skills(candidate_skills, skills),
            relevance=relevance.get(key, 0),
        )
        for key, skills in jobs.items()
    ]
    return sorted(scored, key=lambda entry: (-entry.match.score, entry.job))


def discounted_gain(grades: list[int]) -> float:
    return sum(grade / log2(position + 2) for position, grade in enumerate(grades))


def ndcg(ranked: list[Ranked], cutoff: int) -> float:
    """Normalized discounted cumulative gain, 0 when nothing is relevant."""
    grades = [entry.relevance for entry in ranked[:cutoff]]
    ideal = sorted((entry.relevance for entry in ranked), reverse=True)[:cutoff]
    best = discounted_gain(ideal)
    return discounted_gain(grades) / best if best else 0.0


def evaluate(corpus: dict[str, object]) -> dict[str, object]:
    """Every metric the baseline is judged on, from one corpus."""
    jobs = {
        cast(str, job["key"]): {UUID(value) for value in cast(list[str], job["skills"])}
        for job in cast(list[dict[str, object]], corpus["jobs"])
    }

    per_candidate: list[dict[str, object]] = []
    shown: list[SkillMatch] = []
    for entry in cast(list[dict[str, object]], corpus["candidates"]):
        skills = {UUID(value) for value in cast(list[str], entry["skills"])}
        relevance = cast(dict[str, int], entry["relevance"])
        ranked = rank(skills, jobs, relevance)
        offered = [item for item in ranked[:RANK_CUTOFF] if item.match.score > 0]
        shown.extend(item.match for item in offered)
        per_candidate.append(
            {
                "candidate": entry["key"],
                "ndcg@5": round(ndcg(ranked, RANK_CUTOFF), 4),
                "precision@1": 1 if ranked[0].relevance > 0 else 0,
                "top": [
                    {
                        "job": item.job,
                        "score": round(item.match.score, 4),
                        "relevance": item.relevance,
                        "matched": item.match.matched_count,
                        "required": item.match.required_count,
                    }
                    for item in ranked[:3]
                ],
            }
        )

    sizes = [match.required_count for match in shown]
    naming_a_match = [match for match in shown if match.matched_count > 0]
    return {
        "measurement": "skill-overlap baseline",
        "corpus_version": corpus["version"],
        "vocabulary_version": corpus["vocabulary_version"],
        "candidates": len(per_candidate),
        "jobs": len(jobs),
        "ndcg@5": round(
            sum(cast(float, row["ndcg@5"]) for row in per_candidate) / len(per_candidate), 4
        ),
        "precision@1": round(
            sum(cast(int, row["precision@1"]) for row in per_candidate) / len(per_candidate), 4
        ),
        "explanations_shown": len(shown),
        "mean_skills_per_explanation": round(sum(sizes) / len(sizes), 2) if sizes else 0.0,
        "share_naming_a_matched_skill": (
            round(len(naming_a_match) / len(shown), 4) if shown else 0.0
        ),
        "per_candidate": per_candidate,
    }
