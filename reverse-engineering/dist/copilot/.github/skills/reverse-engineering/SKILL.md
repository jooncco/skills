---
name: reverse-engineering
description: >
  Reverse-engineer an existing (brownfield) codebase into a 9-artifact Code
  Knowledge Base (business-overview, architecture, code-structure,
  api-documentation, component-inventory, technology-stack, dependencies,
  code-quality-assessment, reverse-engineering-timestamp) under
  `codekb/<repo>/`. Runs the AI-DLC reverse-engineering stage as a two-link
  pipeline: developer agent scans → architect agent synthesizes and
  publishes. Rerun-safe: detects an existing store, asks reuse / full rescan /
  focused scan, and merges with a compare-and-swap publish.
argument-hint: "[intent description] [--repo <name>[,<name>]] [--depth Minimal|Standard|Comprehensive] [--focus <paths>]"
---

# Reverse Engineering

You are the **conductor** of the reverse-engineering pipeline. You own the
store/reuse decision, the snapshots, the two agent dispatches, the link
receipts, and the approval gate. You do NOT inspect application source,
enumerate the repo, or precompute the file list yourself — that is the
developer link's job, and doing it here duplicates that link.

Two harness annexes sit beside this file and bind two neutral contracts to
this harness's concrete mechanisms. Read both before Step 1:

- `dispatch.md` — how to delegate a link to the developer / architect agent
  (native subagent, or the inline fallback when this session cannot delegate).
- `question-rendering.md` — how to render every fenced ` ```question ` spec in
  this file. The fence is INPUT to that annex, never text to paste into the chat.

## Conventions used below

- `.github/skills/reverse-engineering` — this skill's installed directory, project-relative
  (`knowledge/`, `templates/`, `scripts/` live under it).
- `<project>` — the current working directory (the workspace root).
- `<repo>` — a repository identity. **Lone-repo layout:** the project root is
  the repository and `<repo>` = its basename. **Multi-repo layout:** each
  registered repo is a sibling directory `<project>/<repo>/`.
- `codekb.ts` — `bun .github/skills/reverse-engineering/scripts/codekb.ts` (run from `<project>`).
  Run `bun .github/skills/reverse-engineering/scripts/codekb.ts help` for the verb list.
- Store: `codekb/<repo>/` (durable, 9 artifacts, shared across runs).
  Record: `codekb/.record/<repo>/` (attempt, receipts, handoff, staging).
- `<intent>` — a short kebab-case slug for what the user asked (e.g.
  `add-oauth-login`, `initial-onboarding`). Derive it from the argument; if
  none was given, ask one question or use `adhoc-<date>`.
- Depth: `Minimal` / `Standard` / `Comprehensive` (default `Standard`) — how
  much detail each document carries, never whether a section exists.

Pipeline contract: two links, in order, per repo. Link 1 (developer) scans and
writes the handoff; link 2 (architect, the final link) synthesizes and publishes
the 9 artifacts. Both links must have a current-attempt receipt before the
stage may be reported complete. Artifact files alone are NOT completion evidence.

What the user hears while the pipeline runs (say only these, filling the
brackets; never mention briefs, receipts, staging, links, or agent file names):
- Starting the chain — **SAY:** "The developer takes a look first, then the architect builds on what comes back."
- Handing a specific question to one specialist — **SAY:** "Let me bring in the [developer|architect] on [the question, in plain terms]."
- A specialist's work has come back and you are folding it in — **SAY:** nothing.

## Steps

### Step 1: Check Conditions

Confirm the workspace is **brownfield**: it contains existing application
source (a build manifest such as `package.json`, `pyproject.toml`, `go.mod`,
`pom.xml`, `Cargo.toml`, or a populated `src/`-like tree). Do this with a
one-line existence check, not a scan. If there is no existing code (greenfield),
stop and tell the user this skill only applies to existing codebases.

#### Resolve the repo set (multi-repo)

This stage runs **per repo**. Resolve the complete repo set before making any
reuse or scan decision:

1. If the user passed `--repo a,b`, that is the set. Each must exist as
   `<project>/<a>/`.
2. Otherwise, if the project root itself is the repository, the set is the
   single unrecorded project-root repo (`<repo>` = basename of `<project>`).
3. Each repo's codekb is independent, so selected scans MAY run as parallel
   dispatches where `dispatch.md` allows (one developer dispatch per repo, then
   one architect per repo).

For each repo, start the attempt record first:

```
bun .github/skills/reverse-engineering/scripts/codekb.ts attempt start --repo <repo> --intent <intent>
```

`attempt start` opens a fresh attempt (a resume of an interrupted run should
instead read `attempt status` first — see Resume below).

#### Rerun guard: check each existing store before scanning

The codekb is a shared store. A full rescan REPLACES all 9 artifacts; a focused
scan MERGES into the existing store so knowledge accumulates across runs. For
every repo in the set, run the read-only check:

```
bun .github/skills/reverse-engineering/scripts/codekb.ts scope-diff --repo <repo>
```

- **NO_STORE** — first scan for this repo. Proceed to Step 2; no question.
- **CURRENT** — the store's analyzed paths are unchanged since it was built.
  If the recorded coverage plausibly serves this intent's area, present the
  reuse question below. If this intent clearly targets code OUTSIDE the store's
  analyzed paths, skip the reuse option and ask rescan vs focused only.
- **STALE / UNVERIFIED / UNKNOWN_SCOPE** — the store's knowledge is out of
  date, unverifiable, or predates scope tracking. Present the rescan question
  below WITHOUT the reuse option.

Reuse question (CURRENT + coverage fits) — fold the tool output (store intent,
analyzed paths) into the prompt so the human decides on evidence. Render per
`question-rendering.md`:

```question
prompt: "An up-to-date code knowledge base exists for <repo> (built by intent <store-intent>; verified unchanged). Deep coverage: <analyzed paths>. Reuse it, or rescan?"
header: "Code KB"
multiSelect: false
options:
  - label: "Reuse existing knowledge base"
    description: "Skip the scan; downstream work reads the current store as-is"
  - label: "Full rescan"
    description: "Rebuild the store covering the whole repo (replaces all 9 artifacts)"
  - label: "Focused scan"
    description: "Scan this intent's area and extend the store; preserve prior prose outside it, demoting unverifiable deep coverage to shallow"
