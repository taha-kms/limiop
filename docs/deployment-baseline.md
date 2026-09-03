# The production deployment baseline

Issue #64. What has to be true of an environment before this runs in it, and
who is responsible for what. No provider is chosen here, because choosing one
before the requirements are written is how the requirements end up describing
whatever was chosen.

## What is deployed

Four things run, and they are separately deployable on purpose.

| Unit | What it is | Scales with |
| --- | --- | --- |
| `backend` | The API. FastAPI over PostgreSQL, serving the public catalogue, accounts, profiles, CVs, matching, and analytics. | Read traffic |
| `frontend` | The Next.js application. Server-renders every page, including personalized ones, from the session cookie. | Read traffic |
| `job-ingestion-service` | The pipeline. Installed as a library and run by a scheduler, never as a server. | Source count and catalogue size |
| `airflow` | The scheduler that runs the pipeline hourly. Orchestrates; does not transform. | Nothing — one instance |

PostgreSQL is the only datastore, shared by all of them. There is no second one,
and adding one needs a demonstrated need rather than a preference.

`job-ingestion-service` has no HTTP surface. It is a Python package Airflow
imports, which is why the API image does not contain it and the Airflow image
does not contain FastAPI.

## Sizing

Measured on a built stack, one container per unit, idle and then under traffic.
Resident memory, because that is what a host runs out of first.

| Unit | Idle | Peak measured | CPU idle |
| --- | --- | --- | --- |
| `database` | 43–59 MiB fresh, 104 MiB once Airflow's metadata database exists | grows toward `shared_buffers`, 128 MiB by default | ~1% |
| `backend` | 71–82 MiB | **+256 MiB** while hashing | <1% |
| `frontend` | 49 MiB, 52 MiB under traffic | — | <1% |
| `airflow-scheduler` | **511 MiB** | 580 MiB during a run | **5–50%, 75% during a run** |
| `airflow-apiserver` | **217 MiB** | — | <1% |

The backend's peak is a ceiling rather than an estimate. Argon2id costs 64 MiB
per call at the library's current defaults, and `MAX_CONCURRENT_HASHES` caps
concurrent hashing at four; past that, hashing queues rather than fanning out.
Four times 64 MiB is the whole of it. It is the one cost in the stack that an
unauthenticated caller can provoke, which is why it is bounded rather than
merely small.

`uvicorn` runs one worker. A second replica doubles these figures, and also
gives every account a second rate-limit budget, for the reason under **Rate
limiting**.

### What a host needs

Two answers, because two of the questions under **What is still open** move the
number and neither is decided.

| | Airflow, and the frontend image built on the host | Cron, and the image built in CI |
| --- | --- | --- |
| Memory | **4 GB** | **2 GB** |
| Cores | **2** | 1, though 2 is better |
| Disk | **40 GB** | **20 GB** |

Steady state, summing the idle column, is about 970 MiB with Airflow and about
190 MiB without it. The rest is headroom for the hashing ceiling, the operating
system, and the page cache PostgreSQL reads through. Its reported memory climbs
with traffic because that cache is attributed to it, so the floor is
`shared_buffers` plus `work_mem` per connection rather than whatever a running
host reports.

Two cores rather than one even at the smaller size, because argon2id runs with
`parallelism=4`: on a single core a sign-in serialises into roughly four times
its measured 60 ms.

Building the frontend image on the host rather than in CI is what forces the
larger box, and it is the weakest reason to buy one. `next build` peaked at
436 MiB in its largest process at 201% CPU, and the tree it needs —
`node_modules` at 698 MB and `.next` at 184 MB — is most of the difference
between the two disk figures. The image itself is 230 MB; a host that pulls it
needs none of that.

Disk, itemised: the images are 297 MB for PostgreSQL, 231 MB for the backend,
230 MB for the frontend and 384 MB for Airflow. The database volume starts at
84 MB with the schema alone and reached 179 MB with a development catalogue in
it. CVs are capped at 5 MiB each by `SKILLSYNC_CV_MAX_UPLOAD_BYTES`, so that
line grows with accounts and nothing else. The rest is logs and headroom.

## Runtime inputs

Values are never in this repository. What follows is the list of names an
environment must supply, and what happens when one is missing.

### Required everywhere

| Name | Consumed by | Missing behaviour |
| --- | --- | --- |
| `SKILLSYNC_DATABASE_URL` | backend, ingestion, both Alembic chains | Falls back to a localhost default that will not resolve in a container |
| `SKILLSYNC_ENVIRONMENT` | backend | Defaults to `local`, which disables the secure cookie flag |

