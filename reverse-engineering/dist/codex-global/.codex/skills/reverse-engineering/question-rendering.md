# Question Rendering — Codex CLI annex

A ` ```question ` block in `SKILL.md` is **INPUT to this rendering, never
output to paste**: never echo the fence or its field lines into the chat.

## Primary: `request_user_input`

When the `request_user_input` tool is available (Codex config
`[tools] experimental_request_user_input = { enabled = true }`), render every
spec through it: `prompt` → the question text, `header` → the short title,
each option's `label` / `description` → a choice, plus an "Other" free-text
choice. Branch on the returned choice.

## Fallback: numbered prose

Otherwise render as numbered prose: the prompt as a sentence prefixed by the
bold header, options as `N. **label** — description` in spec order, one extra
`N+1. Other — tell me what you have in mind.` line, then END THE TURN and wait
for the human's reply (number, label, or free text). The approval gate at Step
5 is rendered the same way; the run is not approved until the human picks
**Approve** explicitly.
