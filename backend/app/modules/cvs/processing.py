"""Turning a stored CV into skills on its owner's profile.

The upload endpoint stores a file and returns. Everything after that happens
here, out of the request, because parsing spawns a process with a timeout and
holding an HTTP request open for it makes the upload's latency a function of
whatever PDF somebody chose.

The state on the row is the record of what happened, and it is the reason this
can run outside the request without disappearing: a CV that never leaves
`pending` is visibly unprocessed rather than silently missing its skills.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Database
from app.modules.cvs.models import CV, CVProcessingState
from app.modules.cvs.parsing import (
    PDFParserLimits,
    PDFParsingFailure,
    PypdfTextExtractor,
    extract_stored_pdf_text,
)
from app.modules.cvs.skills import store_cv_skills
from app.modules.cvs.storage import CVStorage
from app.modules.profiles.service import find_profile

logger = logging.getLogger("app.cvs")


@dataclass(frozen=True, slots=True)
class ProcessingOutcome:
    """What one processing attempt did. Returned for tests and logs."""

    state: CVProcessingState
    skills_added: int = 0


async def process_cv(
    database: Database,
    storage: CVStorage,
    *,
    cv_id: UUID,
    limits: PDFParserLimits,
) -> ProcessingOutcome:
    """Read one stored CV and write the skills it names onto its owner.

    Opens its own session: the request's is closed by the time this runs.

    A failure to read leaves the profile alone. A CV that cannot be parsed says
    nothing about the skills a candidate already has, and clearing them because
    a PDF was malformed would lose work they did by hand.

    A CV deleted while this runs writes nothing. Deleting one removes the skills
    it inferred, so a write landing afterwards would leave a profile holding
    skills from a document that no longer exists.
    """
    async with database.session() as session:
        cv = (await session.execute(select(CV).where(CV.id == cv_id))).scalars().first()
        if cv is None or cv.processing_state is CVProcessingState.PROCESSED:
            return ProcessingOutcome(state=CVProcessingState.PROCESSED)
        cv.transition_to(CVProcessingState.PROCESSING)
        await session.commit()

        owner_id, storage_key, checksum = cv.owner_id, cv.storage_key, cv.checksum_sha256

    try:
        extracted = await extract_stored_pdf_text(
            storage,
            PypdfTextExtractor(limits),
            storage_key=storage_key,
            expected_checksum_sha256=checksum,
            max_file_bytes=limits.max_file_bytes,
        )
    except PDFParsingFailure as failure:
        logger.warning(
            "a CV could not be read", extra={"cv_id": str(cv_id), "reason": failure.reason.value}
        )
        return await _finish(database, cv_id, CVProcessingState.FAILED)

    async with database.session() as session:
        # Locked rather than merely read. A delete arriving between this and the
        # write below would otherwise remove the CV's skills before they were
        # written, and the profile would keep them. Holding the row makes the
        # delete wait, and it then removes what this wrote.
        if await _locked(session, cv_id) is None:
            logger.info("a CV was deleted while it was being read", extra={"cv_id": str(cv_id)})
            return ProcessingOutcome(state=CVProcessingState.PROCESSED)

        profile = await find_profile(session, owner_id)
        if profile is None:
            # A CV uploaded before a profile exists is read and contributes
            # nothing. Creating a profile here would invent one from a document
            # rather than from anything the candidate said.
            await _transition(session, cv_id, CVProcessingState.PROCESSED)
            return ProcessingOutcome(state=CVProcessingState.PROCESSED)

        result = await store_cv_skills(session, profile_id=profile.id, text=extracted.text)
        await _transition(session, cv_id, CVProcessingState.PROCESSED)
        return ProcessingOutcome(state=CVProcessingState.PROCESSED, skills_added=len(result.added))


async def _locked(session: AsyncSession, cv_id: UUID) -> CV | None:
    """The CV row, held until this transaction ends, or nothing if it is gone."""
    found = await session.scalars(select(CV).where(CV.id == cv_id).with_for_update())
    return found.one_or_none()


async def _finish(database: Database, cv_id: UUID, state: CVProcessingState) -> ProcessingOutcome:
    async with database.session() as session:
        await _transition(session, cv_id, state)
    return ProcessingOutcome(state=state)


async def _transition(session: object, cv_id: UUID, state: CVProcessingState) -> None:

    assert isinstance(session, AsyncSession)
    cv = (await session.execute(select(CV).where(CV.id == cv_id))).scalars().first()
    if cv is None:
        return
    cv.transition_to(state)
    await session.commit()
