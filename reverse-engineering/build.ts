#!/usr/bin/env bun
// build.ts — package core/ + harness/<name>/ into dist/<name>/ for every harness.
//
//   bun build.ts            regenerate every dist/<harness>/
//   bun build.ts --check    byte-parity drift guard (exit 1 when dist is stale)
//   bun build.ts --only claude,codex
//
// Tokens substituted in core prose:  {{SKILL_DIR}}  {{AGENTS_DIR}}  {{INVOKE}}
// Tokens substituted in harness annexes additionally: {{HARNESS_NAME}}
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative } from "node:path";

const ROOT = dirname(new URL(import.meta.url).pathname);
const CORE = join(ROOT, "core");
const HARNESS = join(ROOT, "harness");
const DIST = join(ROOT, "dist");

type HarnessCfg = {
  name: string;
  skillDir: string;
  agentsDir: string;
  invoke: string;
  agentFormat: "claude" | "kiro-json" | "kiro-ide" | "codex-toml" | "cursor" | "opencode" | "copilot";
  skillFrontmatterExtra?: string;
  command?: string;
  global?: { skillDir: string; agentsDir: string; command?: string }; // user-global layout
  dist: string; // set by the builder: the dist/<name> directory
};

const AGENTS = ["developer-agent", "architect-agent"] as const;
const AGENT_NAME: Record<(typeof AGENTS)[number], string> = { "developer-agent": "re-developer-agent", "architect-agent": "re-architect-agent" };

// ------------------------------------------------------------- helpers

// A `~/`-prefixed install dir (user-global layouts) stays literal in prose but
// is emitted relative to dist/<harness>/ so the user copies it into $HOME.
function outRel(p: string): string {
  return p.replace(/^~\//, "");
}

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

function sub(text: string, cfg: HarnessCfg): string {
  return text
    .replaceAll("{{SKILL_DIR}}", cfg.skillDir)
    .replaceAll("{{AGENTS_DIR}}", cfg.agentsDir)
    .replaceAll("{{INVOKE}}", cfg.invoke)
    .replaceAll("{{HARNESS_NAME}}", cfg.name);
}

function splitFrontmatter(md: string): { fm: string; body: string } {
  const m = /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(md);
  if (!m) throw new Error("missing frontmatter");
  return { fm: m[1], body: m[2] };
}

function fmField(fm: string, key: string): string {
  // handles `key: value` and `key: >` folded blocks
  const lines = fm.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = new RegExp(`^${key}:\\s*(.*)$`).exec(lines[i]);
    if (!m) continue;
    if (m[1].trim() !== ">" && m[1].trim() !== "") return m[1].trim();
    const acc: string[] = [];
    for (let j = i + 1; j < lines.length && /^\s+/.test(lines[j]); j++) acc.push(lines[j].trim());
    return acc.join(" ");
  }
  return "";
}

// ------------------------------------------------------------- agent emitters

type AgentOut = { path: string; content: string }[];

