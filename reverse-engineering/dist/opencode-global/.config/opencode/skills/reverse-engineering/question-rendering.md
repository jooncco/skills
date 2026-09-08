# Question Rendering — opencode (user-global) annex

This file binds the fenced ` ```question ` specs in `SKILL.md` to this
harness's concrete mechanism. A ` ```question ` block is **INPUT to this
rendering, never output to paste**: never echo the fence or any of its field
lines (`prompt:`, `header:`, `options:`, `label:`, `description:`) into the chat.

## Mechanism: numbered prose

opencode (user-global) has no structured-question tool in this skill's scope, so
render every spec as numbered prose and wait for the human's reply:

1. Write the `prompt` text as a plain sentence (prefix it with the `header` in
   bold, e.g. **Code KB:**).
2. List every option as `N. **label** — description`, in the spec's order.
3. Append one extra line: `N+1. Other — tell me what you have in mind.`
4. End the turn. Do NOT proceed until the human answers with a number, a
   label, or free text; map free text to the closest option or treat it as
   "Other".

Example rendering of the reuse question:

> **Code KB:** An up-to-date code knowledge base exists for `api` (built by
> intent `initial-onboarding`; verified unchanged). Deep coverage: `./`. Reuse
> it, or rescan?
>
> 1. **Reuse existing knowledge base** — Skip the scan; downstream work reads the current store as-is
> 2. **Full rescan** — Rebuild the store covering the whole repo (replaces all 9 artifacts)
> 3. **Focused scan** — Scan this intent's area and extend the store; preserve prior prose outside it, demoting unverifiable deep coverage to shallow
> 4. Other — tell me what you have in mind.

`multiSelect: true` specs say "choose one or more numbers". The approval gate
at Step 5 is rendered the same way; the run is not approved until the human
picks **Approve** explicitly.
