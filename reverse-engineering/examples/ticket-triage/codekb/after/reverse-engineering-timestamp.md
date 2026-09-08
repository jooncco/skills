# Reverse Engineering Timestamp

| Field | Value |
|---|---|
| **Performed** | 2026-09-06 |
| **Repository** | `after` (project `ticket-triage`, version 0.4.2) |
| **Repository root** | `<workspace>/examples/ticket-triage` |
| **Commit** | `36d341d52cf25de5469f072a9c6469dee384353a` (`36d341d` — "baseline", single-commit history) |
| **Intent** | `initial-onboarding` |
| **Breadth** | Full rescan (no prior store existed — `store_generation: none`) |
| **Depth** | Standard |
| **Source fingerprint** | `git:edc586fa596d3d445f0a553dbd01f16a65d7c7ae` |
| **Pipeline** | Reverse Engineering — developer scan (link 1) → architect synthesis (link 2) |

## Coverage Notes

The repository is small (18 application/config files, ~495 lines), so the full
rescan read **every application file line by line**. No path outside the
snapshot set (`./`) required deep reading, and no re-snapshot was needed.

Excluded from analysis (non-application):

- `codekb/` — this pipeline's own working directory; read for run metadata only.
- `.git/` — inspected only via `git log` / `git rev-parse`.

Statements in the eight prose artifacts are grounded in file:line evidence from
this commit. Notable findings recorded as verified, not inferred: the
disconnected read path (`services/api/routes/tickets.py:15,27-29` vs
`services/worker/main.py:44-55`), the absent Dockerfile against
`.gitlab-ci.yml:19` and `infra/docker-compose.yml:3,9`, the layering violation at
`services/worker/main.py:12-13`, and the undeclared `psycopg` driver.

## Scope of Analysis

```yaml
scope_version: 1
kind: full
intent: initial-onboarding
fingerprint: edc586fa596d3d445f0a553dbd01f16a65d7c7ae
analyzed:
  paths:
    - ./
  components:
    - triage_core
    - services.api
    - services.worker
    - tests
    - infra
shallow:
  paths:
    - codekb/
```
