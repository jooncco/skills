# 03 — Code Structure

## Repository layout

```
.
├── .gitlab-ci.yml            CI: lint → test → build (3 stages)
├── pyproject.toml            deps, ruff + pytest config. No [build-system].
├── README.md                 5 lines
├── docs/                     ← this documentation
├── infra/
│   └── docker-compose.yml    api, worker, redis, db
├── packages/
│   └── triage_core/          domain library — no I/O except the DB schema
│       ├── __init__.py       public surface: Ticket, TriageResult, Priority, TriageEngine
│       ├── models.py         dataclasses + enums (42 lines)
│       ├── rules.py          keyword tables + routing tables (24 lines)
│       ├── engine.py         classification / sentiment / priority (68 lines)
│       └── store.py          SQLAlchemy tables + session factory (32 lines)
├── services/
│   ├── api/                  FastAPI HTTP delivery layer
│   │   ├── main.py           app object, router registration (7 lines)
│   │   ├── config.py         env-backed Settings singleton (14 lines)
│   │   ├── deps.py           bearer-token dependency (13 lines)
│   │   ├── queue.py          Redis list adapter (21 lines)
│   │   ├── schemas.py        Pydantic request/response models (25 lines)
│   │   └── routes/
│   │       ├── tickets.py    POST /v1/tickets, GET/POST triage (52 lines)
│   │       └── health.py     /healthz, /readyz (15 lines)
│   └── worker/               queue consumer
│       ├── main.py           the consume loop (61 lines)
│       └── notifier.py       Slack webhook + SNS fan-out (23 lines)
└── tests/
    ├── test_engine.py        2 tests (26 lines)
    └── test_rules.py         1 test (6 lines)
```

**Total: 433 lines of Python across 19 files**, of which 32 lines / 3 tests are
test code. Nothing is generated; there are no migrations, no lockfile, no
Dockerfile, no `.env.example`, and no linter suppressions.

## Packaging — read this before you try to run anything

`pyproject.toml` has **no `[build-system]` table and no package discovery
configuration**. The project is therefore not installable (`pip install -e .`
will not produce a usable install), and every import of the form
`from packages.triage_core import ...` works only because the repository root
happens to be on `sys.path` — which is true when you run `uvicorn` or `pytest`
from the repo root, and false almost everywhere else.

Reinforcing this: `packages/` itself has **no `__init__.py`**. It resolves as a
PEP 420 implicit namespace package on Python 3.11, which is why it works at all.
`services/` likewise has no `__init__.py`, though `services/api`, `services/api/routes`
and `services/worker` each have (empty) ones.

The practical effect is that the repo root is an implicit, undeclared `PYTHONPATH`
entry. Any containerisation or `pip install` work has to address this first.

## Module map

### `packages/triage_core` — the domain

Pure logic plus the persistence schema. It has exactly one third-party dependency
(SQLAlchemy, and only in `store.py`); `models.py`, `rules.py` and `engine.py`
import nothing outside the standard library. That makes the engine trivially
testable, which the existing tests take advantage of.

- **`models.py`** — `Priority(IntEnum)`, `Channel(StrEnum)`, and two
  `@dataclass(slots=True)` records, `Ticket` and `TriageResult`. `slots=True` is a
  reasonable choice for high-volume records. `Ticket.attachments` is declared and
  never read by anything.
- **`rules.py`** — four module-level constants: `CATEGORY_KEYWORDS`,
  `ESCALATION_TENANTS`, `GROUP_BY_CATEGORY`, `PRIORITY_FLOOR`. Its docstring
  admits it is "edited without review". Changing key order here silently changes
  classification precedence.
- **`engine.py`** — `TriageEngine` with one public method, `classify()`, and three
  privates (`_category`, `_sentiment`, `_priority`). Carries a module-level
  `TODO(2025-08)` calling itself a god object; at 68 lines that is premature, but
  the direction of travel it warns about is real — this is where a multilingual
  path and an LLM path would both land.
