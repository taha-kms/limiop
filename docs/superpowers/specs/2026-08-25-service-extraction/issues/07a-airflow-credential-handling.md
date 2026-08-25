# 07a — Stop writing the Airflow admin password ourselves

## Why
CodeQL raises `py/clear-text-storage-sensitive-data` (CWE-312, high) against
`airflow/bootstrap.py:47`, where the admin password is written to disk as
plaintext JSON.

The finding is accurate. It is also work we should not be doing: Compose
already declares the user through
`AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS: admin:admin`, and Airflow's
`SimpleAuthManager` creates and stores that credential itself. The bootstrap
duplicates it.

Deleting our copy removes the alert and the duplication together. Suppressing
the alert would keep both.

## Scope
- Remove the admin-password half of `create_authentication_files()` in
  `airflow/bootstrap.py`, along with the now-unused `AIRFLOW_ADMIN_PASSWORD`
  and `AIRFLOW_ADMIN_USERNAME` handling, wherever they appear:
  `airflow/bootstrap.py`, `docker-compose.yml`, `.env.example`.
- Keep the JWT secret generation. A random secret written once to a
  `0o600` file, never derived from user input and never a stored credential, is
  a different thing from a password — but confirm CodeQL agrees rather than
  assuming it.
- Update `airflow/tests/test_bootstrap.py` to match. Do not delete the test
  file wholesale; the metadata-database half still needs its coverage,
  including the guard that refuses to put Airflow's metadata in the SkillSync
  database.
- If Airflow needs the passwords file to exist before it starts, create it
  empty rather than populated.

## Out of scope
Dismissing or suppressing the CodeQL alert. Changing the auth manager.
Anything about non-local deployment: this is the local Compose profile, the
port binds to `127.0.0.1`, and hardening beyond that is a deployment decision
that has not been made yet.

## Acceptance
- `docker compose --profile pipelines up --wait` brings `airflow-init`,
  `airflow-apiserver`, and `airflow-scheduler` to healthy from a clean volume.
- The Airflow UI is reachable and the generated admin credential works. Airflow
  prints it at startup; say in your final message where a developer finds it.
- `airflow dags list` shows `arbeitnow_ingestion`, unpaused.
- `cd airflow && pytest` passes.
- No occurrence of `AIRFLOW_ADMIN_PASSWORD` remains in the repository.

Note: the Docker criteria need a daemon. If you have none, do the work and say
precisely which criteria are unverified.
