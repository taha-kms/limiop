import ast
from pathlib import Path

from platform_db.base import Base

PACKAGE_ROOT = Path(__file__).parents[1] / "platform_db"
FORBIDDEN_IMPORT_ROOTS = {"app", "backend", "fastapi", "httpx2", "starlette", "uvicorn"}


def test_base_imports() -> None:
    assert Base.__module__ == "platform_db.base"


def test_package_has_no_forbidden_imports() -> None:
    imported_modules: set[str] = set()

    for source_path in PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)

    imported_roots = {module.partition(".")[0] for module in imported_modules}
    assert imported_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
