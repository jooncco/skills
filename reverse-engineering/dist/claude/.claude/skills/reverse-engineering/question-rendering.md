# Question Rendering — Claude Code annex

A ` ```question ` block in `SKILL.md` is **INPUT to this rendering, never
output to paste**: never echo the fence or its field lines into the chat.

## Mechanism: AskUserQuestion

Render every spec with the **AskUserQuestion** tool, mapping fields 1:1:
`prompt` → `question`, `header` → `header`, `multiSelect` → `multiSelect`,
each option's `label` / `description` → an option. The tool adds the "Other"
escape itself. Branch on the returned label.

If AskUserQuestion is unavailable in this session, fall back to numbered
prose: the prompt as a sentence, options as `N. **label** — description`, an
extra `Other` line, and end the turn until the human answers.
