# Dispatch — Codex CLI annex

How the conductor delegates a pipeline link on this harness.

## Native agent roles

The personas ship as Codex agent roles in `.codex/agents/`
(`re-developer-agent.toml`, `re-architect-agent.toml`; the `.md` twins carry
the same body for inline framing). Delegate by **spawning the named role**
(`spawn_agent` with `role: "re-developer-agent"` / `"re-architect-agent"`)
with the brief as the task, then wait for its result before continuing.

- The role's `developer_instructions` carry the persona and its knowledge
  preflight — do NOT inject persona or knowledge prose into the task. The brief
  carries only the items `SKILL.md` lists for that link.
- Delegated roles are leaves (`[agents] max_depth = 1`): they cannot spawn.
  The conductor owns every spawn.
- Independent repos may be spawned in parallel; the two links of one repo are
  sequential, with the link-1 receipt minted between them.

## Inline fallback

If multi-agent spawning is not enabled in this session, run the link inline:
read `.codex/agents/re-developer-agent.md` (or `re-architect-agent.md`) and
every file its preflight names, do that link's work yourself, write the same
files (handoff / staged candidate), then mint the same receipt.

## Return contract

Every link returns the structured summary its persona defines. Read it before
minting the receipt; surface any Issues / Concerns to the user before continuing.
