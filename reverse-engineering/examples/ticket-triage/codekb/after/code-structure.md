# Code Structure

## Package & Module Organization

```
after/                                  repo root (also the Python import root)
├── README.md                           5 lines of prose + one run command
├── pyproject.toml                      PEP 621 metadata, ruff + pytest config
├── .gitlab-ci.yml                      lint → test → build
├── infra/
│   └── docker-compose.yml              api, worker, redis, db
├── packages/                           (no __init__.py — implicit namespace pkg)
│   └── triage_core/                    shared domain library
│       ├── __init__.py                 public re-exports
│       ├── models.py                   Ticket, TriageResult, Priority, Channel
│       ├── rules.py                    static routing/keyword constants
│       ├── engine.py                   TriageEngine (classification + routing)
│       └── store.py                    SQLAlchemy rows + session factory
├── services/
│   ├── api/                            FastAPI HTTP service
│   │   ├── __init__.py                 (empty)
│   │   ├── main.py                     FastAPI app + router registration
│   │   ├── config.py                   Settings dataclass + module singleton
│   │   ├── deps.py                     require_token bearer dependency
│   │   ├── queue.py                    Redis push/pop/depth
│   │   ├── schemas.py                  Pydantic TicketIn/TicketOut/TriageOut
│   │   └── routes/
│   │       ├── __init__.py             (empty)
│   │       ├── health.py               /healthz, /readyz
│   │       └── tickets.py              /v1/tickets ...
│   └── worker/                         queue consumer process
│       ├── __init__.py                 (empty)
│       ├── main.py                     run() loop + SIGTERM handler
│       └── notifier.py                 Slack webhook / AWS SNS fan-out
└── tests/                              pytest suite (triage_core only)
    ├── test_engine.py
    └── test_rules.py
```

Ownership:

| Package | Owns |
|---|---|
| `packages/triage_core` | The domain: what a ticket is, how it is classified, how results are stored. No HTTP, no queue, no config. |
| `services/api` | HTTP surface, request/response DTOs, auth, the Redis client, and application configuration. |
| `services/worker` | The consume-classify-persist-notify loop and outbound notification adapters. |
| `tests` | Unit tests for `triage_core` only. |
| `infra` | Local container topology. |

**Import root.** There is no `packages/__init__.py` and no
`[tool.setuptools]`/build-backend section in `pyproject.toml`, so the project is
not actually installable; `packages` resolves as an implicit namespace package
and both `packages.*` and `services.*` imports only work when the process is
started from the repository root (as `uvicorn services.api.main:app` and
`python -m services.worker.main` both are).

## File Classification

18 application/config files, ~495 lines total.

| Classification | Count | Representative paths |
|---|---|---|
| **Domain model** | 1 | `packages/triage_core/models.py` (`Ticket`, `TriageResult`, `Priority`, `Channel`) |
| **Business rules / constants** | 1 | `packages/triage_core/rules.py` |
| **Service (domain logic)** | 1 | `packages/triage_core/engine.py` (`TriageEngine`) |
| **Repository / persistence** | 1 | `packages/triage_core/store.py` (`TicketRow`, `TriageRow`, `make_session_factory`) |
| **Controller / route** | 2 | `services/api/routes/tickets.py`, `services/api/routes/health.py` |
| **DTO / schema** | 1 | `services/api/schemas.py` |
| **Middleware / dependency** | 1 | `services/api/deps.py` (`require_token`) |
| **Infrastructure client** | 2 | `services/api/queue.py` (Redis), `services/worker/notifier.py` (Slack/SNS) |
| **Configuration (code)** | 1 | `services/api/config.py` |
| **Application entrypoint** | 2 | `services/api/main.py`, `services/worker/main.py` |
| **Package init / re-export** | 4 | `packages/triage_core/__init__.py` (re-exports); `services/api/__init__.py`, `services/api/routes/__init__.py`, `services/worker/__init__.py` (all empty) |
| **Test** | 2 | `tests/test_engine.py`, `tests/test_rules.py` |
| **Build / CI / infra config** | 3 | `pyproject.toml`, `.gitlab-ci.yml`, `infra/docker-compose.yml` |
| **Documentation** | 1 | `README.md` |
| **Migration** | 0 | *none — schema is created by `Base.metadata.create_all`* |
| **Static assets** | 0 | none |

Largest files: `services/worker/main.py` (61 lines), `packages/triage_core/engine.py` (68),
`services/api/routes/tickets.py` (52). Largest function: `worker.run()` (~30 lines).

## Code Patterns & Conventions

### Conventions actually followed

