#!/usr/bin/env bun
// Mechanical scorer: same measurement applied to any run's documentation output.
// Usage: bun score.ts <run-dir> <label> [--exclude <substr>]
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const CANONICAL = [
  "business-overview.md", "architecture.md", "code-structure.md",
  "api-documentation.md", "component-inventory.md", "technology-stack.md",
  "dependencies.md", "code-quality-assessment.md",
  "reverse-engineering-timestamp.md",
];
const SOURCE_DOCS = new Set(["README.md"]); // pre-existing, not produced by the run

const root = process.argv[2];
const label = process.argv[3] ?? root;

function walk(dir: string, acc: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === ".git" || e.name === "node_modules") continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.name.endsWith(".md")) acc.push(p);
  }
  return acc;
}

const all = walk(root)
  .map((p) => relative(root, p))
  .filter((r) => !SOURCE_DOCS.has(r))
  .filter((r) => !r.includes("/.record/"))   // run bookkeeping, not deliverable
  .sort();

let lines = 0, bytes = 0, mermaid = 0, h2 = 0, codeRefs = 0;
const fileRefRe = /(?:^|[\s`(])((?:services|packages|tests|infra)\/[\w./-]+\.(?:py|toml|yml|yaml))/g;
for (const rel of all) {
  const body = readFileSync(join(root, rel), "utf-8");
  lines += body.split(/\r?\n/).length;
  bytes += statSync(join(root, rel)).size;
  mermaid += (body.match(/```mermaid/g) ?? []).length;
  h2 += (body.match(/^##\s+/gm) ?? []).length;
  codeRefs += [...body.matchAll(fileRefRe)].length;
}

const basenames = new Set(all.map((r) => r.split("/").pop()!));
const canonicalPresent = CANONICAL.filter((c) => basenames.has(c));
const scopeBlock = all.some((rel) =>
  /```yaml[\s\S]*?scope_version:\s*1[\s\S]*?analyzed:/.test(readFileSync(join(root, rel), "utf-8")));

console.log(JSON.stringify({
  label,
  docs_produced: all.length,
  files: all,
  total_lines: lines,
  total_bytes: bytes,
  h2_sections: h2,
  mermaid_diagrams: mermaid,
  source_file_citations: codeRefs,
  canonical_artifacts_present: canonicalPresent.length,
  canonical_missing: CANONICAL.filter((c) => !basenames.has(c)),
  machine_readable_scope_block: scopeBlock,
}, null, 2));
