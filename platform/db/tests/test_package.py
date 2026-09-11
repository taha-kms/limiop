import ast
from pathlib import Path

from sqlalchemy import Table, UniqueConstraint

from platform_db.base import Base
from platform_db.models.boards import BoardStatus, JobBoard

PACKAGE_ROOT = Path(__file__).parents[1] / "platform_db"
FORBIDDEN_IMPORT_ROOTS = {"app", "backend", "fastapi", "httpx2", "starlette", "uvicorn"}


def test_base_imports() -> None:
    assert Base.__module__ == "platform_db.base"


def test_package_has_no_forbidden_imports() -> None:
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


def test_board_status_has_exactly_its_eight_values() -> None:
    assert {member.value for member in BoardStatus} == {
        "candidate",
        "confirmed",
        "named",
        "wrong_company",
        "not_found",
        "unreachable",
        "inactive",
        "blocked",
    }
    assert len(BoardStatus) == 8


def test_job_boards_has_a_unique_slug_per_source() -> None:
    table = JobBoard.__table__
    assert isinstance(table, Table)
    constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_job_boards_source_id_slug" in constraint_names
