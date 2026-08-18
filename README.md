# SkillSync

SkillSync helps job seekers understand how their skills and CV align with real job opportunities. It collects public job postings, extracts and normalizes requested skills, compares them with a user's profile, and presents job matches and skill gaps. Applications continue on the original employer or job-board website.

> SkillSync is in its initial development stage. The backend foundation is available; the remaining architecture and stack below describe the intended product direction.

## Product goals

- Parse uploaded CVs into structured skill profiles.
- Collect jobs from public and free sources such as Arbeitnow, Jobicy, Greenhouse, and Lever.
- Normalize job and skill data, with ESCO as a potential taxonomy source.
- Rank relevant jobs using understandable, evaluated matching methods.
- Explain match scores through matched and missing skills.
- Show reproducible job-market analytics and skill-demand trends.
- Redirect users to the original job posting when they choose to apply.

## Planned architecture

```text
External job sources
        |
        v
Apache Airflow pipelines ----> PostgreSQL
        |                           |
        |                           v
        +--------------------> FastAPI <---- ML inference
                                    |
                                    v
                              Next.js frontend
```

The main responsibility boundaries are:

- **Frontend:** presentation, browser interaction, frontend state, and API consumption.
- **Backend:** APIs, authentication, validation, business logic, persistence coordination, and ML inference integration.
- **Data platform:** ingestion, validation, normalization, deduplication, enrichment, and analytics workflows. Airflow orchestrates reusable Python modules rather than containing transformation logic directly in DAGs.
- **Machine learning:** skill extraction, matching, ranking, training, evaluation, and inference, with those stages kept separate.
- **PostgreSQL:** application and normalized job data. CV files and model artifacts belong in object storage when that infrastructure is introduced.

## Technology stack

| Area | Technologies |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS, Recharts |
| Backend | Python, FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL |
| Data engineering | Apache Airflow, Pandas and/or Polars |
| Machine learning | scikit-learn, sentence-transformers, ESCO |
| Testing | pytest, Playwright |
| Tooling | Docker, Docker Compose, GitHub Actions |
| Quality and security | Codecov, CodeQL, SonarQube, Dependabot |

## Repository layout

The monorepo is expected to grow toward this structure:

```text
skillsync/
├── frontend/          # Next.js application
├── backend/           # FastAPI application
├── airflow/           # DAGs and reusable pipeline modules
├── ml/                # Training, evaluation, and inference code
├── tests/             # Cross-component tests where appropriate
├── docker/            # Container configuration
├── docs/              # Architecture and project documentation
├── agent-skills/      # Repository-specific development guidance
├── .github/           # CI/CD and repository automation
├── AGENTS.md          # Repository contribution rules
└── docker-compose.yml # Local service orchestration
```

Directories should be added only when an implementation requires them.

## Getting started

The initial FastAPI backend includes typed environment configuration and a health endpoint. See the [backend setup guide](backend/README.md) for local installation, validation, and run commands.

The repository does not yet contain frontend, Airflow, database, or ML implementations. For the current product scope and architecture decisions, read [the project context](docs/PROJECT_CONTEXT.md). The intended local-development direction is Docker Compose with reproducible environments for the web application, API, PostgreSQL, and Airflow services.

## Development workflow

All meaningful changes follow an issue-first workflow:

1. Create or select a focused GitHub issue.
2. Create a small branch named `<type>/<issue-number>-<description>`.
3. Implement only the issue scope.
4. Add or update relevant tests.
5. Run applicable validation and review the diff.
6. Commit in small, focused steps.
7. Push the branch and open a pull request linked to the issue.
8. Review CI results before merge.

Read [AGENTS.md](AGENTS.md) before contributing. It defines the complete repository workflow, architecture boundaries, testing expectations, security requirements, and Git conventions.

## Data, privacy, and security

CVs and derived user information are sensitive. Do not commit real CVs, production data, credentials, database dumps, uploaded files, or trained model binaries. External job data and uploaded documents must be treated as untrusted input and validated at their boundaries.

Use environment variables or an approved secret store for credentials. Document required variables with placeholder-only `.env.example` files.

## Documentation

- [Project context](docs/PROJECT_CONTEXT.md): product purpose, architecture, technology choices, and component responsibilities.
- [Development rules](AGENTS.md): required workflow and engineering standards.
