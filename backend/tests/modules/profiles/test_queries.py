from sqlalchemy import literal, select

from app.modules.profiles.models import CandidateProfile
from app.modules.profiles.queries import matching_ready


def test_matching_readiness_uses_completeness_and_a_supplied_skill_count() -> None:
    statement = select(CandidateProfile.id).where(matching_ready(literal(2)))

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "candidate_profiles.profile_complete IS true" in compiled
    assert ">= 1" in compiled
