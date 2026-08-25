# 02a — Make the backend depend on `platform-db`

## Why
`platform/db` exists but nothing uses it. Before any model moves into it, the
backend has to be able to resolve it — in a virtualenv, in the Docker image,
and in CI. That is packaging work, and it is separated from the model move
because the two fail in completely different ways and the combined change was
too large for one pass.

The constraint that forces the order: CI runs
`docker build --tag skillsync-backend:test backend`, and
`docker-compose.yml` builds with `context: ./backend`. `platform/` is outside
that context. The moment the backend depends on a local-path package, both
break. So the dependency and the build context have to land together, before
any code needs them.

## Scope
- `backend/pyproject.toml` gains `skillsync-platform-db` in `dependencies`.
- Make it resolvable from the local checkout, since the package is not
  published. Pick the mechanism that fits this repository's pip-and-setuptools
  tooling and keeps `pip install -e backend` working for a developer who has
  just cloned. Whatever you choose, it must work identically in a virtualenv,
  in the Docker build, and in CI — do not solve it three different ways.
- `backend/Dockerfile`: the image must contain `platform/db` and install it.
- `docker-compose.yml`: build context moves to the repository root with an
  explicit `dockerfile: backend/Dockerfile`. Adjust paths inside the Dockerfile
  to match the new context.
- `.github/workflows/backend.yml`: install `platform/db` before the backend,
  and change `docker build ... backend` to build from the repository root with
  `-f backend/Dockerfile`.
- `.github/workflows/airflow.yml`: `airflow/requirements.txt` installs
  `-e ../backend`, so Airflow's CI resolves the backend's dependencies too and
  needs the same treatment.

## Out of scope
Moving any model — that is 02b. The backend must not import `platform_db`
anywhere yet. This issue only makes the dependency resolvable.

## Acceptance
- `pip install -e platform/db -e backend` in a clean virtualenv succeeds, and
  `python -c "import platform_db, app.main"` works.
- `docker build -f backend/Dockerfile -t skillsync-backend:test .` succeeds.
- `docker compose config --quiet` passes and `docker compose build api`
  succeeds.
- `cd backend && pytest` passes, coverage gate included.
- `cd airflow && pytest` passes.
- No file under `backend/app/` imports `platform_db`.

Note: the Docker criteria cannot be run without a Docker daemon. If you have no
daemon, do the configuration work carefully and state plainly in your final
message which criteria are unverified and the exact commands to run.
