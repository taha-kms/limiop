"""Import contracts for the API, ingestion service, and shared platform packages."""

import ast
from collections.abc import Iterable
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
APP_ROOT = REPOSITORY_ROOT / "backend" / "app"
JOB_INGESTION_ROOT = (
    REPOSITORY_ROOT / "services" / "job-ingestion-service" / "job_ingestion"
)
PLATFORM_DB_ROOT = REPOSITORY_ROOT / "platform" / "db"
PLATFORM_DB_PACKAGE_ROOT = PLATFORM_DB_ROOT / "platform_db"
PLATFORM_DB_SOURCE_ROOTS = (PLATFORM_DB_PACKAGE_ROOT, PLATFORM_DB_ROOT / "alembic")
PLATFORM_SKILLS_PACKAGE_ROOT = REPOSITORY_ROOT / "platform" / "skills" / "platform_skills"

ALLOWED_PLATFORM_DB_MODULES = frozenset(
    {
        "platform_db",
        "platform_db.base",
        "platform_db.models",
        "platform_db.models.catalog",
        "platform_db.models.skills",
        "platform_db.session",
    }
)


def imported_modules(source_path: Path) -> Iterable[tuple[int, str]]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.lineno, node.module


def assert_import_rule(
    *,
    rule: str,
    source_roots: Iterable[Path],
    forbidden_roots: frozenset[str],
) -> None:
    violations = []

    for source_root in source_roots:
        for source_path in sorted(source_root.rglob("*.py")):
            for line_number, imported_module in imported_modules(source_path):
                if imported_module.partition(".")[0] in forbidden_roots:
                    relative_path = source_path.relative_to(REPOSITORY_ROOT)
                    violations.append(
                        f"{relative_path}:{line_number} imports {imported_module}"
                    )

    assert not violations, f"Rule '{rule}' broken:\n" + "\n".join(violations)


def module_name(source_path: Path) -> str:
    relative_path = source_path.relative_to(PLATFORM_DB_PACKAGE_ROOT)
    module_parts = list(relative_path.with_suffix("").parts)
    if module_parts[-1] == "__init__":
        module_parts.pop()
    return ".".join(("platform_db", *module_parts))


def test_job_ingestion_does_not_import_app() -> None:
    assert_import_rule(
        rule="job_ingestion must not import app.*",
        source_roots=(JOB_INGESTION_ROOT,),
        forbidden_roots=frozenset({"app"}),
    )


def test_app_does_not_import_job_ingestion() -> None:
    assert_import_rule(
        rule="app.* must not import job_ingestion",
        source_roots=(APP_ROOT,),
        forbidden_roots=frozenset({"job_ingestion"}),
    )


def test_platform_db_does_not_import_services() -> None:
    assert_import_rule(
        rule="platform_db must not import app.* or job_ingestion",
        source_roots=PLATFORM_DB_SOURCE_ROOTS,
        forbidden_roots=frozenset({"app", "job_ingestion"}),
    )


def test_platform_db_does_not_import_service_frameworks() -> None:
    assert_import_rule(
        rule="platform_db must not import fastapi, starlette, uvicorn, or httpx2",
        source_roots=PLATFORM_DB_SOURCE_ROOTS,
        forbidden_roots=frozenset({"fastapi", "starlette", "uvicorn", "httpx2"}),
    )


def test_platform_db_contains_only_allowed_modules() -> None:
    actual_modules = {
        module_name(source_path)
        for source_path in PLATFORM_DB_PACKAGE_ROOT.rglob("*.py")
    }
    unexpected_modules = sorted(actual_modules - ALLOWED_PLATFORM_DB_MODULES)

    assert not unexpected_modules, (
        "Rule 'platform_db must contain only models, migrations, and the session factory' "
        f"broken; modules missing from the explicit allowlist: {unexpected_modules}"
    )


def test_platform_skills_does_not_import_services() -> None:
    assert_import_rule(
        rule="platform_skills must not import app.* or job_ingestion",
        source_roots=(PLATFORM_SKILLS_PACKAGE_ROOT,),
        forbidden_roots=frozenset({"app", "job_ingestion"}),
    )


def test_platform_skills_does_not_import_service_frameworks() -> None:
    assert_import_rule(
        rule="platform_skills must not import fastapi, starlette, or uvicorn",
        source_roots=(PLATFORM_SKILLS_PACKAGE_ROOT,),
        forbidden_roots=frozenset({"fastapi", "starlette", "uvicorn"}),
    )