```

Rescan question (STALE / UNVERIFIED / UNKNOWN_SCOPE, or CURRENT with coverage
that does not fit) — include the verdict line in the prompt:

```question
prompt: "A code knowledge base exists for <repo> but <verdict summary — e.g. its analyzed paths have changed since it was built / it does not cover this intent's area>. A full rescan replaces it; a focused scan merges into it. How should the scan run?"
header: "Code KB"
multiSelect: false
options:
  - label: "Full rescan"
    description: "Rebuild the store covering the whole repo (replaces all 9 artifacts)"
  - label: "Focused scan"
    description: "Scan this intent's area and extend the store; preserve prior prose outside it, demoting unverifiable deep coverage to shallow"
```

Record one decision per repo: reuse, full rescan, or focused scan. On a scan
choice, also record its breadth; that choice sets the developer brief, and Step
3's scope block records what the scan actually covered. If the user chose
"Focused scan" and did not pass `--focus`, ask which repo-relative paths are
this intent's area (directories with trailing `/`, or files).

Immediately after each human **reuse** decision, record that repo's
current-attempt exemption (the tool re-verifies the complete store is present
and CURRENT):

```
bun .github/skills/reverse-engineering/scripts/codekb.ts reuse --repo <repo>
```

Immediately before Step 2, take one compare-and-swap snapshot for every repo
selected for scanning:

```
bun .github/skills/reverse-engineering/scripts/codekb.ts snapshot --repo <repo> --paths <source paths> --json
```

Choose `<source paths>` as follows:

- Full rescan: `./`.
- Focused scan of a CURRENT store: the union of the store's existing
  `analyzed.paths` (from the scope-diff output) and the intended focused paths.
  A full store therefore uses `./`.
- Focused scan of a STALE, UNVERIFIED, UNKNOWN_SCOPE, or NO_STORE store: the
  intended focused paths.

Keep the returned `store_generation`, `source_fingerprint`, and `paths` keyed
by repo. They bind synthesis to both the exact store generation and the source
bytes the scan is about to inspect. If the developer later reports an analyzed
path outside the snapshot's `paths`, discard that result and repeat the
snapshot plus scan over the expanded path set; never widen verified coverage
after the scan without a matching pre-scan snapshot.

Only after every repository decision has been resolved:

- If every repo is reused, skip Steps 2-4 and go to Step 5 reporting the stage
  as skipped with reason "codekb reuse: all resolved stores CURRENT, human chose reuse".
- If any repo needs scanning, proceed to Steps 2-3 for only the full/focused
  scan repos; leave each reused repo's store unchanged.

### Step 2: Developer Code Scan (link 1)

Dispatch the **developer** (agent `re-developer-agent`) per `dispatch.md`. The
agent's persona and knowledge load through the harness (or through the
persona-read line `dispatch.md` prescribes); never paste persona or knowledge
prose into the brief. The brief contains ONLY:

- The repo root to scan (`<project>` for the lone repo, `<project>/<repo>/` for a sibling)
- The intent (`<intent>` and the user's one-line description)
- The scan breadth chosen at Step 1 (full rescan = the whole repo; focused scan
  = the intent's area, named explicitly as paths)
- The depth (Minimal / Standard / Comprehensive)
- The snapshot `paths` for this repo — the deeply analyzed result MUST stay within that set
- The exact handoff path: `codekb/.record/<repo>/developer-scan.md`
- The requirement that the handoff's `### Scan Coverage` lists what was actually
  analyzed deeply vs skimmed
