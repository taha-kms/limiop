"""TF-IDF and cosine similarity over the same concepts, for evaluation only.

Nothing serves this. It exists so the decision to keep the skill-overlap
baseline is a measured one rather than an assumed one, and adopting it would be
a separate change with its own review — a settled decision already says simple
matching comes before sophisticated matching, evaluated before adoption.

The formulation
---------------

Each posting is a document whose terms are its required concepts, and the
candidate is a query of the concepts they hold. Term frequency is binary,
because a posting asking for Python twice does not ask for it twice; the
weighting all comes from inverse document frequency, which is the actual claim
being tested — that a concept few postings ask for should count for more than
one nearly all of them ask for.

Similarity is cosine between the two weighted vectors, which normalises for how
many concepts each side has. That is the difference from the baseline worth
measuring, and also the reason a broad candidate scores lower here.
"""

from collections.abc import Sequence, Set
from math import log, sqrt
from uuid import UUID


def inverse_document_frequency(documents: Sequence[Set[UUID]]) -> dict[UUID, float]:
    """How rare each concept is across the corpus.

    Smoothed so a concept in every document weighs something rather than
    nothing, and so a corpus of one document does not divide by zero.
    """
    total = len(documents)
    if not total:
        return {}
    counts: dict[UUID, int] = {}
    for document in documents:
        for concept in document:
            counts[concept] = counts.get(concept, 0) + 1
    return {concept: log((1 + total) / (1 + count)) + 1 for concept, count in counts.items()}


def cosine(candidate: Set[UUID], required: Set[UUID], weights: dict[UUID, float]) -> float:
    """Weighted cosine similarity between a candidate and one posting."""
    shared = candidate & required
    if not shared:
        return 0.0
    numerator = sum(weights.get(concept, 0.0) ** 2 for concept in shared)
    candidate_norm = sqrt(sum(weights.get(concept, 0.0) ** 2 for concept in candidate))
    required_norm = sqrt(sum(weights.get(concept, 0.0) ** 2 for concept in required))
    if not candidate_norm or not required_norm:
        return 0.0
    return numerator / (candidate_norm * required_norm)