### Required outside local and test

| Name | Consumed by | Missing behaviour |
| --- | --- | --- |
| `SKILLSYNC_SESSION_SECRET` | backend | **The application refuses to start.** There is deliberately no usable default: one would be a production signing key committed to a public repository |

### Required by the frontend

| Name | Consumed by | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | browser | Inlined at build time, so it must be the address a browser can reach. Not a secret |
| `SKILLSYNC_API_URL` | frontend server | The address the server uses, which in a container is not the browser's |

Two variables rather than one because the browser and the server do not reach
the API at the same address, and a single value cannot be right for both.

### Optional, with defaults that are safe

`SKILLSYNC_SESSION_LIFETIME_MINUTES` (60), `SKILLSYNC_CV_MAX_UPLOAD_BYTES`,
`SKILLSYNC_CV_STORAGE_ROOT`, `SKILLSYNC_CV_PDF_MAX_PAGES`,
`SKILLSYNC_SKILL_ALIAS_VERSION` (unset follows the newest published table),
`SKILLSYNC_AUTH_ATTEMPTS` (10) and `SKILLSYNC_AUTH_ATTEMPT_WINDOW_SECONDS` (60),
`SKILLSYNC_SOURCE_CONFIG` (per-source JSON; `{"greenhouse":{"boards":["hudl"]}}`
polls those boards instead of the shipped list, and an absent or empty list
means the shipped one rather than no boards; a `base_url` key in the same
block reads a provider's regional host, for example
`{"lever":{"base_url":"https://api.eu.lever.co/v0/postings"}}`, and is
absent otherwise; `polymer` and `pinpoint` take the same `boards` list and
ship with none, for example `{"polymer":{"boards":["acme"]}}`).

### Secrets, by handling

Only two values are secret: `SKILLSYNC_SESSION_SECRET` and the password inside
`SKILLSYNC_DATABASE_URL`. Both must come from the platform's secret store rather
than from an image, a compose file, or a repository. Neither appears in any log
line: the structured logger writes fields rather than formatted messages, and
readiness reports a failing dependency as `unavailable` rather than echoing a
driver error that carries the connection string.

## Migrations

Two Alembic chains against one database, and they are applied in order:

```
alembic -c platform/db/alembic.ini upgrade head    # shared tables
alembic -c backend/alembic.ini upgrade head        # backend-private tables
```

The platform chain owns everything two deployables touch — the catalogue, the
skill vocabulary, ingestion runs. The backend chain owns `users`, `cvs`,
`candidate_profiles`, and `candidate_profile_skills`. Each has its own version
table, so neither can apply the other's revisions.

**Migrations run before the new image serves traffic, and never from inside it.**
A container that migrates on start races every other replica of itself. The
platform chain must run first: the backend chain has a foreign key into
`skill_concepts`, which the platform chain creates.

Every migration in this repository has a `downgrade`, and the one that added a
column was applied, reversed and re-applied against a real database before it
merged. That is the rollback path for schema: reverse the revision, then deploy
the previous image.

## Health

| Endpoint | Answers | Probe |
| --- | --- | --- |
| `GET /health` | Is this process alive | Liveness |
| `GET /health/ready` | Can it serve — database reachable, CV storage writable | Readiness |
| `GET /health/ingestion` | What each source's most recent run did | Neither |

Liveness touches nothing external, deliberately. A liveness probe that talks to
the database turns one outage into a restart loop. Readiness checks both
dependencies under a two-second timeout each and answers **503** when either is
unusable, because a load balancer reads the status code.

A deployment is not complete until readiness answers 200. A rollout that waits
only for liveness will route traffic to a process whose database is unreachable.

The ingestion report is neither probe. The rule it exists to be read against:
**a source is stale when its last completed run finished more than six hours
ago, and failed when its most recent run failed.** Both DAGs run hourly, so six
hours is six missed runs. An uptime check reads `runs[].state` and
`runs[].finished_at`; a source that has never run is absent, and a pipeline
that was never deployed is not an incident.

It answers 200 even when the last run failed: a stalled pipeline serves a catalogue that is merely getting staler, and
taking the API out of rotation over it would turn a stale catalogue into no
catalogue. It reports facts — state, when the run finished, and its counts — and
leaves "too old" to whoever set the schedule. A source that has never run is
absent rather than listed as idle. What makes silence expensive here is that a
posting cannot be re-fetched once it leaves its board.