- The instruction to return only the structured summary (path + concerns), not the scan body

The developer scans the codebase for: all packages/modules and their purposes;
build systems, configuration, dependency relationships; external and internal
APIs; frameworks/libraries with versions; test directories, frameworks,
coverage config; code quality indicators (linting, CI/CD, documentation);
technical debt signals — and writes the handoff following the Developer Code
Scan Template in `.github/skills/reverse-engineering/knowledge/developer/re-artifacts.md`.

After the developer return has been read, mint link 1 (the tool verifies the
handoff exists, was written in this attempt, and carries `## Developer Code
Scan Results`, `### Scan Coverage`, and `## Handoff Summary`; it binds the
receipt to the file's SHA-256, so any later edit invalidates this link and
everything downstream):

```
bun .github/skills/reverse-engineering/scripts/codekb.ts link --repo <repo> --link developer --artifact codekb/.record/<repo>/developer-scan.md
```

If the return's Issues / Concerns says a deep path fell outside the snapshot
paths, do NOT mint the link: re-snapshot over the expanded set and re-dispatch.

### Step 3: Architect Synthesis (link 2, final)

Dispatch the **architect** (agent `re-architect-agent`) per `dispatch.md`.
Pass the developer handoff **path**, not its body. The brief contains ONLY:

- The handoff path `codekb/.record/<repo>/developer-scan.md`
- The repo root, the intent, the depth
- The write behavior decided in Step 1 (Full rescan / Focused scan) and the
  Step 1 store verdict (NO_STORE / CURRENT / STALE / UNVERIFIED / UNKNOWN_SCOPE)
- The store directory printed by `bun .github/skills/reverse-engineering/scripts/codekb.ts path --repo <repo>`
  (read it for a merge; never write to it directly)
- The staging directory: `codekb/.record/<repo>/.stage/`
- The snapshot values for this repo: `paths`, `store_generation`, `source_fingerprint`
- The exact tool lines the architect must run, in order:
  1. mint: `bun .github/skills/reverse-engineering/scripts/codekb.ts scope-diff --repo <repo> --mint --paths <final analyzed paths>` → paste output verbatim into the scope block's `fingerprint:`
  2. (only when Step 1 found an existing store) write the timestamp content to
     `codekb/.record/<repo>/scope-draft.md`, run
     `bun .github/skills/reverse-engineering/scripts/codekb.ts scope-diff --repo <repo> --compare codekb/.record/<repo>/scope-draft.md`
     BEFORE publishing (the compare needs the prior store unchanged), keep the
     COVERS / NARROWER output for the return summary, then delete the draft
  3. publish:
     ```
     bun .github/skills/reverse-engineering/scripts/codekb.ts publish --repo <repo> \
       --staged codekb/.record/<repo>/.stage/ \
       --paths <snapshot paths> \
       --expect-store <snapshot store_generation> \
       --expect-source <snapshot source_fingerprint> --json
     ```
  4. after a successful publish, delete `codekb/.record/<repo>/.stage/`

The architect synthesizes the scan into the complete 9-artifact candidate
(business-overview, architecture with an `## Interaction Diagrams` section,
code-structure, api-documentation, component-inventory, technology-stack,
dependencies, code-quality-assessment, reverse-engineering-timestamp ending
with the `## Scope of Analysis` block), applying these write behaviors:

- **Focused scan with an existing store (any verdict except NO_STORE):** read
  the existing 9 artifacts and the store's scope block first; update or extend
  sections covering the newly analyzed area and preserve prior prose outside it.
  - CURRENT: `analyzed.paths`/`components` = union of store and this run; a
    `kind: full` store stays full and keeps `./`; otherwise `kind: partial`, never `./`.
  - STALE / UNVERIFIED: record this run only; preserve prior prose but demote
    the store's prior `analyzed.paths` into `shallow.paths`.
  - UNKNOWN_SCOPE: merge prose best-effort; record only this run in the block.
