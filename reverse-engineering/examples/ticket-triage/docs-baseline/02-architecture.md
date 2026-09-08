# 02 — Architecture

## Shape

Two deployable processes sharing one code repository, one Redis instance, and one
SQL database. Both processes import the same domain library.

```
                    ┌──────────────────────────────────────────────┐
                    │            producers (email, chat,           │
                    │             phone, portal front-ends)        │
                    └───────────────────┬──────────────────────────┘
                                        │ HTTPS + Bearer token
                                        ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  API process   (uvicorn services.api.main:app, port 8080)      │
   │                                                                │
   │   routes/tickets.py ──► queue.push()                           │
   │   routes/tickets.py ──► TriageEngine (synchronous, reclassify) │
   │   routes/health.py  ──► queue.depth()                          │
   │   _seen  ← in-process dict, per-replica  ◀── see Finding Q-1   │
   └───────────────────────────────┬────────────────────────────────┘
                                   │ LPUSH  "triage:pending"
                                   ▼
                          ┌────────────────────┐
                          │   Redis  (list)    │
                          └─────────┬──────────┘
                                    │ BRPOP (5s timeout)
                                    ▼
   ┌────────────────────────────────────────────────────────────────┐
   │  Worker process   (python -m services.worker.main)             │
   │                                                                │
   │   queue.pop() ──► TriageEngine.classify() ──► session.merge()  │
   │                                          └──► Notifier.notify()│
   └──────────┬──────────────────────────────────────┬──────────────┘
              │ INSERT/UPDATE triage_results         │
              ▼                                      ▼
      ┌────────────────┐                  ┌──────────────────────┐
      │  PostgreSQL    │                  │ Slack webhook / SNS  │
      │  (or SQLite)   │                  └──────────────────────┘
      └────────────────┘
```

## The three layers

The repository has a deliberate three-layer split, and it is the best thing about
the design:

| Layer | Path | Depends on | Knows about |
|---|---|---|---|
| **Domain** | `packages/triage_core/` | nothing in `services/` | tickets, rules, persistence schema |
| **Delivery** | `services/api/` | `packages/triage_core` | HTTP, auth, Redis |
| **Processing** | `services/worker/` | `packages/triage_core`, `services/api` | Redis, DB, Slack/SNS |

The dependency arrows are clean in one direction (`services` → `packages`, never
the reverse) but there is **one leak**: the worker imports `services.api.queue`
and `services.api.config` (`services/worker/main.py:12-13`). The queue client and
settings are therefore owned by the API package but consumed by the worker, which
means the worker cannot be deployed or reasoned about without the API's module
tree. This is the seam to fix first if you ever split the repository — the queue
adapter and settings belong in `packages/`, not under `services/api/`.

## Request flow: submitting a ticket

1. `POST /v1/tickets` with a JSON body and `Authorization: Bearer <token>`.
2. `require_token` (`services/api/deps.py`) compares the token to the single
   `API_TOKEN` value. Not a match → 401 (missing prefix) or 403 (wrong token).
3. Pydantic validates `TicketIn`. Note `channel` and `locale` are validated only
   as strings, not against the enums.
4. `create_ticket` mints a `uuid4().hex` as `ticket_id` — the client cannot supply
   one, so **there is no idempotency key and no deduplication**. A retried POST
   creates a second ticket.
5. The payload plus the new id is JSON-serialised and `LPUSH`ed to the Redis list
   `triage:pending`.
6. `202 Accepted` is returned with `{ticket_id, accepted_at, queued: true}`.
   `queued` is hardcoded `true` — it is not evidence that the push succeeded, and
   if Redis is down the `LPUSH` raises and the client gets a 500 instead.

Nothing is written to the database on this path. **The ticket body exists only in
Redis** until the worker consumes it.

## Processing flow: the worker loop

`services/worker/main.py` is a single `while _running:` loop:

1. `queue.pop()` → `BRPOP` with a 5-second timeout. On timeout it returns `None`
   and the loop simply continues (a busy-ish poll, but bounded by the blocking
   read, so it is fine).
2. The dict is rehydrated into a `Ticket`. **`created_at` is set to "now"**, not
   to the original submission time — the ticket's real arrival time is lost.
   `locale` is dropped entirely on this path.
