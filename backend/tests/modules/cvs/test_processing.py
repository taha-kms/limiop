"""Turning a stored CV into skills on its owner's profile."""

import asyncio
from collections.abc import Callable, Iterator
from uuid import UUID, uuid4

import pytest
from platform_db.models import SkillConcept
from pydantic import PostgresDsn
from sqlalchemy import create_engine, delete, insert, select

from app.db.session import Database
from app.modules.accounts.models import User
from app.modules.cvs.models import CV, CVProcessingState
from app.modules.cvs.parsing import PDFParserLimits, PDFParsingFailure, PDFParsingFailureReason
from app.modules.cvs.processing import ProcessingOutcome, process_cv
from app.modules.cvs.storage import StoredCVObject
from app.modules.profiles.models import CandidateProfile, CandidateProfileSkill, SkillSource
from app.modules.skills.resolution import AliasTableDocument, KnownSkillResolver

pytestmark = pytest.mark.integration

PYTHON = UUID("ffffffff-0000-4000-8000-000000000001")
SQL = UUID("ffffffff-0000-4000-8000-000000000002")
CONCEPTS = {PYTHON: "Python", SQL: "SQL"}
LIMITS = PDFParserLimits(
    max_file_bytes=1_000_000, max_pages=10, max_text_characters=10_000, timeout_seconds=5.0
)


def vocabulary() -> KnownSkillResolver:
    """A vocabulary of this test's own.

    The published one deliberately holds neither Python nor SQL — that is the
    finding #205 recorded, and a test that depended on it would break the day
    either is promoted.
    """
    return KnownSkillResolver(
        AliasTableDocument.model_validate(
            {
                "schema_version": 1,
                "vocabulary_version": "cv-processing.test.1",
                "concepts": [
                    {"id": concept, "preferred_label": label} for concept, label in CONCEPTS.items()
                ],
                "surface_forms": [
                    {"surface_form": "Python", "concept_ids": [PYTHON]},
                    {"surface_form": "SQL", "concept_ids": [SQL]},
                ],
            }
        )
    )


class FakeStorage:
    """Returns bytes, or raises. The parser is what is stubbed, not this."""

    async def write(self, owner_id: UUID, content: object, *, max_bytes: int) -> StoredCVObject:
        raise NotImplementedError

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        return b"%PDF-1.4 pretend"

    async def delete(self, key: str) -> None:
        return None


@pytest.fixture
def cv_owner(database_url: PostgresDsn) -> Iterator[tuple[UUID, UUID, UUID]]:
    """A user, their profile, and a pending CV. Cleared around the test."""
    engine = create_engine(str(database_url))
    user_id, profile_id, cv_id = uuid4(), uuid4(), uuid4()

    def clear() -> None:
        with engine.begin() as connection:
            connection.execute(
                delete(CandidateProfileSkill).where(CandidateProfileSkill.profile_id == profile_id)
            )
            connection.execute(delete(CV).where(CV.id == cv_id))
            connection.execute(delete(CandidateProfile).where(CandidateProfile.id == profile_id))
            connection.execute(delete(User).where(User.id == user_id))
            connection.execute(delete(SkillConcept).where(SkillConcept.id.in_(CONCEPTS)))

    clear()
    with engine.begin() as connection:
        connection.execute(
            insert(SkillConcept),
            [{"id": c, "preferred_label": label} for c, label in CONCEPTS.items()],
        )
        connection.execute(
            insert(User),
            [
                {
                    "id": user_id,
                    "email": f"cv-{user_id}@example.com",
                    "normalized_email": f"cv-{user_id}@example.com",
                    "password_hash": "x",
                }
            ],
        )
        connection.execute(insert(CandidateProfile), [{"id": profile_id, "user_id": user_id}])
        connection.execute(
            insert(CV),
            [
                {
                    "id": cv_id,
                    "owner_id": user_id,
                    "storage_key": f"cvs/{cv_id}.pdf",
                    "checksum_sha256": "a" * 64,
                    "media_type": "application/pdf",
                    "size_bytes": 1024,
                    "processing_state": CVProcessingState.PENDING,
                }
            ],
        )

    try:
        yield user_id, profile_id, cv_id
    finally:
        clear()
        engine.dispose()


def run(
    database_url: PostgresDsn,
    cv_id: UUID,
    text: str | None,
    *,
    while_reading: Callable[[], None] | None = None,
) -> object:
    """Process one CV, with the parser stubbed to return `text` or fail.

    `while_reading` runs where the real parser would: after the CV was read and
    before its skills are written, which is the only window a delete can land
    in unnoticed.
    """

    async def go() -> object:
        database = Database(database_url)
        try:
            from app.modules.cvs import processing

            async def extract(*_: object, **__: object) -> object:
                if while_reading is not None:
                    while_reading()
                if text is None:
                    raise PDFParsingFailure(PDFParsingFailureReason.SOURCE_UNAVAILABLE)

                class Extracted:
                    pass

                extracted = Extracted()
                extracted.text = text  # type: ignore[attr-defined]
                return extracted

            from app.modules.cvs import skills as cv_skills

            monkey = pytest.MonkeyPatch()
            monkey.setattr(processing, "extract_stored_pdf_text", extract)
            monkey.setattr(cv_skills, "load_default_resolver", vocabulary)
            try:
                return await process_cv(database, FakeStorage(), cv_id=cv_id, limits=LIMITS)
            finally:
                monkey.undo()
        finally:
            await database.dispose()

    return asyncio.run(go())


