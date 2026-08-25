"""Initialize the local Airflow metadata database and authentication files."""

import json
import os
import secrets
from pathlib import Path

import psycopg
from psycopg import sql


def create_metadata_database() -> None:
    """Create Airflow's private database in the shared PostgreSQL server."""
    database_name = os.environ["AIRFLOW_METADATA_DATABASE"]
    if database_name == os.environ["POSTGRES_DB"]:
        raise ValueError("Airflow metadata must use a database separate from SkillSync")

    connection_parameters = {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "autocommit": True,
    }

    with psycopg.connect(**connection_parameters) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def create_authentication_files() -> None:
    """Create persistent local credentials without embedding secrets in Compose."""
    jwt_secret_file = Path(os.environ["AIRFLOW_JWT_SECRET_FILE"])
    if not jwt_secret_file.exists():
        jwt_secret_file.write_text(secrets.token_urlsafe(48))
        jwt_secret_file.chmod(0o600)

    password_file = Path(os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
    passwords = json.loads(password_file.read_text()) if password_file.exists() else {}
    username = os.environ["AIRFLOW_ADMIN_USERNAME"]
    if username not in passwords:
        passwords[username] = os.environ.get("AIRFLOW_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
        password_file.write_text(json.dumps(passwords) + "\n")
        password_file.chmod(0o600)


if __name__ == "__main__":
    create_metadata_database()
    create_authentication_files()