function emitAgent(cfg: HarnessCfg, slug: (typeof AGENTS)[number], core: string): AgentOut {
  const { fm, body: rawBody } = splitFrontmatter(core);
  const name = AGENT_NAME[slug];
  const description = fmField(fm, "description");
  const body = sub(rawBody, cfg);
  const isArchitect = slug === "architect-agent";
  const md = (extra: string) => `---\nname: ${name}\ndescription: >\n  ${description}\n${extra}---\n${body}`;
  const codekb = `${cfg.skillDir}/scripts/codekb.ts`;
  switch (cfg.agentFormat) {
    case "claude":
      return [{ path: join(cfg.agentsDir, `${name}.md`), content: md(`tools: ${isArchitect ? "Read, Grep, Glob, Bash, Write, Edit" : "Read, Grep, Glob, Bash"}\nmodel: inherit\n`) }];
    case "cursor":
      return [{ path: join(cfg.agentsDir, `${name}.md`), content: md("") }];
    case "opencode":
      return [{ path: join(cfg.agentsDir, `${name}.md`), content: md("mode: subagent\npermission:\n  task: deny\n") }];
    case "copilot":
      return [{ path: join(cfg.agentsDir, `${name}.md`), content: md(`tools: [${isArchitect ? '"read", "edit", "search", "execute"' : '"read", "search", "execute", "edit"'}]\n`) }];
    case "kiro-ide":
      return [{
        path: join(cfg.agentsDir, `${name}.md`),
        content: md(
          `tools: ["read", "write", "shell"]\npermissions:\n  rules:\n    - capability: shell\n      effect: allow\n      match:\n        - "bun ${codekb} *"\n        - "git log *"\n        - "git ls-files *"\n        - "date -u *"\n    - capability: filesystem\n      effect: allow\n      match:\n        - "codekb/**"\n`,
        ),
      }];
    case "kiro-json": {
      const json = {
        name,
        description: `${description} Delegation target for the reverse-engineering skill (${isArchitect ? "link 2, synthesis" : "link 1, code scan"}).`,
        prompt: `file://${name}.md`,
        includeMcpJson: true,
        tools: ["fs_read", "fs_write", "execute_bash", "thinking"],
        allowedTools: ["fs_read", "thinking"],
        toolsSettings: {
          execute_bash: {
            allowedCommands: [
              `bun (run )?["']?${codekb.replaceAll(".", "\\.").replaceAll("/", "\\/")}["']?( .*)?`,
              "git (log|ls-files|rev-parse|status)( .*)?",
              "date -u( .*)?",
            ],
            deniedCommands: [
              "([^\\s]*/)?rm( [^\\s]+)* -[A-Za-z]*[rR][A-Za-z]*( .*)?",
              "([^\\s]*/)?git( -[^\\s]+( (\"[^\"]*\"|'[^']*'|[^\\s]+))?)* push( .*)?",
            ],
          },
          fs_write: { allowedPaths: ["codekb/**"] },
        },
        resources: [
          `file://${cfg.agentsDir}/${name}.md`,
          `file://${cfg.skillDir}/knowledge/${isArchitect ? "architect" : "developer"}/*.md`,
          ...(isArchitect ? [`file://${cfg.skillDir}/knowledge/developer/re-artifacts.md`, `file://${cfg.skillDir}/templates/*.md`] : []),
        ],
      };
      return [
        { path: join(cfg.agentsDir, `${name}.json`), content: `${JSON.stringify(json, null, 2)}\n` },
        { path: join(cfg.agentsDir, `${name}.md`), content: md("") },
      ];
    }
    case "codex-toml": {
      const esc = (s: string) => s.replaceAll("\\", "\\\\").replaceAll('"""', '\\"\\"\\"');
      const toml = `name = "${name}"\ndescription = "${description.replaceAll('"', '\\"')}"\ndeveloper_instructions = """\n${esc(body)}"""\n`;
      return [
        { path: join(cfg.agentsDir, `${name}.toml`), content: toml },
        { path: join(cfg.agentsDir, `${name}.md`), content: md("") },
      ];
    }
  }
}

// ------------------------------------------------------------- skill emitter

function emitSkill(cfg: HarnessCfg, hdir: string): AgentOut {
  const out: AgentOut = [];
  // SKILL.md
  const core = readFileSync(join(CORE, "SKILL.md"), "utf-8");
  const { fm, body } = splitFrontmatter(core);
  const fmOut = cfg.skillFrontmatterExtra ? `${fm}\n${cfg.skillFrontmatterExtra}` : fm;
  out.push({ path: join(cfg.skillDir, "SKILL.md"), content: sub(`---\n${fmOut}\n---\n${body}`, cfg) });
  // annexes
  out.push({ path: join(cfg.skillDir, "dispatch.md"), content: sub(readFileSync(join(hdir, "dispatch.md"), "utf-8"), cfg) });
  const qr = existsSync(join(hdir, "question-rendering.md")) ? join(hdir, "question-rendering.md") : join(HARNESS, "_shared", "question-numbered.md");
  out.push({ path: join(cfg.skillDir, "question-rendering.md"), content: sub(readFileSync(qr, "utf-8"), cfg) });
  // knowledge / templates / scripts — verbatim except token substitution in .md
  for (const sub_ of ["knowledge", "templates", "scripts"]) {
    for (const f of walk(join(CORE, sub_))) {
      const rel = relative(CORE, f);
      const raw = readFileSync(f, "utf-8");
      out.push({ path: join(cfg.skillDir, rel), content: f.endsWith(".md") ? sub(raw, cfg) : raw });
    }
  }
  return out;
}

