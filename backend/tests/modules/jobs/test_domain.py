from enum import StrEnum

import pytest

from app.modules.jobs.domain import EmploymentType, JobStatus, WorkplaceType


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (
            WorkplaceType,
            {
                "REMOTE": "remote",
                "HYBRID": "hybrid",
                "ONSITE": "onsite",
                "UNSPECIFIED": "unspecified",
            },
        ),
        (
            EmploymentType,
            {
                "FULL_TIME": "full-time",
                "PART_TIME": "part-time",
                "CONTRACT": "contract",
                "INTERNSHIP": "internship",
                "TEMPORARY": "temporary",
                "UNSPECIFIED": "unspecified",
            },
        ),
        (
            JobStatus,
            {
                "ACTIVE": "active",
                "EXPIRED": "expired",
                "REMOVED": "removed",
            },
        ),
    ],
)
def test_canonical_job_vocabulary(
    enum_type: type[StrEnum],
    expected: dict[str, str],
) -> None:
    assert {member.name: member.value for member in enum_type} == expected
    assert all(str(member) == member.value for member in enum_type)


@pytest.mark.parametrize("enum_type", [WorkplaceType, EmploymentType, JobStatus])
def test_canonical_job_vocabulary_rejects_unsupported_input(
    enum_type: type[StrEnum],
) -> None:
    with pytest.raises(ValueError):
        enum_type("unsupported")


def test_unspecified_classifications_are_explicit() -> None:
    assert WorkplaceType.UNSPECIFIED.value == "unspecified"
    assert EmploymentType.UNSPECIFIED.value == "unspecified"
