# Dispatch — GitHub Copilot annex

How the conductor delegates a pipeline link on this harness.

## Native custom agents

The personas ship as Copilot custom agents in `{{AGENTS_DIR}}/`
(`re-developer-agent.md`, `re-architect-agent.md`). Delegate by **invoking the
named custom agent** with the brief as its task and waiting for its result.

- The agent file carries the persona and its knowledge preflight — do NOT
  paste persona or knowledge prose into the brief. The brief carries only the
  items `SKILL.md` lists for that link.
- Worker agents carry a `tools:` allowlist that omits Copilot's `agent`
  delegation tool, so they cannot delegate further.
- Independent repos may be dispatched in parallel where the client allows; the
  two links of one repo are sequential, with the link-1 receipt minted between them.

## Inline fallback

If agent invocation is unavailable, run the link inline: read the persona file
and every file its preflight names, do that link's work yourself, write the
same files (handoff / staged candidate), then mint the same receipt.

## Return contract

Every link returns the structured summary its persona defines. Read it before
minting the receipt; surface any Issues / Concerns to the user before continuing.
