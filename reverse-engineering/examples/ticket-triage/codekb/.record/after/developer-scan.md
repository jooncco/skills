## Developer Code Scan Results

Repo: `after` (project name `ticket-triage`, version 0.4.2)
Repo root: `<workspace>/examples/ticket-triage`
Commit: `36d341d` ("baseline", single-commit history)
Intent: `initial-onboarding` · Breadth: full rescan · Depth: Standard

### Scan Coverage

- **Analyzed deeply**:
  - `./` (repo root — the entire tree; 18 source/config files total, all read line by line)
  - `README.md`
  - `pyproject.toml`
  - `.gitlab-ci.yml`
  - `infra/docker-compose.yml`
  - `packages/triage_core/__init__.py`
  - `packages/triage_core/models.py`
  - `packages/triage_core/rules.py`
  - `packages/triage_core/engine.py`
  - `packages/triage_core/store.py`
  - `services/api/__init__.py`
  - `services/api/config.py`
  - `services/api/deps.py`
  - `services/api/main.py`
  - `services/api/queue.py`
  - `services/api/schemas.py`
  - `services/api/routes/__init__.py`
  - `services/api/routes/health.py`
  - `services/api/routes/tickets.py`
  - `services/worker/__init__.py`
  - `services/worker/main.py`
  - `services/worker/notifier.py`
  - `tests/test_engine.py`
  - `tests/test_rules.py`
- **Skimmed only**:
  - `codekb/` — pipeline working directory (`codekb/.record/after/attempt.json`), not application source; read for run metadata only.
  - `.git/` — not scanned beyond `git log`/`rev-parse`.

The repository is small enough that a full rescan reached every application file. No path outside the snapshot set (`./`) required deep reading.

### Packages Found

- `triage_core` (`packages/triage_core/`) — shared library — Python — domain models, static routing rules, the triage/classification engine, and SQLAlchemy persistence. Consumed by both services. No `packages/__init__.py`; resolved as an implicit namespace package from the repo root.
- `services.api` (`services/api/`) — FastAPI HTTP service — Python — ticket ingestion, triage lookup, synchronous reclassify, health/readiness probes, Redis queue producer, config, bearer auth dependency.
- `services.worker` (`services/worker/`) — long-running queue consumer — Python — pops queued tickets, classifies via `TriageEngine`, persists `TriageRow`, fans out notifications (Slack webhook / AWS SNS).
- `tests` (`tests/`) — pytest suite — Python — 3 tests, all against `triage_core` only.
- `infra` (`infra/`) — Docker Compose topology — YAML — api, worker, redis, postgres.

### Build System

- **Type**: PEP 621 `pyproject.toml` (pip-installable metadata only; no declared backend, no packaging/`[tool.setuptools]` section — the project is **not actually installable**, it runs from the repo root via `sys.path`). Docker Compose for local orchestration. GitLab CI for pipeline.
- **Config Files**: `pyproject.toml` (deps, ruff, pytest), `.gitlab-ci.yml`, `infra/docker-compose.yml`.
- **Build Dependencies**:
  - `services.api.routes.tickets` → `packages.triage_core` (`TriageEngine`, `Channel`, `Ticket`)
  - `services.api.routes.tickets` → `services.api.queue`, `services.api.deps`, `services.api.schemas`
  - `services.api.routes.health` → `services.api.queue`
  - `services.api.main` → `services.api.routes.{tickets,health}`
  - `services.api.queue` / `deps` → `services.api.config`
  - `services.worker.main` → `packages.triage_core` (engine, models, `store`), `services.api.queue`, `services.api.config`, `services.worker.notifier`
  - `packages.triage_core.engine` → `.models`, `.rules`; `packages.triage_core.store` → SQLAlchemy only
  - No circular imports detected. Notable one-way coupling: **the worker imports the API package** (`services.api.queue`, `services.api.config`) rather than a neutral shared module.

### APIs Discovered

- **REST (FastAPI)** — `services/api/routes/tickets.py`, `services/api/routes/health.py` — 5 endpoints:
  - `POST /v1/tickets` → 202, `TicketOut`. Auth: `require_token`. Mints a `uuid4().hex` id, pushes `{ticket_id, tenant_id, subject, body, channel, locale}` to Redis, returns immediately. **Does not persist the ticket anywhere.**
  - `GET /v1/tickets/{ticket_id}/triage` → `TriageOut`, 404 "triage result not ready". Auth: `require_token`. Reads the in-process `_seen` dict.
  - `POST /v1/tickets/{ticket_id}/reclassify` → `TriageOut`. Auth: `require_token`. Runs `TriageEngine.classify` synchronously in the request path and writes `_seen[ticket_id]`.
  - `GET /healthz` → `{"status": "ok"}`. Unauthenticated.
  - `GET /readyz` → `{"status": "ok", "queue_depth": <llen>}`. Unauthenticated; hits Redis on every call and will raise (500) if Redis is unreachable — it never actually reports "not ready".
