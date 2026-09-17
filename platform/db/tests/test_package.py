import ast
from pathlib import Path

from sqlalchemy import CheckConstraint, DateTime, String, Table, UniqueConstraint

from platform_db.base import Base
from platform_db.models.boards import BoardStatus, JobBoard
from platform_db.models.catalog import Company, Job
from platform_db.models.quota import SourceQuotaUsage

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


def test_companies_records_where_its_website_came_from() -> None:
    table = Company.__table__
    assert isinstance(table, Table)
    columns = {column.name: column for column in table.columns}
    website_source_type = columns["website_source"].type
    assert isinstance(website_source_type, String)
    assert website_source_type.length == 32
    assert columns["website_source"].nullable

    website_checked_at_type = columns["website_checked_at"].type
    assert isinstance(website_checked_at_type, DateTime)
    assert website_checked_at_type.timezone is True
    assert columns["website_checked_at"].nullable


def test_source_quota_usage_has_a_composite_primary_key_and_a_non_negative_check() -> None:
    table = SourceQuotaUsage.__table__
    assert isinstance(table, Table)
    assert table.primary_key.name == "pk_source_quota_usage"
    assert {column.name for column in table.primary_key.columns} == {"source_key", "day"}

    check_constraint_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_source_quota_usage_calls_not_negative" in check_constraint_names

    columns = {column.name: column for column in table.columns}
    assert isinstance(columns["source_key"].type, String)
    assert columns["source_key"].type.length == 64
    assert columns["calls"].nullable is False
    updated_at_type = columns["updated_at"].type
    assert isinstance(updated_at_type, DateTime)
    assert updated_at_type.timezone is True


def test_jobs_records_when_retention_anonymised_them() -> None:
    table = Job.__table__
    assert isinstance(table, Table)
    columns = {column.name: column for column in table.columns}
    anonymised_at_type = columns["anonymised_at"].type
    assert isinstance(anonymised_at_type, DateTime)
    assert anonymised_at_type.timezone is True
    assert columns["anonymised_at"].nullable