function emitExtras(cfg: HarnessCfg, files: AgentOut): AgentOut {
  const out: AgentOut = [];
  if (cfg.command) {
    out.push({
      path: cfg.command,
      content: `---\ndescription: >\n  Reverse-engineer this brownfield codebase into the 9-artifact Code Knowledge Base under codekb/<repo>/ (developer scan → architect synthesis, rerun-safe).\n---\nRead \`${cfg.skillDir}/SKILL.md\` now and follow it exactly as the conductor of the\nreverse-engineering pipeline, with the arguments below passed through verbatim.\n\n$ARGUMENTS\n`,
    });
  }
  // exact copy command: the top-level harness dirs this dist ships
  const tops = [...new Set(out.concat(files).map((f) => outRel(f.path).split("/")[0]).filter((t) => t !== "INSTALL.md"))].sort();
  const home = cfg.skillDir.startsWith("~/");
  const cpCmd = `cp -R ${tops.map((t) => `dist/${cfg.dist}/${t}`).join(" ")} ${home ? "~/" : "/path/to/project/"}`;
  out.push({
    path: "INSTALL.md",
    content: `# reverse-engineering — ${cfg.name} distribution\n\nFrom the skill source directory, merge the harness director${tops.length > 1 ? "ies" : "y"} into ${home ? "your home directory" : "your project root"} (\`cp -R\` merges into an existing directory; do NOT append the harness dir to the destination, the dist already contains it):\n\n\`\`\`bash\n${cpCmd}\n\`\`\`\n\nInstalled paths:\n\n- \`${cfg.skillDir}/\` — the skill (SKILL.md, harness annexes, knowledge, templates, scripts)\n- \`${cfg.agentsDir}/re-developer-agent.*\`, \`re-architect-agent.*\` — the two pipeline personas\n${cfg.command ? `- \`${cfg.command}\` — the slash command that invokes the skill\n` : ""}\nPrerequisites: \`bun\` and \`git\` on PATH.\n\nInvoke from the project root: \`${cfg.invoke} <what you are about to do in this codebase>\`\n\nVerify: \`bun ${cfg.skillDir}/scripts/codekb.ts help\`\n\nOutput: \`codekb/<repo>/\` (9 artifacts, commit it). \`codekb/.record/\` is run bookkeeping (git-ignorable).\n`,
  });
  return out;
}

// ------------------------------------------------------------- main

// Each harness yields two distributions: `<name>` (project-local) and
// `<name>-global` (the harness's user-global directories, `~/`-prefixed).
function variants(h: string): HarnessCfg[] {
  const raw = JSON.parse(readFileSync(join(HARNESS, h, "harness.json"), "utf-8")) as Omit<HarnessCfg, "dist">;
  const local: HarnessCfg = { ...raw, dist: h };
  if (!raw.global) return [local];
  const g: HarnessCfg = {
    ...raw,
    name: `${raw.name} (user-global)`,
    skillDir: raw.global.skillDir,
    agentsDir: raw.global.agentsDir,
    command: raw.global.command,
    dist: `${h}-global`,
  };
  return [local, g];
}

function buildHarness(cfg: HarnessCfg): Map<string, string> {
  const hdir = join(HARNESS, cfg.dist.replace(/-global$/, ""));
  const files = new Map<string, string>();
  for (const f of emitSkill(cfg, hdir)) files.set(f.path, f.content);
  for (const slug of AGENTS) for (const f of emitAgent(cfg, slug, readFileSync(join(CORE, "agents", `${slug}.md`), "utf-8"))) files.set(f.path, f.content);
  for (const f of emitExtras(cfg, [...files].map(([path, content]) => ({ path, content })))) files.set(f.path, f.content);
  return files;
}

const args = process.argv.slice(2);
const check = args.includes("--check");
const onlyIdx = args.indexOf("--only");
const harnesses = readdirSync(HARNESS).filter((n) => !n.startsWith("_") && statSync(join(HARNESS, n)).isDirectory()).sort();
const selected = onlyIdx >= 0 ? args[onlyIdx + 1].split(",") : harnesses;

let drift = 0;
for (const cfg of selected.flatMap(variants)) {
  const h = cfg.dist;
  const files = buildHarness(cfg);
  const outDir = join(DIST, h);
  if (check) {
    const existing = existsSync(outDir) ? new Set(walk(outDir).map((p) => relative(outDir, p))) : new Set<string>();
    for (const [rel, content] of files) {
      const p = join(outDir, outRel(rel));
      if (!existsSync(p) || readFileSync(p, "utf-8") !== content) {
        console.log(`DRIFT ${h}: ${rel}`);
        drift++;
      }
      existing.delete(outRel(rel));
    }
    for (const stale of existing) {
      console.log(`STALE ${h}: ${stale}`);
      drift++;
    }
    continue;
  }
  rmSync(outDir, { recursive: true, force: true });
  for (const [rel, content] of files) {
    const p = join(outDir, outRel(rel));
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, content);
  }
  console.log(`built dist/${h} (${files.size} files)`);
}
if (check) {
  if (drift > 0) {
    console.log(`\n${drift} drifted file(s); run \`bun build.ts\``);
    process.exit(1);
  }
  console.log("dist is in sync");
}
