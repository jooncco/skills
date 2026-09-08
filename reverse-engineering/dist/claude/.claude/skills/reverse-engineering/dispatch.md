# Dispatch — Claude Code annex

How the conductor delegates a pipeline link on this harness.

## Native subagents

The personas ship as Claude Code subagents in `.claude/agents/`
(`re-developer-agent.md`, `re-architect-agent.md`). Delegate with the
**Agent** tool:

- Developer (link 1): `subagent_type: "re-developer-agent"`
- Architect (link 2): `subagent_type: "re-architect-agent"`

The harness loads the persona and its knowledge preflight automatically —
do NOT paste persona or knowledge prose into the brief. The brief carries only
the items `SKILL.md` lists for that link. Independent repos may be dispatched
in parallel (several Agent calls in one turn); the two links of one repo are
always sequential, with the link-1 receipt minted between them.

If the named subagent type is not registered in this session (the skill was
installed to `~/.claude/skills/` without copying `agents/`), use
`subagent_type: "general-purpose"` and open the brief with:

> Read `.claude/agents/re-developer-agent.md` (or `re-architect-agent.md`) now
> and act as that agent for this task; complete its knowledge preflight first.

## Inline fallback

If the Agent tool is unavailable, run the link inline: read the persona file
and every file its preflight names, do that link's work yourself, write the
same files (handoff / staged candidate), then mint the same receipt. Keep the
conductor and link roles separate in your reasoning; the artifacts and
receipts are the contract, not the process boundary.

## Return contract

Every link returns the structured summary its persona defines. Read it before
minting the receipt; surface any Issues / Concerns to the user before continuing.
