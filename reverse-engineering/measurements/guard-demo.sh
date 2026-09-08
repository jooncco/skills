#!/usr/bin/env bash
# Reproduces the rerun-guard / compare-and-swap behaviour on the published
# `after` store in examples/ticket-triage/ — deterministic, no LLM involved.
#
# Requires: bun, git. Safe by construction: the example tree is copied to a
# temporary directory and turned into a throwaway git repo there; nothing in
# this submission folder is modified. codekb.ts fingerprints the working tree
# through a temporary git index, so the copy needs one commit and nothing else.
#
#   bash measurements/guard-demo.sh            # prints the six-step transcript
#   bash measurements/guard-demo.sh > measurements/rerun-guard.txt
set -euo pipefail
CH="$(cd "$(dirname "$0")/.." && pwd)"
SK="${SKILL_DIR:-$CH/dist/claude/.claude/skills/reverse-engineering}"
KB="bun $SK/scripts/codekb.ts"
WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

cp -R "$CH/examples/ticket-triage/." "$WORK/"
rm -rf "$WORK/docs-baseline"
cd "$WORK"
git init -q && git add -A && git -c user.email=demo@example.com -c user.name=demo commit -qm baseline

REPO="$WORK"
SCRATCH="$REPO/services/api/routes/exports.py"
STAGE="$REPO/codekb/.record/after/.stage"
DRAFT="$REPO/codekb/.record/after/scope-draft.md"

echo "### [1] store verdict before any source change"
$KB scope-diff --repo after --json

echo; echo "### [2] add one new source file (feature-work scenario)"
cat > "$SCRATCH" <<'PY'
"""CSV export of triage results. Added after the codekb was built."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..deps import require_token

router = APIRouter(prefix="/v1/exports", tags=["exports"])


@router.get("/triage.csv")
def export_triage(tenant_id: str, _: str = Depends(require_token)) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ticket_id", "category", "priority", "assignee_group"])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv")
PY
echo "created services/api/routes/exports.py"

echo; echo "### [3] store verdict after the change -> STALE"
$KB scope-diff --repo after --json

echo; echo "### [4] a focused rescan narrower than the store -> NARROWER warning"
cat > "$DRAFT" <<'MD'
# Reverse Engineering Timestamp

## Scope of Analysis

```yaml
scope_version: 1
kind: partial
intent: add-csv-export
fingerprint: unknown
analyzed:
  paths:
    - services/api/routes/
  components:
    - services.api
shallow:
  paths:
    - packages/
```
MD
$KB scope-diff --repo after --compare codekb/.record/after/scope-draft.md || true
rm -f "$DRAFT"

mkdir -p "$STAGE"; cp codekb/after/*.md "$STAGE"/
# `|| true` is required: `set -o pipefail` would otherwise propagate the
# publish refusal (exit 1) out of the command substitution and abort the script.
GEN=$({ $KB publish --repo after --staged codekb/.record/after/.stage --paths ./ \
        --expect-store WRONG --expect-source x --json 2>&1 || true; } \
      | sed -n 's/.*found \(sha256:[0-9a-f]*\).*/\1/p')
STORE_FP=$({ $KB scope-diff --repo after --json || true; } | sed -n 's/.*"store_fingerprint":"\([0-9a-f]*\)".*/\1/p')

echo; echo "### [5a] publish with a stale store generation -> CODEKB_STORE_CHANGED"
$KB publish --repo after --staged codekb/.record/after/.stage --paths ./ \
  --expect-store none --expect-source "git:$STORE_FP" --json 2>&1 | head -1 || true

echo; echo "### [5b] correct store generation, stale source fingerprint -> CODEKB_SOURCE_CHANGED"
$KB publish --repo after --staged codekb/.record/after/.stage --paths ./ \
  --expect-store "$GEN" --expect-source "git:$STORE_FP" --json 2>&1 | head -1 || true
rm -rf "$STAGE"

echo; echo "### [6] every refusal left the store untouched"
rm -f "$SCRATCH"
$KB scope-diff --repo after --json
echo; echo "(temporary copy removed; the submission folder was never touched)"
