"""Pure skill mention extraction shared by SkillSync callers."""

from platform_skills.extraction import (
    EXTRACTOR_VERSION,
    Mention,
    Vocabulary,
    extract_mentions,
)

__all__ = ["EXTRACTOR_VERSION", "Mention", "Vocabulary", "extract_mentions"]
