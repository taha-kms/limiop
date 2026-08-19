"""Structure tests that keep DAG files thin.

These load DAGs through Airflow's own DagBag, so an import error here means the
DAG would also fail to load in a real Airflow deployment.
"""

import ast
from datetime import timedelta
from pathlib import Path

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk import DAG

DAGS_DIR = Path(__file__).parents[1] / "dags"
DAG_ID = "arbeitnow_ingestion"

# Names a DAG file may call at module scope or inside a task. Anything else
# suggests transformation logic is growing where it cannot be tested.
ALLOWED_CALLS = frozenset(
    {
        "dag",
        "task",
        "ingest",
        "arbeitnow_ingestion",
        "asyncio.run",
        "ingest_arbeitnow",
        "datetime",
        "timedelta",
    }
)


@pytest.fixture(scope="session")
def dagbag() -> DagBag:
    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def call_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            names.add(ast.unparse(node.func))
    return names


def test_every_dag_imports_cleanly(dagbag: DagBag) -> None:
    assert dagbag.import_errors == {}


def test_the_ingestion_dag_is_registered(dagbag: DagBag) -> None:
    assert DAG_ID in dagbag.dags


def test_the_dag_is_scheduled_and_does_not_backfill(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert dag.schedule == "0 * * * *"
    assert dag.catchup is False
    assert dag.max_active_runs == 1


def test_failure_behavior_is_explicit(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]
    task = dag.get_task("ingest")

    assert task.retries == 2
    assert task.retry_delay == timedelta(minutes=5)
    assert task.execution_timeout == timedelta(minutes=15)


def test_the_dag_stays_a_single_thin_task(dagbag: DagBag) -> None:
    dag: DAG = dagbag.dags[DAG_ID]

    assert [task.task_id for task in dag.tasks] == ["ingest"]


def test_the_dag_delegates_to_reusable_application_code() -> None:
    source = (DAGS_DIR / f"{DAG_ID}.py").read_text()

    assert "from app.modules.ingestion.arbeitnow import ingest_arbeitnow" in source


@pytest.mark.parametrize("dag_file", sorted(DAGS_DIR.glob("*.py")), ids=lambda path: path.name)
def test_no_business_logic_grows_inside_a_dag_file(dag_file: Path) -> None:
    tree = ast.parse(dag_file.read_text())

    unexpected = call_names(tree) - ALLOWED_CALLS

    assert unexpected == set(), f"{dag_file.name} calls {sorted(unexpected)}"


@pytest.mark.parametrize("dag_file", sorted(DAGS_DIR.glob("*.py")), ids=lambda path: path.name)
def test_a_dag_file_defines_no_database_or_transport_access(dag_file: Path) -> None:
    imported = {
        alias.name
        for node in ast.walk(ast.parse(dag_file.read_text()))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(ast.parse(dag_file.read_text()))
        if isinstance(node, ast.ImportFrom)
    }

    assert not {name for name in imported if name.startswith(("sqlalchemy", "httpx", "psycopg"))}
