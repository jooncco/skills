# Code Quality Assessment

## Test Coverage

| Aspect | State |
|---|---|
| Test directories | `tests/` — `testpaths = ["tests"]` (`pyproject.toml:22-23`) |
| Frameworks | pytest `8.2.0`; `pytest-asyncio 0.23.6` declared but **unused** |
| Coverage configuration | **Absent** — no `pytest-cov`, no `.coveragerc`, no `[tool.coverage]` |
| Test count | **3** (`test_engine.py`: 2, `test_rules.py`: 1) |
| Fixtures / conftest / factories | none (`test_engine.py:7-15` has one local helper) |
| HTTP / integration tests | none — `fastapi.testclient` is never imported |
| Test doubles for Redis / DB / Slack | none |

### What is tested

- `test_outage_keyword_sets_high_priority` (`tests/test_engine.py:18-21`) —
  keyword → category and the priority floor.
- `test_unknown_category_falls_back_to_tier1` (`tests/test_engine.py:24-26`) —
  the routing default.
- `test_every_category_has_a_group` (`tests/test_rules.py:4-6`) — one direction
  of the rules mapping.

### Alignment with architectural risk — poor

Coverage sits exactly where risk does not.

| Component | Health (see `component-inventory.md`) | Tests |
|---|---|---|
| `triage_core` | at-risk | 3 |
| `services.api` | **degraded** | **0** |
| `services.worker` | **degraded** | **0** |

Specifically untested: the auth dependency (`deps.py`), every route, the
Pydantic schemas, the Redis queue contract, the worker consume loop, persistence,
and the notifier. **No existing test would fail if the read-path defect (D1
below) were fixed or made worse** — the defect lives entirely in untested code.
Untested precedence semantics also hide in `engine.py:48-50`: a ticket matching
both `"refund"` and `"down"` is always `billing`, and nothing asserts that.
`test_rules.py` checks only that every keyword category has a group; it never
validates `PRIORITY_FLOOR` keys or that every `GROUP_BY_CATEGORY` entry is
reachable.

**The root cause is structural, not neglect.** `services/api/queue.py:8`
constructs a Redis client at import, `services/worker/notifier.py:10` calls
`boto3.client("sns")` at import, and `services/api/config.py:7-11` reads
environment variables as dataclass *default values* (evaluated once at
class-definition time). Importing either service in a test therefore requires
live infrastructure and AWS credentials, and settings cannot be overridden
without reimporting the module. Dependency inversion is a **prerequisite** for
any service-layer testing recommendation, not a follow-up to it.

## Linting & Static Analysis

| Tool | State |
|---|---|
| **ruff** `0.4.4` | Configured at `pyproject.toml:18-20` — `line-length = 120`, `target-version = "py311"`. **No `select`/`ignore`**, so only the default `E4/E7/E9` + `F` rules run: no import sorting (`I`), no bugbear (`B`), no security (`S`), no pyupgrade (`UP`). |
| CI invocation | `.gitlab-ci.yml:6` — `ruff check services packages`. **`tests/` is not linted.** |
| Formatter | none configured (`ruff format` is never invoked) |
| Type checker | **none** — no mypy, pyright, or pyre, despite thorough annotations throughout. `Settings`, `TriageEngine.__init__(llm_client=None)` (untyped parameter), and the untyped queue dicts would all benefit. |
| Security / SCA | none — no `bandit`, `pip-audit`, Dependabot, or Renovate config |
| Suppressions | **none found** — no `# noqa`, `# type: ignore`, or `# pragma: no cover` anywhere. The clean lint result reflects a narrow rule set, not verified quality. |
| pre-commit | none |

## CI/CD

`.gitlab-ci.yml` — three stages, 18 lines.

| Stage | Script | Assessment |
|---|---|---|
| `lint` | `ruff check services packages` | Runs; excludes `tests/`; default rule set only. |
| `test` | `pytest -q` | Runs 3 tests. Line 12: `# NOTE: coverage gate disabled since 2025-11 incident, re-enable later` — **the quality gate is explicitly off, with no tracking issue, owner, or date**. |
| `build` | `docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .` (`only: [main]`) | **Cannot succeed — there is no Dockerfile in the repository.** |

Gaps: no image `docker push`, no deploy stage, no environments, no artifact or
cache configuration, no `image:`/`services:` declarations (so the jobs assume a
runner that already has Python, ruff, pytest and Docker), no dependency
installation step at all, no branch protection or MR pipeline rules, no
scheduled/security pipeline.

`infra/docker-compose.yml` shares the missing-Dockerfile problem (`build: .` at
lines 3 and 9) and adds its own: the `db` service declares no
`POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` although the API is given
`postgresql+psycopg://triage:triage@db:5432/triage`; the `worker` service gets
**no environment at all**, so it silently falls back to
`redis://localhost:6379/0` and `sqlite:///./triage.db` (`config.py:7-8`) and
would not even share a queue with the API; there are no `depends_on`, no
healthchecks, and no volumes.

