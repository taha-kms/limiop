# 09 — Update the architecture documents

## Why
`PROJECT_CONTEXT.md` describes a monorepo whose backend owns ingestion. It also
lists an "expected structure" containing `ml/`, `tests/`, and `docker/`, none of
which exist. The documents should describe what is on disk and what was decided,
not what was imagined before the code existed.

## Scope
Update, without inventing new decisions:

- **§6 Backend** — the backend is the API. Ingestion, normalization,
  deduplication, and persistence of job postings are not its responsibility.
- **§7 Database** — one PostgreSQL, two Alembic chains, and the ownership rule:
  a table lives with whoever writes it, unless two deployables touch it. List
  which tables are in `platform/db` and which stay in the backend.
- **§10 Data Engineering** — Airflow depends on `services/job-ingestion-service`
  and never on the backend.
- **§15 Repository Strategy** — replace the aspirational tree with the real one:
  `platform/db`, `services/job-ingestion-service`, `backend`, `frontend`,
  `airflow`, `docs`. Do not list directories that do not exist.
- **§16 Local Development** — the pipelines compose profile.
- **§20 Architecture Principles** — leave the existing text alone. It forbids
  unnecessary microservices, brokers, additional databases, and Kubernetes, and
  none of this work introduces any of them. Add one principle: a service
  boundary goes where behaviour differs, never where storage differs, and the
  rejected data-access service as the worked example.
- **`AGENTS.md`** — update the module boundaries it encodes for agents so they
  match the new layout.
- **`docs/canonical-job-contract.md`** — note that it is now the interface
  between two deployables rather than an internal convention, which raises the
  cost of changing it.
- **`docs/delivery-plan.md`** — record this extraction in the phase table and
  the settled-decisions list. It sits before Phase C rather than inside it: the
  CV and profile work lands in the backend, and it should land in a backend that
  is only an API.

## Constraints
Match the existing prose style: plain declarative sentences, decisions stated
with their reasons, no marketing register.

## Acceptance
- Every path named in the documents exists on disk.
- No document still says the backend performs ingestion.
- `docs/delivery-plan.md` states what this phase's exit criterion was and that
  it was met.