## Rate limiting

Registration and sign-in are the only unauthenticated write endpoints, and both
cost an argon2id hash. Each **account** gets `SKILLSYNC_AUTH_ATTEMPTS` attempts
per `SKILLSYNC_AUTH_ATTEMPT_WINDOW_SECONDS`, refused with **429** and a
`Retry-After` before any hashing happens. Sign-in counts only failures;
registration counts every attempt on one address.

Per account rather than per caller, because of the topology. The browser never
reaches the API directly: it posts to the frontend, which re-issues the call
server-side, so every browser-originated attempt arrives from one address.
Keying on that address made the limit a single shared budget — ten failed
sign-ins from anybody refused sign-in for everybody.

So be exact about what this bounds. Guessing one account's password is bounded,
from however many addresses. **Creating many accounts under many addresses is
not**: the only signal that would bound it is a caller identity this process
cannot see through the frontend hop, so volume abuse belongs at the edge — a
rate limit on the ingress or CDN in front of the frontend, not here.

The counter is per process and in memory, which is right for the single replica
that is deployed and is not right for several: two replicas give an account two
budgets. It is bounded in size, so the number of distinct addresses attempted
cannot grow it without limit.

## Persistent state

| What | Where | If lost |
| --- | --- | --- |
| The catalogue, profiles, accounts | PostgreSQL | Everything is lost. This is the only thing that must be backed up |
| Uploaded CVs | A filesystem path behind one interface (`CVStorage`) | Candidates re-upload. Metadata rows would point at nothing |
| Airflow metadata | PostgreSQL, a separate database on the same server | Scheduling history. Re-created on next start |

CV storage is behind an interface with one implementation. Moving it to object
storage is a new implementation and no other change, which is why the interface
exists and why the choice is not made here.

Local development keeps PostgreSQL on an **external** Docker volume, so the
catalogue survives `docker compose down -v`. A hosted environment should use
whatever the provider's equivalent durable volume is, and the same reasoning
applies: the thing that took hours to collect must not be deleted by a routine
command.

## Backup and recovery

- **PostgreSQL is the only thing that must be backed up.** Everything else is
  re-derivable: the catalogue can be re-ingested, the images rebuilt from a tag.
- Restoring is a `pg_restore` followed by running both migration chains to head.
- The catalogue is re-derivable *in principle* and not *in practice*: a posting
  removed from its source cannot be fetched again. 64 of 78 gold postings were
  lost that way, which is recorded in the delivery plan as the reason a
  measurement commits its evidence. A backup is the only thing standing between
  the stored catalogue and that.

## Rollback

| Change | Reversed by |
| --- | --- |
| Application code | Deploy the previous image tag |
| A schema migration | `alembic downgrade`, then the previous image |
| An alias table | Publish nothing; set `SKILLSYNC_SKILL_ALIAS_VERSION` to the previous version. Tables are immutable once published and are never edited in place |

Alias versions are the one piece of state a rollback does not need to undo. A
published version is immutable, every stored skill records which version
produced it, and pinning an older one is a configuration change.

## Observability

Structured JSON logs on stdout, one object per line, every record carrying the
correlation identifier of the request that produced it. A client may supply
`X-Correlation-ID` so a trace spans more than this service; it is validated
before being echoed.

Ingestion writes one `ingestion_runs` row per execution with its counts, its
terminal state, and a bounded failure summary. That row is the answer to "did
last night's run finish", and its identifier is that run's correlation
identifier.

**The minimum an environment must collect:** stdout from every unit, and the
ability to query `ingestion_runs`. Anything beyond that is a choice this
document does not make.

## What is still open

- **Where this is hosted.** Nothing here needs a managed service beyond
  PostgreSQL and a container runtime. Five containers run long-term with the
  pipelines profile and three without it; **Sizing** says how large a host has
  to be for each.
- **Whether Airflow is worth its own instance** for two hourly DAGs. It earns
  its place when board discovery (#120) multiplies the sources; until then a
  cron entry calling the same function would do the same work. What it costs
  in the meantime is measured: 728 MiB resident and a third of a core,
  permanently, which is more than the API, the frontend and PostgreSQL
  together and is the whole difference between a 2 GB host and a 4 GB one.
- **Object storage for CVs**, which is a `CVStorage` implementation and a
  provider decision, not an architecture one.
- **TLS termination and the public hostname**, which belong to whatever fronts
  the frontend.
