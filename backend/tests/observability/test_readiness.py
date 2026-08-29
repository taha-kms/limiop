"""Liveness and readiness."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.observability import readiness
from app.observability.readiness import (
    DependencyState,
    check_database,
    check_storage,
)


def test_storage_that_can_be_written_is_up(tmp_path: Path) -> None:
    report = asyncio.run(check_storage(tmp_path / "cvs"))

    assert report.state is DependencyState.UP
    assert report.reason is None


def test_storage_that_exists_but_cannot_be_written_is_down(tmp_path: Path) -> None:
    """Presence is not usability: a read-only directory passes any check that
    only looks, and fails the first upload."""
    root = tmp_path / "cvs"
    root.mkdir()
    root.chmod(0o500)
    try:
        report = asyncio.run(check_storage(root))
    finally:
        root.chmod(0o700)

    assert report.state is DependencyState.DOWN
    assert report.reason == "unavailable"


def test_an_unreachable_database_is_down_without_naming_the_connection() -> None:
    """A driver's message carries the connection string, and readiness is
    reachable before anything has authenticated."""
    engine = create_async_engine("postgresql+psycopg://nobody:secret@127.0.0.1:1/nothing")
    try:
        report = asyncio.run(check_database(engine))
    finally:
        asyncio.run(engine.dispose())

    assert report.state is DependencyState.DOWN
    assert report.reason == "unavailable"
    assert "secret" not in (report.reason or "")


def test_a_check_that_hangs_is_reported_rather_than_waited_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A probe that hangs is worse than one that fails: failing is an answer."""
    monkeypatch.setattr(readiness, "CHECK_TIMEOUT_SECONDS", 0.05)

    async def forever() -> None:
        await asyncio.sleep(10)

    async def run() -> None:
        report = await readiness._bounded("slow", forever)
        assert report.state is DependencyState.DOWN
        assert report.reason == "timed out"

    asyncio.run(asyncio.wait_for(run(), timeout=2))


@pytest.mark.integration
def test_liveness_touches_nothing_external(migrated_client: TestClient) -> None:
    assert migrated_client.get("/health").json() == {"status": "ok"}


@pytest.mark.integration
def test_readiness_reports_every_dependency_when_all_are_usable(
    migrated_client: TestClient,
) -> None:
    response = migrated_client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert {row["name"] for row in body["dependencies"]} == {"database", "cv_storage"}
    assert all(row["state"] == "up" for row in body["dependencies"])


@pytest.mark.integration
def test_readiness_answers_503_when_a_dependency_is_unusable(
    migrated_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A load balancer reads the status code. `degraded` under a 200 is a body
    nobody reads."""
    from app.api.routes import health

    async def down(*_: object, **__: object) -> readiness.DependencyReport:
        return readiness.DependencyReport(
            name="database", state=DependencyState.DOWN, reason="unavailable"
        )

    monkeypatch.setattr(health, "check_database", down)

    response = migrated_client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert {row["name"]: row["state"] for row in body["dependencies"]}["database"] == "down"


@pytest.mark.integration
def test_a_liveness_probe_stays_healthy_while_readiness_is_degraded(
    migrated_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise one outage becomes a restart loop."""
    from app.api.routes import health

    async def down(*_: object, **__: object) -> readiness.DependencyReport:
        return readiness.DependencyReport(
            name="database", state=DependencyState.DOWN, reason="unavailable"
        )

    monkeypatch.setattr(health, "check_database", down)

    assert migrated_client.get("/health/ready").status_code == 503
    assert migrated_client.get("/health").status_code == 200