**Deployment is broken as committed. Do not treat the container workflow as
functional.**

## Documentation Quality

| Artefact | State |
|---|---|
| `README.md` | **5 lines** — a two-sentence purpose statement and one `uvicorn` command. No prerequisites, no env-var reference, no worker run instructions (the compose file's `python -m services.worker.main` is the only record), no architecture notes, no troubleshooting. Critically, it describes the pipeline as if it worked end to end. |
| API docs | Auto-generated OpenAPI only (`/docs`, `/openapi.json`); no committed spec, no examples, no error-response documentation. |
| ADRs / design docs | none |
| CONTRIBUTING / onboarding | none |
| Env-var reference | none — the authoritative list exists only in `config.py:7-11` plus `SLACK_WEBHOOK` read directly at `worker/main.py:30` |
| Module docstrings | **Present and genuinely useful** on `models.py`, `rules.py`, `engine.py`, `store.py`, `queue.py`, `notifier.py`, `worker/main.py`. Several are the only written record of a known defect (`rules.py:1`, `engine.py:1-6`, `deps.py:7`, `notifier.py:22`). |
| Function docstrings | Sparse — only `TriageEngine` (`engine.py:27`) and `require_token` (`deps.py:7`). |
| Inline comments | 4 debt markers in ~495 lines; each marks a real problem. |
| Change history | **Single commit** (`36d341d "baseline"`). There is no history to recover intent from — the docstrings and markers are the only archaeology available. |

Net: docstrings punch above their weight and are honest about problems;
everything above module level is missing.

## Technical Debt

Ordered by severity. Locations are `path:line`.

### D1 — The read path is disconnected from the write path *(correctness, critical)*

`POST /v1/tickets` queues (`routes/tickets.py:18-22`); the worker classifies and
writes `TriageRow` (`worker/main.py:44-55`). But
`GET /v1/tickets/{id}/triage` reads only the in-process dict `_seen`
(`routes/tickets.py:15,27-29`), which is populated **exclusively** by
`POST .../reclassify` (`routes/tickets.py:51`). **No code anywhere reads
`TriageRow`.** A normally-ingested ticket's triage result is therefore never
retrievable over the API — the GET returns 404 forever. The only way to get a
200 is to call `reclassify` first, which recomputes triage synchronously in the
request and bypasses the worker entirely. The system's advertised asynchronous
flow does not complete. Fixing it touches the API, the store, and the worker at
once, and forces a decision on whether `_seen`/`reclassify` survives.

### D2 — No Dockerfile *(deployment, critical)*

`.gitlab-ci.yml:19` and `infra/docker-compose.yml:3,9` all build from `.`; no
Dockerfile exists. The CI build stage and local compose are both unrunnable.

### D3 — In-memory state in a multi-process service *(correctness, high)*

`_seen` (`routes/tickets.py:15`, self-marked `FIXME: in-memory, lost on
restart`) is per-uvicorn-worker. Under any multi-worker deployment even the
reclassify path returns 404 non-deterministically depending on which process
serves the GET. Lost entirely on restart.

### D4 — Ticket content is never persisted *(data loss, high)*

`POST /v1/tickets` pushes to Redis and returns; the worker drops the ticket after
classifying. `TicketRow` (`store.py:10-17`) is never instantiated — the `tickets`
table is dead schema. `BRPOP` (`queue.py:16`) removes the message *before* any
processing succeeds, and there is no dead-letter list, so a crash or Redis flush
loses the ticket with no audit trail.

### D5 — Static shared token, no tenant scoping *(security, high)*

`deps.py:6-13` (self-documented `NOTE`) validates one shared bearer token whose
default is the literal `"dev-token"` (`config.py:10`) — a deployment that forgets
`API_TOKEN` runs on a publicly known credential. The comparison is not
constant-time. **No route compares `payload.tenant_id` to anything**, so any
token holder can read or reclassify any tenant's ticket
(`routes/tickets.py:25-29,32-52`). Cross-tenant data exposure.

### D6 — No error handling on the worker loop *(reliability, high)*

`worker/main.py:32-56` — a malformed payload (`KeyError`), an unknown channel
(`ValueError` at line 41), a DB error, or a notifier exception all propagate out
of `run()` and kill the process. Shutdown is cosmetic too: `queue.pop()` blocks
up to 5 s on `brpop` and `_running` is only checked between iterations; SIGINT is
not handled at all (`main.py:18-27`).

### D7 — Blocking I/O inside the consumer loop *(performance, medium-high)*

`notifier.py:21-23` (self-documented `NOTE`) — `httpx.post` with a 10 s timeout
runs inline in the worker's `while` loop, so a slow Slack endpoint stalls the
entire queue. No retry, no backoff, no circuit breaker.

### D8 — Import-time side effects *(testability, medium-high)*

`notifier.py:10` (`boto3.client("sns")` — fails without a region even though SNS
is unused), `queue.py:8` (Redis client), `config.py:7-11` (env read as dataclass
defaults, frozen at class-definition time). This is why service-layer coverage
is zero; see § Test Coverage.

### D9 — No database migrations *(operability, medium)*

Schema is created by `Base.metadata.create_all` inside `make_session_factory`
(`store.py:29-32`), invoked at worker startup. No Alembic, so no path to evolve
the schema against an existing database. Compounded by a default/prod mismatch:
`config.py:7` defaults to SQLite while compose supplies
`postgresql+psycopg://`, and psycopg is not a declared dependency.

### D10 — Unbounded LLM call *(reliability, medium — currently dormant)*

`engine.py:51-53`, self-marked `FIXME: unbounded call, no timeout and no retry
budget`. No client is ever injected today, but the call site sits on the
synchronous request path via `reclassify`, so wiring an LLM in would immediately
expose request threads to an unbounded external call.

### D11 — Quality gates weakened *(process, medium)*

`.gitlab-ci.yml:12` — coverage gate disabled "since 2025-11 incident, re-enable
later", no tracking issue. `tests/` excluded from lint (`.gitlab-ci.yml:6`). No
type checker, no formatter, no pre-commit, no SCA.

### D12 — Business rules edited without review *(governance, medium)*

`rules.py:1` — "Owned by the CX ops team, edited without review." Keyword lists,
escalation tenants (`{"acme-corp","globex","initech"}`), routing groups and
priority floors are hard-coded constants requiring a code deploy to change, yet
are explicitly outside code review — with only one weak test guarding them.

### D13 — Silent, untested classification precedence *(correctness, medium)*

`engine.py:48-50` iterates `CATEGORY_KEYWORDS` in dict insertion order, so a
ticket matching both `"refund"` and `"down"` is always `billing`, never
`outage` — a triage error on exactly the tickets that matter most. Sentiment is
a naive regex count hard-coded for English + Korean only
(`engine.py:22-23,56-60`) while `locale` defaults to `ko-KR` and multilingual
support is a stated upcoming feature.

### D14 — `TriageEngine` is a god object *(design, medium)*

`engine.py:1-6`, `TODO(2025-08)` — classification, sentiment, priority and
routing in one class, self-flagged as the blocker for the planned multilingual
path.

### D15 — Unbounded and under-validated input *(robustness, medium)*

`TicketIn.body` (`schemas.py:9`) has no `max_length` while `subject` and
`tenant_id` do; the engine truncates at 4000 chars but the full body still
transits the queue and the DB (`Text` column). `channel` is a bare `str` in the
schema and is only converted to the `Channel` enum later
(`routes/tickets.py:39`, `worker/main.py:41`), where an invalid value is an
unhandled `ValueError` — a 500 on the API, a process death in the worker.
`locale` is sent on the queue but never read by the consumer.

### D16 — Layering violation *(design, medium)*

`worker/main.py:12-13` imports `services.api.queue` and `services.api.config`,
making the consumer depend on the HTTP service package. The main obstacle to
deploying or scaling the two services independently.

### D17 — Duplication *(maintainability, low-medium)*

`Ticket` construction duplicated at `routes/tickets.py:34-42` and
`worker/main.py:36-43` (already divergent — the route passes `locale`, the worker
does not); the `TriageResult → TriageOut` mapping duplicated at
`routes/tickets.py:44-50` and, as a row build, `worker/main.py:46-53`; version
`0.4.2` hard-coded at both `pyproject.toml:3` and `main.py:5`.

### D18 — Dead code and unused surfaces *(clarity, low)*

`TicketRow` (`store.py:10-17`), `settings.llm_endpoint` (`config.py:11`), the
SNS branch (`notifier.py:19-20`), the whole `_llm` fallback (`engine.py:51-53`),
`pytest-asyncio`, and every module-level `log` object (declared in `engine.py`,
`notifier.py`, `worker/main.py` — **never called**, so the system emits no
application logs whatsoever).

### D19 — Not installable / single-commit history *(process, low)*

`pyproject.toml` has no `[build-system]` and no packaging section, so the project
runs only from the repo root via `sys.path`. `git log` shows one commit
(`36d341d baseline`), leaving no change history to learn intent from.

### Debt summary

| Severity | Items |
|---|---|
| Critical | D1 (broken read path), D2 (no Dockerfile) |
| High | D3, D4, D5, D6 |
| Medium | D7-D16 |
| Low | D17, D18, D19 |

**Marker density**: 4 explicit `TODO`/`FIXME`/`NOTE` markers in ~495 lines. The
codebase is honest — it names its own god object, its in-memory cache, its
unbounded call, its blocking notifier, its unreviewed rules, and its disabled
coverage gate. What the markers do *not* name is D1, the defect that actually
breaks the product.
