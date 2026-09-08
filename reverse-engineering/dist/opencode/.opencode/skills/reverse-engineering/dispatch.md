# Dispatch — opencode annex

How the conductor delegates a pipeline link on this harness.

## Native subagents

The persona files in `.opencode/agents/` (`re-developer-agent.md`,
`re-architect-agent.md`) are native opencode subagents (`mode: subagent`; `permission.task: deny` keeps them leaves). Delegate with the **`task`** tool targeting the agent by
name, with the brief as the task.

- The persona and its knowledge preflight load through the agent file — do NOT
  paste persona or knowledge prose into the brief. The brief carries only the
  items `SKILL.md` lists for that link.
- Worker agents do not get the `task` tool and cannot delegate further.
- Independent repos may be dispatched in parallel; the two links of one repo
  are sequential, with the link-1 receipt minted between them.

## Inline fallback

If the `task` tool is unavailable, run the link inline: read the persona file
and every file its preflight names, do that link's work yourself, write the
same files (handoff / staged candidate), then mint the same receipt.

## Return contract

Every link returns the structured summary its persona defines. Read it before
minting the receipt; surface any Issues / Concerns to the user before continuing.
