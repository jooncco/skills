# Technology Stack

## Languages & Runtimes

| Language / runtime | Version | Where used | Evidence |
|---|---|---|---|
| Python | `>=3.11` (required), ruff targets `py311` | All application code (18 files, ~495 lines) | `pyproject.toml:4,20` |
| — 3.11-specific features | `enum.StrEnum`, `dataclass(slots=True)` | `packages/triage_core/models.py:16,23,35` | hard floor at 3.11; the project will not run on 3.10 |
| YAML | — | CI and container topology | `.gitlab-ci.yml`, `infra/docker-compose.yml` |
| TOML | — | Project metadata and tool config | `pyproject.toml` |
| SQL | — | Emitted by SQLAlchemy only; no hand-written SQL, no migration files | `packages/triage_core/store.py` |

No other language is present. No frontend, no client SDK, no scripts directory.

## Frameworks

| Framework | Version | Purpose | Where |
|---|---|---|---|
| **FastAPI** | `0.111.0` (pinned) | HTTP routing, dependency injection, request validation, automatic OpenAPI | `services/api/main.py`, `routes/*.py`, `deps.py` |
| **Pydantic** | `2.7.1` (pinned) | Request/response models (`TicketIn`, `TicketOut`, `TriageOut`) | `services/api/schemas.py` |
| **SQLAlchemy** | `2.0.30` (pinned) | ORM, declarative table definitions, engine + `sessionmaker`. Uses the legacy `declarative_base()` helper rather than 2.0's `DeclarativeBase`/`Mapped[]` typing | `packages/triage_core/store.py` |
| **Uvicorn** (`[standard]` extra) | `0.30.1` (pinned) | ASGI server; the documented run command is `uvicorn services.api.main:app --reload --port 8080` | `README.md:7`, `pyproject.toml:7` |
| **pytest** | `8.2.0` (dev, pinned) | Test runner; `testpaths = ["tests"]` | `pyproject.toml:16,22-23` |

## Libraries & Tooling

### Runtime libraries

| Library | Version | Purpose | Usage footprint |
|---|---|---|---|
| `redis` (redis-py) | `5.0.4` | Queue client — `from_url`, `lpush`, `brpop`, `llen` | `services/api/queue.py` (single module) |
| `httpx` | `0.27.0` | Slack incoming-webhook POST, 10 s timeout | `services/worker/notifier.py:23` — **only usage in the repo** |
| `boto3` | `1.34.100` | AWS SNS `publish` | `services/worker/notifier.py:10,20` — **only usage; the publish branch is unreachable** because the worker never supplies `topic_arn` |

Standard library in notable use: `dataclasses`, `enum`, `datetime`, `re`,
`uuid`, `json`, `os`, `logging`, `signal`.

### Development tooling

| Tool | Version | Configuration | Notes |
|---|---|---|---|
| **ruff** | `0.4.4` (dev) | `[tool.ruff]` in `pyproject.toml:18-20`: `line-length = 120`, `target-version = "py311"` | **No `select`/`lint.select`**, so only ruff's default `E4/E7/E9,F` rules run — no import sorting (`I`), no bugbear, no pyupgrade. CI lints `services packages` only, **excluding `tests/`** (`.gitlab-ci.yml:6`). |
| **pytest-asyncio** | `0.23.6` (dev) | none | **Declared but unused** — no async tests exist. |
| *(none)* | — | — | **No type checker** (no mypy, pyright, or pyre) despite pervasive annotations. **No coverage tool** (no `pytest-cov`, `.coveragerc`, or `[tool.coverage]`). **No formatter** configured (`ruff format` is not invoked). **No pre-commit** config. |

### Build & packaging

| Aspect | State |
|---|---|
| Metadata format | PEP 621 `[project]` table in `pyproject.toml` |
| Build backend | **Absent** — no `[build-system]` table, no `[tool.setuptools]`/`[tool.hatch]` section. The project therefore **cannot be `pip install`ed**; it runs from the repository root via `sys.path`, and `packages/` resolves as an implicit namespace package (there is no `packages/__init__.py`). |
| Dependency pinning | Every dependency is `==`-pinned; no lockfile (no `requirements.txt`, `poetry.lock`, `uv.lock`, or `pip-tools` output), so transitive dependencies are unpinned. |
| Package manager | Implied `pip`; not stated anywhere. |
| Version | `0.4.2`, duplicated at `pyproject.toml:3` and `services/api/main.py:5` — two sources of truth that will drift. |

### Infrastructure & platform

| Component | Version / image | Role | Evidence |
|---|---|---|---|
| Redis | `redis:7-alpine` | Pending-work queue (list `triage:pending`) | `infra/docker-compose.yml:11-12`, `config.py:9` |
| PostgreSQL | `postgres:16-alpine` | Triage-result store | `infra/docker-compose.yml:13-14` |
| SQLite | via `sqlite:///./triage.db` | **Default** `DB_URL` when the env var is unset (`config.py:7`) — a dev/prod database divergence |
| psycopg (v3) | **not declared** | Required by the compose `postgresql+psycopg://` URL but absent from `pyproject.toml` dependencies — the worker cannot connect to the compose database as configured | `infra/docker-compose.yml:7` vs `pyproject.toml:5-13` |
| Docker | — | `build: .` for `api` and `worker` | `infra/docker-compose.yml:3,9` — **no Dockerfile exists in the repository**, so neither service can be built |
| GitLab CI | — | `lint → test → build` stages | `.gitlab-ci.yml` — the `build` stage runs `docker build … .` and fails for the same reason |

### External services

| Service | Client | Status |
|---|---|---|
| Slack (incoming webhook) | `httpx` | Live, gated on the `SLACK_WEBHOOK` env var (`worker/main.py:30`) |
| AWS SNS | `boto3` | **Dormant** — client constructed at import (`notifier.py:10`) but `publish` is unreachable |
| LLM endpoint | none | **Unwired** — `settings.llm_endpoint` (`config.py:11`) is read by no code, and `TriageEngine` is always constructed with `llm_client=None` |

### Configuration surface (environment variables)

| Variable | Default | Consumed at |
|---|---|---|
| `DB_URL` | `sqlite:///./triage.db` | `config.py:7` → `worker/main.py:28` |
| `REDIS_URL` | `redis://localhost:6379/0` | `config.py:8` → `queue.py:8` |
| `QUEUE_KEY` | `triage:pending` | `config.py:9` → `queue.py:12,16,21` |
| `API_TOKEN` | `"dev-token"` (**insecure default**) | `config.py:10` → `deps.py:11` |
| `LLM_ENDPOINT` | `""` | `config.py:11` — **never read** |
| `SLACK_WEBHOOK` | `""` | `worker/main.py:30` (read directly via `os.getenv`, bypassing `Settings`) |

All `Settings` fields are evaluated **once at class-definition time**
(`config.py:5-11` uses `os.getenv(...)` as dataclass *defaults*), so the values
are frozen at import and cannot be changed by setting the environment later.
There is no `.env` support, no `pydantic-settings`, and no documented env-var
reference outside these files.