def state_of(database_url: PostgresDsn, cv_id: UUID) -> CVProcessingState:
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        found = connection.execute(select(CV.processing_state).where(CV.id == cv_id)).scalar_one()
    engine.dispose()
    return CVProcessingState(found)


def skills_of(database_url: PostgresDsn, profile_id: UUID) -> dict[UUID, str]:
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        rows = connection.execute(
            select(CandidateProfileSkill.concept_id, CandidateProfileSkill.source).where(
                CandidateProfileSkill.profile_id == profile_id
            )
        ).all()
    engine.dispose()
    return {row[0]: row[1] for row in rows}


def test_a_readable_cv_ends_processed_with_its_skills_on_the_profile(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    _, profile_id, cv_id = cv_owner

    run(database_url, cv_id, "Five years of Python and SQL.")

    assert state_of(database_url, cv_id) is CVProcessingState.PROCESSED
    assert skills_of(database_url, profile_id) == {
        PYTHON: SkillSource.CV,
        SQL: SkillSource.CV,
    }


def test_a_cv_that_cannot_be_read_fails_and_leaves_the_profile_alone(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    """Clearing skills because a PDF was malformed loses work done by hand."""
    _, profile_id, cv_id = cv_owner
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(
            insert(CandidateProfileSkill),
            [
                {
                    "profile_id": profile_id,
                    "concept_id": PYTHON,
                    "vocabulary_version": "test.1",
                    "source": SkillSource.MANUAL,
                }
            ],
        )
    engine.dispose()

    run(database_url, cv_id, None)

    assert state_of(database_url, cv_id) is CVProcessingState.FAILED
    assert skills_of(database_url, profile_id) == {PYTHON: SkillSource.MANUAL}


def test_a_cv_naming_nothing_is_still_processed(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    _, profile_id, cv_id = cv_owner

    run(database_url, cv_id, "A page about nothing in particular.")

    assert state_of(database_url, cv_id) is CVProcessingState.PROCESSED
    assert skills_of(database_url, profile_id) == {}


def test_re_processing_replaces_what_the_last_read_wrote(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    _, profile_id, cv_id = cv_owner

    run(database_url, cv_id, "Python and SQL.")
    # A processed CV is terminal, so the second read is a no-op rather than a
    # transition the state machine would refuse.
    outcome = run(database_url, cv_id, "Only Python now.")

    assert state_of(database_url, cv_id) is CVProcessingState.PROCESSED
    assert getattr(outcome, "skills_added", None) == 0
    assert set(skills_of(database_url, profile_id)) == {PYTHON, SQL}


def test_a_cv_uploaded_before_a_profile_exists_is_read_and_contributes_nothing(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    """Creating a profile here would invent one from a document."""
    _, profile_id, cv_id = cv_owner
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(delete(CandidateProfile).where(CandidateProfile.id == profile_id))
    engine.dispose()

    run(database_url, cv_id, "Five years of Python.")

    assert state_of(database_url, cv_id) is CVProcessingState.PROCESSED


def test_a_cv_that_no_longer_exists_is_not_an_error(database_url: PostgresDsn) -> None:
    outcome = run(database_url, uuid4(), "Python.")

    assert getattr(outcome, "state", None) is CVProcessingState.PROCESSED


def delete_cv_row(database_url: PostgresDsn, cv_id: UUID, profile_id: UUID) -> None:
    """What the delete endpoint does, in the same order."""
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(
            delete(CandidateProfileSkill).where(
                CandidateProfileSkill.profile_id == profile_id,
                CandidateProfileSkill.source == SkillSource.CV,
            )
        )
        connection.execute(delete(CV).where(CV.id == cv_id))
    engine.dispose()


def test_a_cv_deleted_while_it_is_being_read_leaves_no_skills_behind(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    """Deleting a CV takes the skills it inferred, including the ones in flight.

    Processing is queued on upload and runs after the response, so a delete can
    land between the read and the write. Writing then would leave a profile
    holding skills from a document that no longer exists.
    """
    _, profile_id, cv_id = cv_owner

    outcome = run(
        database_url,
        cv_id,
        "Five years of Python and SQL.",
        while_reading=lambda: delete_cv_row(database_url, cv_id, profile_id),
    )

    assert skills_of(database_url, profile_id) == {}
    assert isinstance(outcome, ProcessingOutcome)
    assert outcome.skills_added == 0


def test_a_cv_deleted_after_it_was_read_keeps_nothing_either(
    database_url: PostgresDsn, cv_owner: tuple[UUID, UUID, UUID]
) -> None:
    """The ordinary case, for contrast: the delete removes what processing wrote."""
    _, profile_id, cv_id = cv_owner
    run(database_url, cv_id, "Five years of Python and SQL.")
    assert skills_of(database_url, profile_id) != {}

    delete_cv_row(database_url, cv_id, profile_id)

    assert skills_of(database_url, profile_id) == {}
