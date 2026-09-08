# reverse-engineering — Cursor (user-global) distribution

From the skill source directory, merge the harness directory into your home directory (`cp -R` merges into an existing directory; do NOT append the harness dir to the destination, the dist already contains it):

```bash
cp -R dist/cursor-global/.cursor ~/
```

Installed paths:

- `~/.cursor/skills/reverse-engineering/` — the skill (SKILL.md, harness annexes, knowledge, templates, scripts)
- `~/.cursor/agents/re-developer-agent.*`, `re-architect-agent.*` — the two pipeline personas

Prerequisites: `bun` and `git` on PATH.

Invoke from the project root: `/reverse-engineering <what you are about to do in this codebase>`

Verify: `bun ~/.cursor/skills/reverse-engineering/scripts/codekb.ts help`

Output: `codekb/<repo>/` (9 artifacts, commit it). `codekb/.record/` is run bookkeeping (git-ignorable).