- **Full rescan:** wholesale replace all 9 artifacts; scope block from this run only.
- **NO_STORE:** create all 9 from this run. A focused first scan is
  `kind: partial`; `kind: full` is valid only when `analyzed.paths` includes `./`.

Publish refusals (the architect handles them; you re-dispatch as needed):
- `CODEKB_STORE_CHANGED` — another run published after this repo's snapshot.
  Re-run the Step 1 status check, read the new store, recompute the merge, take
  a fresh snapshot, retry. The existing developer scan may be reused only when a
  fresh snapshot over the same paths returns the same `source_fingerprint`.
- `CODEKB_SOURCE_CHANGED` — source changed after the snapshot. Discard the
  candidate, take a fresh snapshot, repeat Step 2 and synthesis for that repo.
- `CODEKB_CANDIDATE_STALE` — fingerprint not minted from the current source. Rebuild and retry.
Never bypass a refusal with direct writes.

After the architect return has been read and the publish line is present, mint
the final-link receipt (the tool verifies all 9 files exist in the store and the
developer handoff is unchanged since its receipt):

```
bun .github/skills/reverse-engineering/scripts/codekb.ts link --repo <repo> --link architect
```

Do not proceed until every selected repo's chain has both receipts
(`bun .github/skills/reverse-engineering/scripts/codekb.ts attempt status --repo <repo>` shows
`COMPLETED developer,architect`, or `REUSED true`).

### Step 4: Completion Check

For every repo, confirm the evidence with `attempt status`. Then run the
advisory required-sections sensor on each published store:

```
bun .github/skills/reverse-engineering/scripts/codekb.ts sensor --dir codekb/<repo>/
```

Findings are advisory: report them at the gate; the human decides.

### Step 5: Present Completion & Request Approval

Present a completion summary:

- Per repo, the 9 artifacts produced under `codekb/<repo>/`; identify reused
  repos whose existing stores were left unchanged.
- **For every repo whose Step 3 compare returned NARROWER**, the summary MUST
  carry a repo-labeled warning before the question, quoting the tool's
  discarded list verbatim:

  ```
  WARNING for <repo>: this scan's verified scope is narrower than the previous
  store. On a focused merge, prior prose is preserved, but deep coverage for
  the following paths and components was demoted (affected paths remain
  recorded as shallow):
  <paths and components from the compare output>
  Choose Request Changes to widen the scan instead.
  ```

  (COVERS, or no prior store, needs no warning line.)
- Sensor findings, if any.
- Review path: `codekb/<repo>/` for each repo.
- Then render the approval question per `question-rendering.md`:

```question
prompt: "Reverse engineering is complete. Review codekb/<repo>/ and choose how to proceed."
header: "Approval"
multiSelect: false
options:
  - label: "Approve"
    description: "Accept the knowledge base as published<; accept the narrower verified coverage for <repos> when any repo returned NARROWER>"
  - label: "Request Changes"
    description: "Describe what to widen or correct; the affected repo's chain runs again"
```

On **Request Changes**: collect what to change, start a new attempt for the
affected repo (`attempt start` — this invalidates the old receipts), re-run the
Step 1 guard (the store now exists, so its verdict drives the question), and
run the chain again. A new developer scan is required whenever the developer
handoff must change; the architect alone may be re-dispatched only when the
change is purely a synthesis correction over an unchanged handoff — in that
case the developer link is re-minted against the unchanged handoff for the new
attempt, then the architect link.

On **Approve**: finish. Suggest committing `codekb/<repo>/`; `codekb/.record/`
is run bookkeeping and may be git-ignored.

### Learn (optional)

Before the approval question, ask once: "Anything to add for next time?" and
append any answer under a dated heading in `codekb/.record/learnings.md`.

## Resume

If invoked while a previous run was interrupted, read
`bun .github/skills/reverse-engineering/scripts/codekb.ts attempt status --repo <repo> --json` for each
repo first. `completed` lists the links with current-attempt receipts; dispatch
only the FIRST missing link (developer → architect). `reused: true` means that
repo's chain is already satisfied. A snapshot is not persisted: if the
developer link is complete but the architect is missing and the snapshot values
are lost, take a fresh snapshot over the same paths and reuse the handoff only
when the `source_fingerprint` is unchanged; otherwise start a new attempt.
