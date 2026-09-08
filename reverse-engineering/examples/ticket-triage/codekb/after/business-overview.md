# Business Overview

## Domain & Purpose

`ticket-triage` (version 0.4.2) is a **customer-support ticket ingestion and
triage service**. It accepts inbound support tickets over HTTP, classifies each
one, and decides which internal group should own it — replacing the manual
first-pass sorting a CX (customer experience) team would otherwise do by hand.

The domain vocabulary is encoded directly in `packages/triage_core/models.py`
and `packages/triage_core/rules.py`:

| Term | Meaning in this system | Defined at |
|---|---|---|
| **Ticket** | A single inbound support request: tenant, subject, body, channel, locale, attachments | `packages/triage_core/models.py:23-32` |
| **Tenant** | The customer organisation the ticket belongs to (multi-tenant SaaS) | `models.py:26` |
| **Channel** | How the ticket arrived: `email`, `chat`, `phone`, `portal` | `models.py:16-20` |
| **Category** | The triage bucket: `billing`, `outage`, `how-to`, `feedback`, or `unknown` | `rules.py:4-9` |
| **Priority** | `LOW`(1) / `NORMAL`(2) / `HIGH`(3) / `URGENT`(4) | `models.py:9-13` |
| **Sentiment** | A −1.0 … +1.0 score derived from emotive keywords | `engine.py:56-60` |
| **Assignee group** | The team queue the ticket routes to: `cx-billing`, `sre-oncall`, `cx-tier1`, `product` | `rules.py:13-19` |
| **Escalation tenant** | A named account whose tickets get a priority bump | `rules.py:11` |
| **Triage result** | Category + priority + sentiment + assignee group + a human-readable rationale | `models.py:35-42` |

The system is explicitly **bilingual by design** — keyword and sentiment
dictionaries carry both English and Korean terms (`rules.py:4-9`,
`engine.py:22-23`) and `Ticket.locale` defaults to `ko-KR` (`models.py:31`).

## Key Functionality

1. **Accept a support ticket** — a tenant's system posts a ticket; the service
   assigns it an id and acknowledges immediately (`POST /v1/tickets` → 202).
2. **Classify it** — keyword matching picks a category, an emotive-word count
   produces a sentiment score, and a priority floor plus escalation-tenant and
   sentiment rules set the final priority (`packages/triage_core/engine.py`).
3. **Route it** — each category maps to an owning group; unmatched tickets fall
   back to `cx-tier1` (`rules.py:13-19`, `engine.py:43`).
4. **Notify the owning team** — the worker fans the result out to a Slack
   channel (`services/worker/notifier.py`).
5. **Re-run triage on demand** — an operator can force reclassification of a
   ticket with corrected content (`POST /v1/tickets/{id}/reclassify`).
6. **Report liveness / queue depth** — `GET /healthz`, `GET /readyz`.

### Capability status (important for onboarding)

The advertised end-to-end business flow **does not currently complete**. The
worker classifies queued tickets and writes `triage_results` rows
(`services/worker/main.py:44-55`), but the only read endpoint,
`GET /v1/tickets/{id}/triage`, serves an in-process dictionary that is written
*exclusively* by the reclassify endpoint (`services/api/routes/tickets.py:15,
27-29, 51`). Nothing in the codebase ever reads `TriageRow`. A normally
ingested ticket's triage result is therefore **never retrievable through the
API**. See `architecture.md` § Improvement Opportunities and
`code-quality-assessment.md` § Technical Debt (D1).

The following are present in code but are **not live capabilities** and should
not be described as such:

- **Ticket archival** — the `tickets` table / `TicketRow` (`store.py:10-17`) is
  never written or read; inbound ticket bodies are not persisted anywhere.
- **AWS SNS notification** — the SNS branch (`notifier.py:19-20`) is unreachable
  because the worker never passes `topic_arn` (`worker/main.py:30`).
- **LLM classification fallback** — `engine.py:51-53` and
  `settings.llm_endpoint` (`config.py:11`); no LLM client is ever injected.

## Users & Actors

| Actor | Interaction | Evidence |
|---|---|---|
| **Tenant / integrating support system** | Posts tickets over HTTP with a bearer token | `routes/tickets.py:18-22`, `deps.py:6-13` |
| **CX operations team** | Owns the routing rule constants; edits them directly in source | `rules.py:1` ("Owned by the CX ops team, edited without review") |
| **CX / SRE agent groups** | Downstream recipients of routed tickets: `cx-billing`, `cx-tier1`, `sre-oncall`, `product` | `rules.py:13-19` |
| **Operator / support engineer** | Calls `reclassify`, checks `/healthz` and `/readyz` | `routes/tickets.py:32-52`, `routes/health.py` |
| **Slack** (external system) | Receives triage notifications via incoming webhook | `notifier.py:21-23` |
| **AWS SNS** (external system, dormant) | Would receive triage notifications | `notifier.py:10,19-20` |
| **Redis / PostgreSQL** (external infrastructure) | Pending queue and triage-result store | `queue.py`, `store.py`, `infra/docker-compose.yml` |

## Business Constraints & Assumptions

- **Multi-tenancy is a data-model concept only, not a security boundary.**
  Every ticket carries `tenant_id`, but authentication is a single shared static
  bearer token (`deps.py:6-13`) and **no endpoint compares the caller to the
  ticket's tenant**. Any token holder can read or reclassify any tenant's
  ticket. If tenants are distinct legal customers, this is a contractual and
  likely regulatory exposure.
- **Routing rules are business-owned but change-controlled as code.** Category
  keywords, escalation tenants, groups and priority floors are hard-coded
  constants (`rules.py`) that require a code deploy to change, yet the module
  header states they are edited without review.
- **Named escalation accounts.** `acme-corp`, `globex`, `initech` receive an
  automatic priority bump (`rules.py:11`, `engine.py:64-65`) — an operational
  commitment encoded in source.
- **Korean-first / English-second locale assumption.** `locale` defaults to
  `ko-KR`; sentiment regexes recognise only English and Korean tokens
  (`engine.py:22-23`), so any other language scores neutral. Multilingual
  support is a stated upcoming requirement (`engine.py:3-5`).
- **Ticket content is not retained.** Bodies transit Redis and are dropped after
  classification. There is no audit trail of what was received — relevant to any
  dispute-resolution or data-retention obligation.
- **Priority is capped at URGENT** and a sentiment score of −1.0 forces URGENT
  regardless of category (`engine.py:66-67`).
- No SLA, rate-limiting, billing, or reporting logic is present anywhere in the
  repository.