3. `TriageEngine.classify()` runs the rules described in
   [01 — Overview](01-overview.md#the-triage-rules).
4. The result is `session.merge()`d into `triage_results` and committed — an
   upsert keyed on `ticket_id`, so reprocessing the same ticket is idempotent at
   the DB level.
5. `Notifier.notify()` fires. See below.

### Failure semantics (important)

`BRPOP` **removes** the item from Redis before any processing happens. There is no
acknowledgement, no visibility timeout, no dead-letter queue, and no `try/except`
anywhere in the loop. Consequences:

- A malformed payload (missing `tenant_id`, unknown `channel` string) raises,
  the loop escapes, `run()` returns, the process exits — and **the ticket is
  gone**, along with the rest of the loop.
- A DB blip or a Slack timeout does the same thing: one bad ticket kills the
  worker and is silently lost.
- SIGTERM sets `_running = False`, but the flag is only checked at the top of the
  loop, so shutdown waits for the current `BRPOP` (up to 5s) plus the current
  ticket's DB write and HTTP notify. There is no SIGINT handler, so Ctrl-C in
  development kills it hard mid-ticket.

This is the single largest operational risk in the system. Tracked as
[Finding Q-3](08-code-quality.md#q-3-at-most-once-delivery-with-no-error-handling).

## The read path, and why it is broken

`GET /v1/tickets/{id}/triage` reads from `_seen`, a module-level `dict` inside the
API process (`services/api/routes/tickets.py:15`). The worker writes to
PostgreSQL. **Nothing connects the two.** The only writer of `_seen` is the
`reclassify` endpoint, in the same process.

So in practice:

- Submit a ticket → worker triages it → DB row appears → `GET .../triage` returns
  **404 forever**.
- Call `reclassify` → `_seen` is populated in *that one API replica* → `GET`
  works, but only if the load balancer routes you back to the same replica, and
  only until it restarts.

The `# FIXME: in-memory, lost on restart` comment acknowledges the restart
problem but understates it: the deeper issue is that the API never queries the
store at all. `packages/triage_core/store.py` is imported by the worker only.

## Configuration and deployment

`services/api/config.py` builds a frozen `Settings` dataclass whose defaults call
`os.getenv` **at class-definition time** — i.e. environment variables are read
once when the module is first imported, and the module-level `settings` singleton
is created immediately. Env changes after import have no effect, and tests cannot
override settings without reloading the module. Five knobs:

| Variable | Default | Used by |
|---|---|---|
| `DB_URL` | `sqlite:///./triage.db` | worker only |
| `REDIS_URL` | `redis://localhost:6379/0` | API + worker |
| `QUEUE_KEY` | `triage:pending` | API + worker |
| `API_TOKEN` | `dev-token` | API auth |
| `LLM_ENDPOINT` | `""` | **nothing — dead config** |

`SLACK_WEBHOOK` is read directly via `os.getenv` in `services/worker/main.py:30`,
bypassing `Settings` entirely. The SNS `topic_arn` has no configuration path at
all: `Notifier.__init__` accepts it, and the worker never passes it, so the SNS
branch is unreachable.

`infra/docker-compose.yml` declares four services (api, worker, redis, db) but is
**not currently runnable** — the `db` service sets no `POSTGRES_*` credentials, the
`worker` service gets no environment block (so it would connect to
`redis://localhost` inside its own container and write to SQLite), there are no
`depends_on` or volumes, and both `api` and `worker` `build: .` against a
Dockerfile that does not exist. Details in
[09 — Local Development](09-local-development.md).

## Scaling characteristics

- **API** is stateless *except* for `_seen`, which makes it accidentally sticky.
  Once the read path is fixed to query the DB, it scales horizontally freely.
- **Worker** scales horizontally on the Redis list — `BRPOP` distributes to one
  consumer each, so N workers is safe. Ordering is not preserved across workers,
  which does not matter here since triage is per-ticket independent.
- **Bottleneck** is the synchronous `httpx.post` to Slack inside the worker loop
  (10s timeout, no retry, flagged in a source comment). One slow Slack response
  stalls the entire consumer for up to 10 seconds per ticket.
- **Redis is a durability single point of failure.** Between the API's `LPUSH` and
  the worker's DB commit, the ticket exists only in a Redis list.
