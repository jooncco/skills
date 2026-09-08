# 01 — System Overview

## What the system is for

`ticket-triage` is a back-office service for a customer-support (CX) organisation.
Its job is to take an inbound support ticket and answer four questions
automatically, so a human does not have to:

| Question | Output field | Example |
|---|---|---|
| What is this about? | `category` | `billing`, `outage`, `how-to`, `feedback`, `unknown` |
| How urgent is it? | `priority` | `LOW` (1) … `URGENT` (4) |
| How angry is the customer? | `sentiment` | `-1.0` … `+1.0` |
| Who should handle it? | `assignee_group` | `cx-billing`, `sre-oncall`, `cx-tier1`, `product` |

The answer is produced by a deterministic keyword rule engine, not a model. There
is a hook for an LLM fallback, but it is not wired to anything (see
[Finding Q-6](08-code-quality.md#q-6-the-llm-fallback-is-dead-code)).

## Who uses it

There is no UI in this repository. The service is consumed machine-to-machine:

- **Upstream producers** — whatever fronts the customer (email gateway, chat
  widget, phone system, self-service portal) POSTs tickets to `/v1/tickets`. The
  `channel` field on the ticket records which of these it came from.
- **Downstream consumers** — the worker pushes a notification to a Slack webhook
  and/or an AWS SNS topic when a triage verdict is ready. Presumably a routing or
  on-call system listens there.
- **Operators** — `/healthz` and `/readyz` exist for a load balancer / orchestrator.

## Domain model

Four concepts, all defined in `packages/triage_core/models.py`.

### Ticket

The inbound unit of work. Fields: `ticket_id`, `tenant_id`, `subject`, `body`,
`channel`, `created_at`, `locale` (default `ko-KR`), `attachments`.

Two things are worth noticing about `Ticket`:

- **It is multi-tenant.** `tenant_id` is carried on every ticket and is one of the
  two inputs to the priority calculation. But see
  [Finding Q-4](08-code-quality.md#q-4-no-tenant-scoping-on-reads-idor) — tenancy
  is not enforced on the read path.
- **The default locale is Korean.** The keyword rules are bilingual
  (`"환불"`/`"refund"`, `"장애"`/`"down"`), which tells you the primary market is
  Korea with English as a secondary. The `attachments` field is declared and never
  used anywhere in the codebase.

### TriageResult

The verdict: `ticket_id`, `category`, `priority`, `sentiment`, `assignee_group`,
and a human-readable `rationale` string. Note the `rationale` is generated but
**never persisted and never returned by the API** — it exists only in memory
inside the worker.

### Priority

An `IntEnum`: `LOW = 1`, `NORMAL = 2`, `HIGH = 3`, `URGENT = 4`. Being an
`IntEnum` matters, because the escalation logic does integer arithmetic on it.

### Channel

A `StrEnum`: `email`, `chat`, `phone`, `portal`. The API accepts `channel` as a
free-form `str` and only converts it to `Channel` later, which is a source of
500s — see [Finding Q-9](08-code-quality.md#q-9-invalid-channel-returns-500-not-422).

## The triage rules

All business rules live in one 24-line file, `packages/triage_core/rules.py`,
whose docstring says: *"Static routing rules. Owned by the CX ops team, edited
without review."* Treat that as a warning label — this file is the highest-churn,
lowest-guardrail part of the system.

**Category** is decided by first-match keyword scan over
`subject + "\n" + body`, lowercased and truncated to 4000 characters:

```
billing  ← invoice, refund, charge, 결제, 환불
outage   ← down, cannot login, 500, 장애, 접속안됨
how-to   ← how do i, where is, 사용법
feedback ← suggest, feature request, 건의
```

First match wins, and **dictionary insertion order is the precedence order** — a
ticket saying "I cannot login and want a refund" is classified `billing`, not
`outage`, purely because `billing` is listed first. That is load-bearing
behaviour that nothing documents or tests.

If no keyword matches, the LLM fallback would run if a client were injected;
otherwise the category is `unknown`.

**Sentiment** is a bag-of-words score, clamped to `[-1.0, 1.0]`:

```
score = 0.4 × (positive matches) − 0.6 × (negative matches)
negative: terrible, awful, angry, 화가, 최악, 환불해
positive: thanks, great, 감사, 좋아
```

**Priority** starts at a per-category floor (`outage` → HIGH, `billing` → NORMAL,
everything else → LOW) and is then adjusted:

1. If the tenant is in `ESCALATION_TENANTS` (`acme-corp`, `globex`, `initech`),
   priority is bumped by one, capped at `URGENT`. This is a hardcoded list of
   customer names in source control.
2. If `sentiment <= -1.0`, priority is forced to `URGENT`.

Because sentiment is clamped at `-1.0`, rule 2 fires as soon as **two** negative
keywords appear in the text (2 × 0.6 = 1.2, clamped to 1.0). A customer who
writes "this is awful and I am angry" goes straight to URGENT regardless of
category or tenant. Whether that is intended is unclear from the code; it reads
like an accident of the clamp.

**Assignee group** is a straight lookup of category in `GROUP_BY_CATEGORY`, with
`cx-tier1` as the fallback.

## What the system explicitly does *not* do

Worth knowing up front, because a newcomer will assume otherwise:

- It does not store ticket bodies. The `tickets` table is defined in
  `store.py` and **never written to by any code path**.
- It does not deduplicate, rate-limit, or retry.
- It does not translate or branch on `locale`, despite carrying the field.
- It does not authorise per tenant — one shared static bearer token guards
  everything.
- It has no notion of a ticket lifecycle (open/closed/reassigned). Triage is
  fire-and-forget.
