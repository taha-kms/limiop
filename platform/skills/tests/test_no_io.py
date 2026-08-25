import ast
import builtins
import socket
from pathlib import Path
from uuid import UUID

import pytest

from platform_skills import extract_mentions

PACKAGE_ROOT = Path(__file__).parents[1] / "platform_skills"
FORBIDDEN_IMPORT_ROOTS = {
    "app",
    "fastapi",
    "httpx",
    "httpx2",
    "job_ingestion",
    "psycopg",
    "requests",
    "sqlalchemy",
    "starlette",
    "urllib",
    "uvicorn",
}


def test_package_has_no_database_network_or_service_imports() -> None:
    imported_modules: set[str] = set()

    for source_path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)

    imported_roots = {module.partition(".")[0] for module in imported_modules}
    assert imported_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)


def test_extraction_succeeds_when_file_and_network_access_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("I/O is forbidden during extraction")

    monkeypatch.setattr(builtins, "open", blocked)
    monkeypatch.setattr(socket, "socket", blocked)

    mentions = extract_mentions(
        "Postgres",
        {"postgres": UUID("25a5528c-45a4-4a1d-a43c-45f3f4e79a20")},
    )

    assert mentions[0].surface_form == "Postgres"
