"""Scoring one job against one candidate by the skills they share.

The baseline, deliberately. It is a set intersection over canonical concepts,
which means every score can be read back as the skills behind it, and a result
nobody can explain is not a result this product wants to serve.

The score is coverage of the job's skills
----------------------------------------

``len(matched) / len(required)``: the share of what the posting asks for that
the candidate already has. Bounded to ``[0, 1]``, and it answers the question a
candidate is actually asking — how much of this job can I already do.

Set similarity was the obvious alternative and is wrong here. Jaccard divides by
the union, so a candidate who knows more than the posting asks for scores lower
than one who knows exactly the posting's list, and a broader candidate is not a
worse fit for a narrower job. The asymmetry is real and the formula should
carry it: skills the job did not ask for are not held against anybody, while
skills it asked for and the candidate lacks are exactly what `missing` names.

A posting naming no skills scores zero
--------------------------------------

There is no share of nothing. Scoring it 1.0 would rank every posting whose
skills failed to extract above every posting that matched genuinely, on the
strength of having said nothing — and roughly two thirds of the stored
catalogue currently has no extracted skills at all. Zero is the honest answer:
we cannot say this posting fits, so we do not say it does.
"""

from collections.abc import Set
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SkillMatch:
    """One job scored against one candidate, with the reason attached.

    The concepts are sorted so a result is stable to compare and to page
    through, and every score arrives with both halves of its explanation.
    """

    score: float
    matched: tuple[UUID, ...]
    missing: tuple[UUID, ...]

    @property
    def matched_count(self) -> int:
        return len(self.matched)

    @property
    def required_count(self) -> int:
        return len(self.matched) + len(self.missing)


def match_skills(candidate: Set[UUID], required: Set[UUID]) -> SkillMatch:
    """Score what the candidate has against what the posting asks for."""
    matched = candidate & required
    missing = required - candidate
    return SkillMatch(
        score=len(matched) / len(required) if required else 0.0,
        matched=tuple(sorted(matched)),
        missing=tuple(sorted(missing)),
    )