- **`store.py`** — declarative `TicketRow` and `TriageRow` plus
  `make_session_factory(db_url)`, which calls `Base.metadata.create_all(engine)`.
  Schema is created implicitly at worker start-up; **there is no migration tool**,
  so any column change to an existing deployment must be applied by hand.
  `TicketRow` has no writer anywhere in the codebase.

### `services/api` — HTTP delivery

- **`main.py`** — constructs `FastAPI(title="ticket-triage", version="0.4.2")`
  (version duplicated from `pyproject.toml`, so it will drift) and includes the
  two routers. No middleware, no CORS, no exception handlers, no lifespan hooks.
- **`config.py`** — see [02 — Architecture](02-architecture.md#configuration-and-deployment).
  Frozen dataclass, env read at import time, module-level singleton.
- **`deps.py`** — one FastAPI dependency, `require_token`. Reads the raw
  `Authorization` header rather than using `HTTPBearer`, so the endpoints do not
  advertise auth in the OpenAPI schema. Uses `!=` for the token comparison, which
  is not constant-time.
- **`queue.py`** — thin Redis list wrapper: `push`, `pop`, `depth`. The client is
  constructed at **module import time** (`_client = redis.from_url(...)`), which
  couples importing this module to configuration being present. It is also the
  module the worker reaches into across the layer boundary.
- **`schemas.py`** — `TicketIn`, `TicketOut`, `TriageOut`. `TriageOut` exposes
  `priority` as a bare `int` rather than the enum, so API consumers must know the
  1–4 mapping out of band. `TriageResult.rationale` is not exposed at all.
- **`routes/tickets.py`** — the three business endpoints, plus two pieces of
  module-level mutable state: a shared `TriageEngine()` instance (stateless, so
  safe) and the `_seen` dict (not safe — see
  [Finding Q-1](08-code-quality.md#q-1-the-read-path-is-disconnected-from-the-write-path)).
- **`routes/health.py`** — `/healthz` returns a static OK; `/readyz` calls
  `queue.depth()`, so it genuinely probes Redis. `/readyz` has no `try/except`,
  so a Redis outage surfaces as a 500 rather than a structured not-ready response
  — arguably correct for a readiness probe, but it will also emit a stack trace
  per poll.

### `services/worker` — the consumer

- **`main.py`** — module-level `_running` flag, `_stop` SIGTERM handler, and
  `run()`. Constructs its own `TriageEngine`, session factory and `Notifier` on
  entry. No `try/except` in the loop; see the failure semantics in
  [02 — Architecture](02-architecture.md#failure-semantics-important).
- **`notifier.py`** — `Notifier` with a single `notify(result: dict)` method.
  Creates a module-level `boto3.client("sns")` **at import time**, which requires
  an AWS region to be resolvable in the environment or the import itself raises —
  even for deployments that never use SNS. The SNS message body is `str(result)`,
  i.e. a Python dict repr, not JSON.

### `tests`

Three tests, all against the pure domain layer:

- `test_engine.py::test_outage_keyword_sets_high_priority`
- `test_engine.py::test_unknown_category_falls_back_to_tier1`
- `test_rules.py::test_every_category_has_a_group`

There are **no tests for the API, the worker, the queue, the store, the notifier,
or auth**. `pytest-asyncio` is a declared dev dependency and is not used by any
test. See [08 — Code Quality](08-code-quality.md#testing).

## Conventions in use

Consistent enough to follow without thinking:

- `from __future__ import annotations` at the top of most modules; PEP 604 union
  syntax (`dict | None`) and PEP 585 builtin generics throughout.
- Module-level `log = logging.getLogger(__name__)` — declared in `engine.py` and
  `notifier.py`, and **never actually used to log anything**. There is not a
  single log statement in the codebase outside `logging.basicConfig`.
- Leading underscore for module-private names (`_engine`, `_seen`, `_client`,
  `_NEGATIVE`, `_running`).
- Relative imports within a service (`from .. import queue`), absolute imports
  across the layer boundary (`from packages.triage_core import ...`).
- Type hints on every function signature. Ruff at line-length 120, targeting
  py311.