- **Internal queue contract (untyped)** — `services/api/queue.py` ↔ `services/worker/main.py` — Redis list `triage:pending`, JSON payloads, `lpush`/`brpop` (FIFO). 3 functions: `push`, `pop`, `depth`. The payload shape is an implicit contract with no schema on either side; the worker uses `item["ticket_id"|"tenant_id"|"subject"|"body"]` directly and would `KeyError` on a malformed message.
- **Outbound integrations** — `services/worker/notifier.py` — AWS SNS `publish` (boto3) and a Slack incoming webhook (`httpx.post`, 10s timeout).
- **Outbound LLM (optional, unwired)** — `packages/triage_core/engine.py` `self._llm.classify(text)`. `TriageEngine` is constructed with `llm_client=None` at every call site, so this fallback is currently dead. `settings.llm_endpoint` exists but is read by nobody.
- **Persistence schema** — `packages/triage_core/store.py` — tables `tickets` (`TicketRow`) and `triage_results` (`TriageRow`); created via `Base.metadata.create_all` at worker startup. **`TicketRow` is never written or read by any code** — the `tickets` table is dead schema.

### Frameworks & Libraries

- `fastapi` — 0.111.0 — HTTP framework, routing, DI, OpenAPI.
- `uvicorn[standard]` — 0.30.1 — ASGI server (`uvicorn services.api.main:app --port 8080`).
- `pydantic` — 2.7.1 — request/response schemas (`services/api/schemas.py`).
- `sqlalchemy` — 2.0.30 — ORM, declarative models, `create_engine`/`sessionmaker` (`store.py`).
- `redis` — 5.0.4 — queue client (`services/api/queue.py`).
- `httpx` — 0.27.0 — Slack webhook POST (`notifier.py`) — only usage.
- `boto3` — 1.34.100 — AWS SNS publish (`notifier.py`) — only usage.
- `pytest` — 8.2.0 (dev) — test runner.
- `pytest-asyncio` — 0.23.6 (dev) — declared but **unused**; no async tests exist.
- `ruff` — 0.4.4 (dev) — lint, `line-length = 120`, `target-version = "py311"`.
- Runtime: Python `>=3.11` (uses `enum.StrEnum` and `dataclass(slots=True)`, both 3.11+).
- Images: `redis:7-alpine`, `postgres:16-alpine`; DB driver implied by `postgresql+psycopg://` (psycopg 3) — **not in `dependencies`**.

### Test Coverage

- **Test Directories**: `tests/` (`testpaths = ["tests"]`).
- **Test Frameworks**: pytest (+ pytest-asyncio, unused).
- **Coverage Config**: absent — no `pytest-cov`, no `.coveragerc`, no `[tool.coverage]`. The CI coverage gate is explicitly disabled (`.gitlab-ci.yml:12`).
- **Actual coverage**: 3 tests, all in `packages/triage_core` (2 engine, 1 rules consistency). **Zero tests** for `services/api` (routes, auth, schemas, queue) and **zero** for `services/worker` (consumer loop, persistence, notifier). No fixtures, no factories, no conftest.py, no HTTP client tests (`fastapi.testclient` never imported), no Redis/DB test doubles.

### Code Quality Indicators

