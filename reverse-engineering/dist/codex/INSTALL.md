# reverse-engineering — Codex CLI distribution

From the skill source directory, merge the harness directories into your project root (`cp -R` merges into an existing directory; do NOT append the harness dir to the destination, the dist already contains it):

```bash
cp -R dist/codex/.agents dist/codex/.codex /path/to/project/
```

Installed paths:

- `.agents/skills/reverse-engineering/` — the skill (SKILL.md, harness annexes, knowledge, templates, scripts)
- `.codex/agents/re-developer-agent.*`, `re-architect-agent.*` — the two pipeline personas

Prerequisites: `bun` and `git` on PATH.

Invoke from the project root: `$reverse-engineering <what you are about to do in this codebase>`

Verify: `bun .agents/skills/reverse-engineering/scripts/codekb.ts help`

Output: `codekb/<repo>/` (9 artifacts, commit it). `codekb/.record/` is run bookkeeping (git-ignorable).
