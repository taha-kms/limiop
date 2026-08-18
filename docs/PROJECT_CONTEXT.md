# SkillSync Project Context

## 1. Project Overview

**SkillSync** is a web application that helps job seekers understand how well their skills and CV match real job opportunities.

The platform collects job postings from public and free job-data sources, analyzes the skills requested by employers, compares those requirements against a user's CV, and recommends relevant jobs and missing skills.

Users are redirected to the original job posting when they want to apply. SkillSync does not act as a job application platform itself.

---

## 2. Core Problem

Job seekers often face three problems:

1. They do not know which jobs best match their current skills.
2. They do not know which skills they are missing for a target role.
3. They have difficulty understanding which technologies and skills are currently in demand.

SkillSync addresses these problems using job-market data, data analysis, and machine learning.

---

## 3. Main User Flow

The expected user flow is:

1. User creates an account.
2. User uploads a CV.
3. SkillSync extracts structured information and technical skills from the CV.
4. SkillSync retrieves active jobs from its database.
5. The system compares the user's skills and CV against job requirements.
6. Each job receives a match score.
7. The user sees:

   * matched skills
   * missing skills
   * job information
   * match percentage
   * recommended jobs
8. The user can open the original job posting to apply.

Example:

```text
User CV
   ↓
CV Parsing
   ↓
Skill Extraction
   ↓
User Skill Profile
   ↓
Job Matching Engine
   ↓
Recommended Jobs
   ↓
Original Job Application Page
```

---

## 4. Main Product Areas

SkillSync contains several major technical areas.

### Web Application

Provides the user-facing product.

Responsibilities include:

* authentication
* user profiles
* CV upload
* job browsing
* recommended jobs
* match scores
* skill-gap visualization
* job-market analytics

---

### Backend API

The backend provides application logic and APIs used by the frontend.

Primary responsibilities include:

* authentication and authorization
* user management
* CV management
* job retrieval
* job filtering
* job recommendations
* skill matching
* analytics endpoints
* communication with PostgreSQL
* communication with ML components

The backend is implemented using **Python and FastAPI**.

---

## 5. Frontend

The frontend uses:

* Next.js
* TypeScript
* Tailwind CSS
* Recharts

The frontend should communicate with the backend through clearly defined APIs.

Business logic, machine-learning logic, and direct database access should not be implemented in frontend components.

---

## 6. Backend

The backend uses:

* Python
* FastAPI
* SQLAlchemy
* Pydantic
* PostgreSQL

FastAPI is responsible for exposing REST APIs.

SQLAlchemy is responsible for database access.

Pydantic is responsible for request, response, configuration, and validation models where appropriate.

---

## 7. Database

The primary application database is **PostgreSQL**.

Expected entities include:

```text
users
cvs
jobs
companies
skills
job_skills
cv_skills
job_matches
saved_jobs
pipeline_runs
model_metadata
```

The schema may evolve as requirements become clearer.

Large binary files such as CV documents and ML model artifacts should not be stored directly in PostgreSQL.

---

## 8. Job Data Sources

SkillSync should prioritize public and free data sources.

Initial sources may include:

* Arbeitnow
* Jobicy
* Greenhouse public job boards
* Lever public job postings

SkillSync should maintain a source-independent internal job representation.

Each external source may have a different schema, but all jobs should eventually be normalized into the SkillSync job schema.

Example pipeline:

```text
External Job API
      ↓
Raw Data
      ↓
Validation
      ↓
Cleaning
      ↓
Normalization
      ↓
Deduplication
      ↓
Skill Extraction
      ↓
PostgreSQL
```

Each stored job should preserve its original source and application URL.

---

## 9. Skills Taxonomy

SkillSync may use **ESCO** as a standardized source for occupations and skills.

ESCO can help normalize skill names and relationships.

For example:

```text
Postgres
PostgreSQL
PostgreSQL Database
```

should not automatically be treated as unrelated concepts.

Skill normalization should be handled independently from the frontend.

---

## 10. Data Engineering

**Apache Airflow** is the workflow orchestrator for SkillSync.

Airflow is responsible for scheduled and repeatable data workflows.

Expected DAGs may include:

```text
job_ingestion
job_normalization
job_deduplication
skill_extraction
job_expiration
analytics_aggregation
model_training
model_evaluation
```

Airflow should orchestrate jobs rather than contain large amounts of business logic directly inside DAG files.

Reusable processing logic should live in normal Python modules and be called by Airflow tasks.

---

## 11. Raw and Processed Data

Data should conceptually move through stages.

```text
External Source
      ↓
Raw
      ↓
Cleaned
      ↓
Normalized
      ↓
Enriched
      ↓
Application / Analytics Data
```

Raw source data should be preserved where practical so transformations can be reproduced and debugged.

The production application should primarily consume cleaned and normalized data.

---

## 12. Data Analysis

SkillSync should provide job-market insights such as:

* most requested skills
* skill demand by job role
* jobs by location
* jobs by company
* remote versus onsite opportunities
* common skill combinations
* technology trends
* job-posting trends over time

Analytics should be calculated from collected job data rather than hardcoded values.

---

## 13. Data Science and Machine Learning

Machine learning is used primarily for:

* CV-to-job matching
* semantic similarity
* skill extraction
* skill-gap detection
* job recommendation
* potentially job-demand analysis

The first implementation should favor understandable baseline models before introducing unnecessary complexity.

Possible progression:

