"""Temporary probe: does a replacement leave the old CV's skills behind?"""

import pytest
from sqlalchemy import create_engine, text

from tests.api.test_cvs import (  # type: ignore[import-not-found]
    CVClient,
    cv_client,  # noqa: F401
    cv_rows,
    profile_with_skills,
    sign_in,
    stored_concepts,
    upload,
)

pytestmark = pytest.mark.integration


def test_probe_replacement_leaves_cv_sourced_skills(cv_client: CVClient) -> None:
    owner_id = sign_in(cv_client)
    first = upload(cv_client).json()["id"]
    from_cv, by_hand = profile_with_skills(cv_client, owner_id)

    second = upload(cv_client, b"%PDF-1.7\nnewer")
    assert second.status_code == 201

    rows = cv_rows(cv_client.database_url)
    engine = create_engine(str(cv_client.database_url))
    with engine.connect() as connection:
        skills = [
            dict(row)
            for row in connection.execute(
                text("SELECT concept_id, source FROM candidate_profile_skills")
            ).mappings()
        ]
    engine.dispose()

    print("FIRST CV:", first)
    print("SECOND CV:", second.json()["id"], second.json().get("processing_state"))
    print("CV ROWS:", [(str(r["id"]), r["processing_state"]) for r in rows])
    print("SKILLS:", skills)
    print("from_cv concept still present:", from_cv in stored_concepts(cv_client))
    print("storage deleted:", cv_client.storage.deleted)
    print("storage objects:", list(cv_client.storage.objects))
