# Component Inventory

Five components, matching the deployable/importable units in the repository.
Health ratings: **healthy** (works as intended, low risk) / **at-risk**
(functional but carrying defects that will bite) / **degraded** (contains a
defect that already prevents intended behaviour).

## Components

### triage_core

- **Responsibility**: The domain. Defines what a ticket and a triage result are
  (`models.py`), holds the static business rules (`rules.py`), performs
  classification / sentiment scoring / priority assignment / routing
  (`engine.py`), and declares the relational persistence schema and session
  factory (`store.py`).
- **Location**: `packages/triage_core/` — `__init__.py`, `models.py`,
  `rules.py`, `engine.py`, `store.py` (~160 lines).
- **Depends on**: `sqlalchemy` (only in `store.py`); Python stdlib
  (`enum`, `dataclasses`, `datetime`, `re`, `logging`). No dependency on either
  service — the dependency direction here is correct.
- **Depended on by**: `services.api` (`routes/tickets.py:6-7`),
  `services.worker` (`main.py:9-11`), `tests` (both files).
- **Sub-parts**: `models.py` (healthy), `rules.py` (at-risk),
  `engine.py` (at-risk), `store.py` (degraded).
- **Health**: **at-risk**
- **Rationale**: `models.py` is clean and well-formed. Against that:
  `TriageEngine` is a self-declared god object (`engine.py:1-6`,
  `TODO(2025-08)`) whose category precedence is dict-insertion order
  (`engine.py:48-50`) and whose sentiment analysis is two hard-coded EN/KO
  regexes (`engine.py:22-23`) — while the default locale is `ko-KR` and
  multilingual support is the next planned feature. `rules.py` is business
  logic explicitly exempted from review (`rules.py:1`) that requires a deploy to
  change. `store.py` is the worst part: `TicketRow` is dead schema, `TriageRow`
  is write-only, schema creation happens as an import-time-adjacent side effect
  of `make_session_factory` (`store.py:31`), and there are no migrations. The
  engine is nonetheless the only unit-tested code in the repo.

### services.api

- **Responsibility**: The HTTP surface. Accepts and validates inbound tickets,
  authenticates callers, enqueues work, serves triage lookups, offers a
  synchronous reclassify operation, and exposes liveness/readiness probes. Also
  — incorrectly — owns the shared Redis client and the application-wide
  `Settings` object that the worker consumes.
- **Location**: `services/api/` — `main.py`, `config.py`, `deps.py`, `queue.py`,
  `schemas.py`, `routes/tickets.py`, `routes/health.py` (~130 lines).
- **Depends on**: `fastapi`, `pydantic`, `redis`, `uvicorn` (runtime host);
  `packages.triage_core` (`TriageEngine`, `Ticket`, `Channel`).
- **Depended on by**: `services.worker` (`main.py:12-13` imports
  `services.api.queue` and `services.api.config`) — **a layering violation**;
  external HTTP clients.
- **Health**: **degraded**
- **Rationale**: `GET /v1/tickets/{id}/triage` reads a process-local dict
  (`routes/tickets.py:15,27-29`) that the ingest pipeline never populates, so
  the endpoint returns 404 for every normally-ingested ticket and the service
  fails to deliver its primary read capability. Compounding: `_seen` is
  per-process, so even the reclassify path is non-deterministic under a
  multi-worker deploy; auth is a single static token defaulting to `"dev-token"`
  with **no tenant-ownership checks on any route** (`deps.py:6-13`); `readyz`
  can only 500, never report "not ready" (`health.py:13-15`); `TicketIn.body`
  is unbounded and `channel` is an unvalidated `str` that raises an unhandled
  `ValueError` → 500 at `routes/tickets.py:39`; and import-time construction of
  the Redis client (`queue.py:8`) plus env-as-dataclass-defaults
  (`config.py:7-11`) make the whole package unimportable in a test without live
  infrastructure. **Zero tests.**

### services.worker

- **Responsibility**: The consumer process. Blocks on the Redis queue, rebuilds
  a `Ticket`, classifies it via `TriageEngine`, upserts a `TriageRow`, and fans
  the result out to Slack (and, nominally, AWS SNS).
- **Location**: `services/worker/` — `main.py` (61 lines), `notifier.py` (23 lines).
- **Depends on**: `packages.triage_core` (engine, models, store),
  **`services.api.queue` and `services.api.config`**, `boto3`, `httpx`,
  `sqlalchemy` (transitively via `store`).
- **Depended on by**: nothing (it is a leaf process). Started by
  `python -m services.worker.main` (`infra/docker-compose.yml:10`).
