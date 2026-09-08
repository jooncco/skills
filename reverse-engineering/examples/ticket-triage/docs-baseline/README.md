# ticket-triage — Engineering Documentation

Reverse-engineered documentation for the `ticket-triage` service (version `0.4.2`,
per `pyproject.toml`). Written from the source at commit `c1edfc3`; there was no
pre-existing documentation beyond a 5-line root `README.md`.

> **Scope note.** Everything here was derived by reading the code. Where the code
> is ambiguous or apparently broken, that is called out explicitly rather than
> smoothed over. Nothing was inferred from a running system — the service was not
> executed.

## Start here

If you are new, read in this order:

1. **[01 — System Overview](01-overview.md)** — what the product does and the
   domain vocabulary (ticket, category, priority, sentiment, assignee group).
2. **[02 — Architecture](02-architecture.md)** — the two processes, the queue
   between them, and the request/data flow end to end.
3. **[03 — Code Structure](03-code-structure.md)** — directory-by-directory,
   module-by-module map of the repository.
4. **[04 — API Reference](04-api-reference.md)** — the five HTTP endpoints.
5. **[05 — Component Inventory](05-components.md)** — every component, its
   responsibility, its collaborators, and its state.
6. **[06 — Technology Stack](06-technology-stack.md)** — languages, frameworks,
   infrastructure, CI.
7. **[07 — Dependencies](07-dependencies.md)** — third-party packages, internal
   coupling, and external systems.
8. **[08 — Code Quality Assessment](08-code-quality.md)** — the honest state of
   the codebase: bugs, gaps, risks, ranked.
9. **[09 — Local Development](09-local-development.md)** — how to actually get it
   running, including the things that are currently missing.

## The 60-second version

`ticket-triage` accepts customer-support tickets over HTTP, pushes them onto a
Redis list, and a separate worker process pops each ticket, classifies it with a
keyword rule engine (category + priority + sentiment), writes the verdict to a
SQL database, and notifies a downstream channel (Slack webhook and/or AWS SNS).

It is small — **433 lines of Python across 19 files**, of which 32 lines are
tests. It is also, in its current state, **not coherently wired**: the read path
of the API does not read what the worker writes (see
[Finding Q-1](08-code-quality.md#q-1-the-read-path-is-disconnected-from-the-write-path)),
and the container build referenced by CI and Compose does not exist in the
repository (see [Finding Q-2](08-code-quality.md#q-2-there-is-no-dockerfile)).
Read [08 — Code Quality](08-code-quality.md) before you promise anyone a delivery
date.