```text
TF-IDF
   ↓
Cosine Similarity
   ↓
Sentence Embeddings
   ↓
More advanced ranking models
```

Models must be evaluated rather than adopted solely because they are more sophisticated.

---

## 14. Model Artifacts

Machine-learning model binaries should not be committed directly to Git.

Model code belongs in the repository.

Model artifacts belong in external object storage when production storage is introduced.

A future production setup may use:

```text
AWS S3
```

for:

* model artifacts
* uploaded CV files
* selected raw data artifacts

PostgreSQL may store metadata pointing to those artifacts.

---

## 15. Repository Strategy

SkillSync should use a monorepo.

Expected high-level structure:

```text
skillsync/
├── frontend/
├── backend/
├── airflow/
├── ml/
├── tests/
├── docker/
├── docs/
├── .github/
├── docker-compose.yml
└── README.md
```

The exact structure may evolve, but responsibilities should remain clearly separated.

---

## 16. Local Development

Local development should use Docker where appropriate.

A developer should eventually be able to start the main local environment using Docker Compose.

Typical local services may include:

```text
Next.js
FastAPI
PostgreSQL
Airflow Webserver
Airflow Scheduler
Airflow Worker
```

Machine-learning and pipeline code should execute within reproducible Python environments.

---

## 17. CI/CD

GitHub is the primary source-code repository.

GitHub Actions is the main CI/CD automation system.

The project uses:

* GitHub Actions
* Codecov
* CodeQL
* SonarQube
* Dependabot

These tools have different responsibilities.

### GitHub Actions

Responsible for:

* running CI workflows
* running tests
* linting
* building applications
* building Docker images
* deployment workflows

### Codecov

Responsible for:

* tracking test coverage
* reporting coverage changes
* identifying untested code

### CodeQL

Responsible for:

* static security analysis
* identifying vulnerable code patterns

### SonarQube

Responsible for:

* code quality analysis
* maintainability checks
* code smells
* duplicated code
* selected security findings

### Dependabot

Responsible for:

* dependency monitoring
* dependency update pull requests
* security-related dependency updates

---

## 18. Testing

Testing is a first-class requirement.

The project should include appropriate:

* unit tests
* integration tests
* API tests
* data-pipeline tests
* data-validation tests
* ML evaluation tests
* frontend tests
* end-to-end tests where useful

Primary tools include:

```text
Backend:
pytest

Frontend / E2E:
Playwright
```

Coverage should be reported through Codecov.

---

## 19. Deployment Direction

Initial deployment should remain reasonably simple.

Possible architecture:

```text
GitHub
   ↓
GitHub Actions
   ↓

Frontend
Next.js
   ↓
Vercel

Backend
FastAPI
   ↓
Cloud application/container host

Database
PostgreSQL
   ↓
Managed PostgreSQL

Data Pipelines
Apache Airflow
   ↓
Containerized/cloud environment

Files / Models
   ↓
Object Storage
```

The architecture may later migrate toward AWS services when justified.

Possible future AWS components include:

```text
S3
RDS PostgreSQL
ECS / Fargate
MWAA
Secrets Manager
CloudWatch
```

Do not introduce cloud services merely for architectural complexity.

---

## 20. Architecture Principles

When working on SkillSync, follow these principles.

### Prefer clear boundaries

Frontend, backend, data pipelines, and machine-learning logic should have distinct responsibilities.

### Prefer simple solutions first

Build the simplest correct implementation before introducing additional infrastructure or abstraction.

### Keep code reusable

Shared logic should live in reusable modules instead of being duplicated across API routes, DAGs, scripts, or notebooks.

### Keep pipelines reproducible

Data transformations should be deterministic and testable where practical.

### Keep secrets outside the repository

Never commit:

* passwords
* tokens
* API keys
* private certificates
* database credentials

Use environment variables or secret-management systems.

### Keep production data out of Git

Do not commit:

* real user CVs
* production database dumps
* secrets
* large datasets
* trained model binaries

### Preserve external job attribution

Jobs should retain information about their original source and original application URL.

### Do not over-engineer

Do not introduce:

* unnecessary microservices
* distributed systems
* message brokers
* Kubernetes
* additional databases
* unnecessary cloud products

unless there is a demonstrated technical requirement.

---

## 21. Current Technology Stack

```text
Frontend
- Next.js
- TypeScript
- Tailwind CSS
- Recharts

Backend
- Python
- FastAPI
- SQLAlchemy
- Pydantic

Database
- PostgreSQL

Data Engineering
- Apache Airflow
- Pandas and/or Polars

Data Science
- scikit-learn
- sentence-transformers
- ESCO

Testing
- pytest
- Playwright

DevOps
- Docker
- Docker Compose
- GitHub Actions
- Codecov
- CodeQL
- SonarQube
- Dependabot
```

---

## 22. Agent Guidance

Before implementing a feature:

1. Understand which SkillSync component owns the responsibility.
2. Inspect existing code before creating new abstractions.
3. Preserve established architecture and naming conventions.
4. Avoid introducing dependencies without a clear benefit.
5. Add or update tests for meaningful behavior changes.
6. Keep data-engineering logic outside Airflow DAG definitions where possible.
7. Keep machine-learning experimentation separate from production inference code.
8. Keep frontend components independent from database implementation details.
9. Never commit credentials, user data, or generated model binaries.
10. Prefer incremental, reviewable changes over large rewrites.

If existing code conflicts with this document, inspect the surrounding implementation before changing architecture. Do not silently redesign the project.