- **Health**: **degraded**
- **Rationale**: The loop (`main.py:32-56`) has **no error handling at all** —
  a malformed payload (`KeyError`), an unknown channel (`ValueError`), a
  database error, or a Slack failure each propagates out of `run()` and kills
  the process, with no dead-letter and no re-queue (`BRPOP` already removed the
  message). Graceful shutdown is cosmetic: `_running` is only checked between
  iterations while `pop()` blocks up to 5 s, and SIGINT is not handled. The
  Slack POST is synchronous inside the loop with a 10 s timeout
  (`notifier.py:21-23`), so queue throughput is hostage to Slack latency; there
  is no retry or backoff. `notifier.py:10` calls `boto3.client("sns")` at import
  time, which fails without a region/credentials even though the SNS branch is
  unreachable (the worker never supplies `topic_arn`). The work it does persist
  is never read by anything. Its declared `postgresql+psycopg://` driver is not
  a declared dependency. **Zero tests.**

### tests

- **Responsibility**: Automated verification. Currently: two engine behaviour
  tests and one rules-consistency test.
- **Location**: `tests/` — `test_engine.py` (26 lines, 2 tests),
  `test_rules.py` (6 lines, 1 test). `testpaths = ["tests"]`
  (`pyproject.toml:22-23`).
- **Depends on**: `pytest`; `packages.triage_core` only.
- **Depended on by**: `.gitlab-ci.yml:8-11` (`pytest -q`).
- **Health**: **degraded**
- **Rationale**: 3 tests covering one of five components. Zero coverage of
  `services.api` (routes, auth, schemas, queue) and `services.worker` (loop,
  persistence, notifier) — i.e. **none of the code containing the known
  defects is tested**, and the read-path break would not be caught by any
  existing or straightforwardly-added test. No `conftest.py`, no fixtures or
  factories, no `fastapi.testclient` usage, no Redis/DB doubles. No coverage
  tooling is installed and the CI coverage gate is explicitly disabled
  (`.gitlab-ci.yml:12`). `tests/` is also excluded from linting
  (`.gitlab-ci.yml:6` lints only `services packages`). `pytest-asyncio` is
  declared but unused. `test_rules.py` checks only one direction (every keyword
  category has a group) and never validates `PRIORITY_FLOOR` keys or the reverse
  mapping.

### infra

- **Responsibility**: Local/CI deployment topology — the API, the worker, Redis,
  and PostgreSQL, plus the GitLab pipeline definition.
- **Location**: `infra/docker-compose.yml` (14 lines); `.gitlab-ci.yml` (18
  lines) is the associated CI definition.
- **Depends on**: a container image built from the repository root (`build: .`,
  twice), `redis:7-alpine`, `postgres:16-alpine`.
- **Depended on by**: developers running locally; the CI `build` stage.
- **Health**: **degraded**
- **Rationale**: **There is no Dockerfile in the repository.** Both compose
  services (`build: .` at lines 3 and 9) and the CI build stage
  (`.gitlab-ci.yml:19`, `docker build -t ... .`) therefore cannot succeed —
  deployment is broken as committed. Further: the `db` service sets no
  `POSTGRES_USER`/`PASSWORD`/`DB` yet the API is handed
  `postgresql+psycopg://triage:triage@db:5432/triage`, and the `psycopg` driver
  is not in `pyproject.toml` dependencies; the `worker` service receives no
  `REDIS_URL` or `DB_URL` at all, so it silently falls back to
  `redis://localhost:6379/0` and `sqlite:///./triage.db` (`config.py:7-8`) —
  meaning the worker and API would not even share a queue; no `depends_on`, no
  healthchecks, no volumes (Postgres and Redis data are ephemeral), no
  `SLACK_WEBHOOK` or `API_TOKEN` wiring. The CI pipeline has no deploy stage and
  no image push.

## Health Summary

| Component | Health | Main risk |
|---|---|---|
| `triage_core` | at-risk | God-object engine with implicit, untested category precedence and EN/KO-only sentiment; `store.py` holds dead (`TicketRow`) and write-only (`TriageRow`) schema with no migrations. |
| `services.api` | degraded | The triage read endpoint serves a process-local dict the pipeline never fills → 404 for every ingested ticket; static shared token with no tenant-ownership checks; untestable due to import-time infrastructure. |
| `services.worker` | degraded | No error handling anywhere in the loop — one bad message kills the process and loses the ticket; blocking Slack call throttles the queue; imports the API package. |
| `tests` | degraded | 3 tests, all on `triage_core`; nothing covers the two degraded services or any known defect; coverage gate disabled in CI. |
| `infra` | degraded | No Dockerfile exists, so compose and the CI build stage both cannot run; worker gets no `REDIS_URL`/`DB_URL`; undeclared `psycopg` driver. |

**No component is currently rated healthy.** The system-level risk concentrates
in one place: the API's read path (`services/api/routes/tickets.py:15,27-29`) is
not connected to the worker's write path (`services/worker/main.py:45-55`), so
the advertised asynchronous transaction does not complete end to end.