- **Linting**: ruff, configured in `pyproject.toml` (`[tool.ruff]`). CI runs `ruff check services packages` — **`tests/` is not linted**. No rule selection configured, so ruff runs its default (E/F) rule set only; no import sorting, no type checking (no mypy/pyright anywhere).
- **CI/CD**: `.gitlab-ci.yml`, stages `lint → test → build`. The `build` stage (`main` only) runs `docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .` — **there is no Dockerfile in the repo**, so this stage cannot succeed. `infra/docker-compose.yml` has the same problem (`build: .` for both `api` and `worker`). No deploy stage, no image push, no environment definitions.
- **Documentation**: `README.md` is 5 lines — purpose plus one local-run command. No architecture notes, no env-var reference, no worker run instructions (the compose file's `python -m services.worker.main` is the only record), no API docs beyond generated OpenAPI, no CONTRIBUTING, no ADRs. Module docstrings are present and genuinely useful on `engine.py`, `models.py`, `rules.py`, `store.py`, `queue.py`, `notifier.py`, `worker/main.py`; function-level docstrings are sparse. No type-checked public API surface, though annotations are consistently applied.
- **Naming clarity**: good. **Function size**: good (largest is `worker.run`, ~30 lines). **Error handling**: poor (see debt). **Test presence**: poor. **Duplication**: fair — `Ticket` construction is duplicated between `routes/tickets.py:34-42` and `worker/main.py:36-43`; the `TriageResult → TriageOut` mapping is duplicated in the same two places; version `0.4.2` is hard-coded in both `pyproject.toml` and `services/api/main.py:5`. **Dead code**: `TicketRow`, `settings.llm_endpoint`, the `Notifier` SNS branch (worker never passes `topic_arn`), the entire `_llm` fallback, `pytest-asyncio`.

### Technical Debt Signals

Ordered by severity.

1. **Read path is disconnected from the write path (correctness bug, highest impact).** `POST /v1/tickets` queues; the worker classifies and writes `TriageRow` to Postgres (`services/worker/main.py:45-55`). But `GET /v1/tickets/{id}/triage` reads only the in-process dict `_seen` (`services/api/routes/tickets.py:15,27-29`), which is populated *exclusively* by `POST .../reclassify` (line 51). Nothing ever reads `TriageRow`. Net effect: **a normally-ingested ticket's triage result is never retrievable over the API — the GET returns 404 forever.** The only way to get a 200 is to call `reclassify` first, which recomputes triage synchronously in the request and bypasses the worker entirely. This makes the documented async pipeline effectively non-functional end to end.
2. **No Dockerfile.** `.gitlab-ci.yml:19` and `infra/docker-compose.yml` (`build: .`, twice) both reference an image build that cannot run. The build stage and local compose are both broken.
3. **In-memory state in a multi-process service.** `_seen` (`routes/tickets.py:15`, marked `FIXME: in-memory, lost on restart`) is per-worker-process. Under any multi-worker uvicorn/gunicorn deployment it is also per-process inconsistent, so even the reclassify path returns 404 non-deterministically depending on which worker serves the GET.
4. **Ticket bodies are never persisted.** `POST /v1/tickets` pushes to Redis and returns; the worker drops the ticket after classifying. `TicketRow` exists but is never instantiated. A Redis flush or crash between push and pop loses the ticket with no audit trail, and there is no dead-letter handling — `brpop` removes the item before any processing succeeds.
5. **Auth is a single static shared token with no tenant scoping.** `services/api/deps.py:7` (self-documented `NOTE`). `settings.api_token` defaults to the literal `"dev-token"` (`config.py:10`), so a deployment that forgets `API_TOKEN` silently runs with a publicly known credential. No route compares `payload.tenant_id` to anything, so **any token holder can read or reclassify any tenant's ticket** — `GET /{ticket_id}/triage` and `POST /{ticket_id}/reclassify` do no ownership check at all.
6. **Unbounded LLM call.** `engine.py:52-53` (`FIXME: unbounded call, no timeout and no retry budget`). Currently dormant (no client is ever injected) but it sits on the synchronous request path via `reclassify`.
7. **Blocking I/O in the consumer loop.** `notifier.py:22` (self-documented `NOTE`) — `httpx.post` with a 10s timeout runs inline in the worker's while loop, so a slow Slack endpoint stalls the whole queue. No retry, no backoff, no circuit breaker.
8. **No error handling anywhere on the worker loop.** `services/worker/main.py:32-56` — a malformed queue payload (`KeyError`), an invalid `Channel` value (`ValueError`), a DB error, or a notifier exception all propagate out of `run()` and kill the worker process. The `_running`/SIGTERM shutdown is likewise cosmetic: `queue.pop()` blocks up to 5s on `brpop` and the flag is only checked between iterations, and SIGINT is not handled.
9. **Module-level side effects at import.** `notifier.py:10` calls `boto3.client("sns")` at import time (fails without region/credentials even when SNS is unused); `queue.py:8` builds a Redis client at import; `config.py:7-11` reads env vars as dataclass *default values*, which are evaluated once at class-definition time — so `Settings` is effectively a frozen import-time singleton and cannot be overridden in tests without reimporting the module. This is the main reason the services are untestable.
10. **No database migrations.** Schema is created by `Base.metadata.create_all` at worker startup (`store.py:31`). No Alembic, so no path to evolve the schema against an existing Postgres. There is also a default/prod mismatch: `config.py:7` defaults to SQLite while compose supplies `postgresql+psycopg://`, and the psycopg driver is not a declared dependency.
11. **Quality gates weakened.** `.gitlab-ci.yml:12` — coverage gate disabled "since 2025-11 incident, re-enable later" with no tracking issue. `tests/` is excluded from lint. No type checker. No pre-commit config.
12. **Business rules edited without review.** `packages/triage_core/rules.py:1` — docstring states "Owned by the CX ops team, edited without review." Keyword lists, escalation tenants (`{"acme-corp","globex","initech"}`), routing groups and priority floors are hard-coded constants requiring a code deploy to change, yet are explicitly outside code review. `test_rules.py` checks only that every category has a group; nothing validates `PRIORITY_FLOOR` keys or `GROUP_BY_CATEGORY`'s reverse direction.
13. **Classification is first-match-wins over an unordered-by-intent dict.** `engine.py:48-50` iterates `CATEGORY_KEYWORDS` in insertion order, so a ticket matching both "refund" and "down" is always `billing`. Silent, untested precedence. Sentiment is a naive regex count (`engine.py:22-23,56-60`) hard-coded for English + Korean only, while `locale` defaults to `ko-KR` and multilingual support is a stated upcoming feature (`engine.py:3-5`).
14. **`TriageEngine` is a god object.** `engine.py:1-6` `TODO(2025-08)` — classification, sentiment, priority and routing all in one class, flagged as a blocker for the planned multilingual path.
15. **Unbounded input.** `TicketIn.body` (`schemas.py:9`) has no `max_length` while `subject` and `tenant_id` do; the engine truncates at 4000 chars but the full body still transits the queue and the DB (`Text` column). `channel` is a bare `str` in the schema and is only converted to the `Channel` enum later (`routes/tickets.py:39`, `worker/main.py:41`), where an invalid value raises an unhandled `ValueError` — a 500 on the API, a crash in the worker.
16. **Single-commit history.** `git log` shows only `36d341d baseline`, so there is no change history to learn intent from — the code comments are the only archaeology available.

## Handoff Summary

- **Intent-relevant finding**: For a new engineer onboarding, the single most important fact is that **the service's advertised async flow does not complete**. `POST /v1/tickets` (`services/api/routes/tickets.py:18-22`) → Redis → worker (`services/worker/main.py:44-55`) writes `TriageRow` to Postgres, but the only read endpoint, `GET /v1/tickets/{ticket_id}/triage` (`routes/tickets.py:25-29`), consults the process-local `_seen` dict (`routes/tickets.py:15`) that is written *only* by `POST .../reclassify` (`routes/tickets.py:51`). No code path ever queries `TriageRow`. A newcomer reading the README ("tickets arrive over HTTP, are queued, and a worker classifies them") will assume the loop closes; it does not. Wiring the GET to `store.TriageRow` — and deciding whether `_seen`/`reclassify` survives that change — is the first architectural decision this codebase forces, and it touches the API, the store, and the worker at once.
- **Risks / follow-up**:
  - **Scope**: full rescan completed within the snapshot path set (`./`). Every application file was read deeply; nothing outside the snapshot needed reading, so no re-snapshot is required. The scope block may legitimately claim `kind: full` with `analyzed.paths: ["./"]`.
  - **Deployment is broken as committed**: no Dockerfile exists, yet CI's build stage and both compose services build from `.`. Do not describe the container workflow as functional in the artifacts.
  - **Security items to carry forward verbatim**: static shared bearer token with a `"dev-token"` fallback default (`config.py:10`, `deps.py:6-13`), and complete absence of tenant-ownership checks on `/{ticket_id}/triage` and `/{ticket_id}/reclassify` — cross-tenant data exposure to any token holder.
  - **Dead surfaces that should not be documented as live capabilities**: the `tickets` table / `TicketRow`, the SNS notification branch (`topic_arn` is never supplied by the worker), the LLM classification fallback and `settings.llm_endpoint` (no client is ever injected), and `pytest-asyncio`.
  - **Layering violation to preserve**: `services/worker/main.py:12-13` imports `services.api.queue` and `services.api.config`, making the worker depend on the API service rather than on shared infrastructure. Any component inventory must show this edge; it is the main obstacle to deploying the two services independently.
  - **Undeclared runtime dependency**: compose uses `postgresql+psycopg://` but psycopg is absent from `pyproject.toml` dependencies; the worker cannot connect to the compose database as configured.
  - **Testability blocker**: import-time side effects (`boto3.client` at `notifier.py:10`, Redis client at `queue.py:8`, env-as-dataclass-defaults at `config.py:7-11`) mean the API and worker modules cannot be imported in a test without live infrastructure. This, not developer neglect, is the structural reason service-layer coverage is zero — record it as a prerequisite for any testing recommendation.
  - Version `0.4.2` is duplicated between `pyproject.toml` and `services/api/main.py:5` and will drift.
