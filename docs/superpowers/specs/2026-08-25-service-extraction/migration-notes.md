# Alembic chain split upgrade

The split replaces the legacy backend history with independent platform and
backend baselines. Existing databases already contain every table described by
both baselines, so running either baseline as an upgrade would try to recreate
tables. Stamp those databases instead.

Before deploying the split, apply the final legacy revision with the previous
release of the repository:

```bash
cd backend
alembic upgrade head
alembic current
```

The current revision must be `0015_add_profile_skills`. Stop database writers,
back up the database, deploy the split, and keep the same
`SKILLSYNC_DATABASE_URL` configured for both commands below.

First create the platform chain's version row without running its baseline:

```bash
cd platform/db
alembic stamp head
```

Then replace the legacy value in the backend version table with the new
backend baseline:

```bash
cd ../../backend
alembic stamp --purge head
```

Confirm that each chain has exactly its new head:

```bash
cd ../platform/db
alembic current
cd ../../backend
alembic current
psql "${SKILLSYNC_DATABASE_URL/+psycopg/}" -c \
  "TABLE alembic_version_platform; TABLE alembic_version;"
```

The two rows must be `0001_platform_baseline` and `0001_backend_baseline`.
Fresh databases must not be stamped: run `alembic upgrade head` from
`platform/db/` first and then from `backend/`.
