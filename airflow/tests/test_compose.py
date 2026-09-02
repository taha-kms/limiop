"""Static checks for the local Airflow Compose boundary."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
AIRFLOW_SERVICES = {"airflow-init", "airflow-scheduler", "airflow-apiserver"}


def test_default_compose_service_set_is_unchanged() -> None:
    default_services = {
        name for name, service in COMPOSE["services"].items() if "profiles" not in service
    }

    assert default_services == {
        "database",
        "migrate-platform",
        "migrate-backend",
        "api",
        "frontend",
    }


def test_airflow_services_use_the_pipeline_profile_and_private_database() -> None:
    services = COMPOSE["services"]

    assert services.keys() >= AIRFLOW_SERVICES
    assert all(services[name]["profiles"] == ["pipelines"] for name in AIRFLOW_SERVICES)

    environment = services["airflow-scheduler"]["environment"]
    assert "AIRFLOW_METADATA_DATABASE" in environment["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"]
    assert (
        environment["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN_ASYNC"]
        == environment["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"]
    )
    assert environment["SKILLSYNC_DATABASE_URL"].startswith("${SKILLSYNC_DATABASE_URL:")
    assert environment["AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION"] == "false"
    assert environment["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS"] == "admin:admin"


def test_airflow_image_does_not_install_the_backend() -> None:
    dockerfile = (ROOT / "airflow" / "Dockerfile").read_text()
    requirements = {
        line.strip()
        for line in (ROOT / "airflow" / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert "backend" not in dockerfile.lower()
    assert requirements == {"apache-airflow==3.2.2", "-e ../services/job-ingestion-service"}
