# Dispatch — Kiro IDE annex

How the conductor delegates a pipeline link on this harness.

## Native crew dispatch

The personas ship as Kiro custom agents in `~/.kiro/agents/`
(`re-developer-agent.md`, `re-architect-agent.md` — frontmatter `tools` + `permissions`).
Delegate with the **`subagent`** tool using Kiro's crew schema — every call has
the shape:

```json
{ "mode": "blocking",
  "task": "<one-line task>",
  "stages": [ { "name": "developer-<repo>", "role": "re-developer-agent", "prompt_template": "<the brief>" } ] }
```

- One link = a one-element `stages` array. Never call `subagent` with a bare
  agent/task pair or omit `stages`.
- Several repos' developer links may be independent entries in one call
  (parallel). The architect link of a repo is a SEPARATE later call, because
  the developer receipt must be minted between the two links — do not chain
  them with `depends_on` inside one call.
- The agent file IS its persona and its preflight loads the knowledge; do NOT paste persona
  or knowledge prose into `prompt_template`. The brief carries only the items
  `SKILL.md` lists for that link.

## Inline fallback

If the `subagent` tool is unavailable, run the link inline: read
`~/.kiro/agents/re-developer-agent.md` (or `re-architect-agent.md`) and every
file its preflight names, do that link's work yourself, write the same files
(handoff / staged candidate), then mint the same receipt.

## Return contract

Every link returns the structured summary its persona defines. Read it before
minting the receipt; surface any Issues / Concerns to the user before continuing.