- **`from __future__ import annotations`** at the top of every non-trivial
  module (`models.py`, `engine.py`, `store.py`, `worker/main.py`,
  `notifier.py`).
- **Type annotations everywhere** on function signatures and dataclass fields —
  but no type checker is configured to enforce them (no mypy/pyright).
- **`@dataclass(slots=True)`** for domain entities (`models.py:23,35`);
  `@dataclass(frozen=True)` for settings (`config.py:5`). Python ≥3.11 only.
- **`enum.StrEnum` / `enum.IntEnum`** for closed vocabularies (`models.py:9,16`).
- **Module-level `log = logging.getLogger(__name__)`** in `engine.py`,
  `notifier.py`, and `logging.getLogger("worker")` in `worker/main.py` — though
  **none of these loggers is ever actually called**.
- **FastAPI idiom**: `APIRouter` per concern with a `prefix`/`tags`, routers
  included in `main.py`, auth via `Depends(require_token)`, response shapes via
  `response_model=`.
- **Explicit relative imports inside a package** (`from .models import ...`,
  `from .. import queue`) and absolute imports across packages.
- **Docstrings on modules** are present and genuinely informative — several
  (`rules.py:1`, `engine.py:1-6`, `deps.py:7`, `notifier.py:22`) are the primary
  record of known problems. Function-level docstrings are sparse.
- **Self-documenting debt markers**: `TODO(2025-08)` (`engine.py:3`),
  `FIXME` (`engine.py:52`, `routes/tickets.py:15`), `NOTE`
  (`deps.py:7`, `notifier.py:22`, `.gitlab-ci.yml:12`). Four markers in ~495
  lines — low density, high signal; each one marks a real defect.

### Recurring anti-patterns

| Anti-pattern | Locations | Effect |
|---|---|---|
| **Import-time side effects** | `queue.py:8` (Redis client), `notifier.py:10` (`boto3.client("sns")`), `config.py:7-11` (env read as dataclass defaults) | Modules cannot be imported without live infrastructure/credentials; settings are frozen at class-definition time and cannot be overridden in tests. Root cause of zero service-layer coverage. |
| **Module-global mutable state** | `routes/tickets.py:15` (`_seen`), `worker/main.py:18` (`_running`) | Per-process, lost on restart, inconsistent across uvicorn workers. |
| **Duplicated mapping logic** | `Ticket` construction: `routes/tickets.py:34-42` vs `worker/main.py:36-43`; `TriageResult → TriageOut`: `routes/tickets.py:44-50` vs the row build at `worker/main.py:46-53` | Two places to change for any model change; already subtly divergent (the route passes `locale`, the worker does not). |
| **Untyped dict as an inter-service contract** | `queue.push(dict)` / `queue.pop() -> dict` (`queue.py:11-17`), consumed by key access at `worker/main.py:37-41` | Schemaless wire format between two services that already share models. |
| **Missing error handling** | The entire `worker.run()` loop (`worker/main.py:32-56`); `Channel(...)` conversion at `routes/tickets.py:39` and `worker/main.py:41`; `queue.depth()` in `readyz` (`health.py:15`) | Unhandled `KeyError`/`ValueError`/connection errors become a 500 in the API and a process death in the worker. |
| **Hard-coded values** | Business constants in `rules.py`; version `"0.4.2"` in `main.py:5` duplicating `pyproject.toml:3`; `timeout=10` (`notifier.py:23`); `timeout: int = 5` (`queue.py:15`); `max_body_chars: int = 4000` (`engine.py:29`); default token `"dev-token"` (`config.py:10`) | Deploy required to change; the token default is a security default-open. |
| **Dead code** | `TicketRow` (`store.py:10-17`), the SNS branch (`notifier.py:19-20`), the LLM fallback (`engine.py:51-53`), `settings.llm_endpoint` (`config.py:11`), every `log` object, `pytest-asyncio` | Suggests capabilities that do not exist; misleads readers. |
| **Dict-insertion-order as business logic** | `engine.py:48-50` iterating `CATEGORY_KEYWORDS` | Precedence between categories is implicit in the literal's ordering and is untested. |
| **Cross-layer import** | `worker/main.py:12-13` importing `services.api.queue` / `services.api.config` | The consumer depends on the HTTP service package. |

### Naming

Consistent and clear: `snake_case` modules/functions, `PascalCase` classes,
leading-underscore for module-private (`_engine`, `_seen`, `_client`, `_sns`,
`_NEGATIVE`, `_running`, `_stop`) and for private methods (`_category`,
`_sentiment`, `_priority`). Domain terms in code match the business vocabulary
in `business-overview.md`. No naming defects observed.
