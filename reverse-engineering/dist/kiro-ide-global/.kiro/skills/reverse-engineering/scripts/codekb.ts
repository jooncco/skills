#!/usr/bin/env bun
// codekb.ts — standalone CodeKB engine for the `reverse-engineering` skill.
//
// A compact, self-contained port of the AI-DLC reverse-engineering stage's
// deterministic tooling (aidlc-utility.ts codekb-* verbs, aidlc-log.ts link,
// aidlc-state.ts reuse-artifact, the required-sections sensor). No aidlc
// workspace is needed: everything lives under `<project>/codekb/`.
//
//   codekb/<repo>/                 durable 9-artifact store (shared, committed)
//   codekb/.record/<repo>/         per-repo run record:
//       attempt.json               current attempt (id, started_at, intent, decision)
//       receipts.jsonl             PIPELINE_LINK_COMPLETED / ARTIFACT_REUSED rows
//       developer-scan.md          link-1 handoff (developer -> architect)
//       .stage/                    architect's staged candidate (transaction input)
//       scope-draft.md             temporary compare input (deleted after compare)
//       .txn/                      publish transaction scratch
//
// Verbs (all take --repo <name>; default = basename(project)):
//   path                         print the store directory
//   attempt start [--intent s] [--breadth full|focused] [--decision ...]
//   attempt status [--json]      completed links / reuse rows for the current attempt
//   scope-diff [--json]          NO_STORE | CURRENT | STALE | UNVERIFIED | UNKNOWN_SCOPE
//   scope-diff --mint --paths a,b            print the content fingerprint
//   scope-diff --compare <timestamp.md>      COVERS | NARROWER
//   snapshot --paths a,b [--json]            store_generation + source_fingerprint
//   publish --staged <dir> --paths a,b --expect-store G --expect-source F [--json]
//   link --link developer --artifact <handoff.md>
//   link --link architect
//   reuse                        record a current-attempt reuse row (store must be CURRENT)
//   sensor --dir <dir> [--templates <dir>] [--json]   required-sections check (advisory)
//   help
import {
  createHash,
  randomUUID,
} from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  realpathSync,
  renameSync,
  rmSync,
  rmdirSync,
  statSync,
  unlinkSync,
  writeFileSync,
  appendFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import {
  basename,
  dirname,
  isAbsolute,
  join,
  relative,
  resolve,
  sep,
} from "node:path";
import { spawnSync } from "node:child_process";

// ---------------------------------------------------------------- constants

export const ARTIFACT_FILES = [
  "api-documentation.md",
  "architecture.md",
  "business-overview.md",
  "code-quality-assessment.md",
  "code-structure.md",
  "component-inventory.md",
  "dependencies.md",
  "reverse-engineering-timestamp.md",
  "technology-stack.md",
] as const;

const LINKS = ["developer", "architect"] as const;
type Link = (typeof LINKS)[number];

const CODEKB_ROOT = "codekb";

// ---------------------------------------------------------------- cli utils

function die(msg: string, code = 1): never {
  process.stderr.write(`${msg}\n`);
  process.exit(code);
}

function parseArgs(argv: string[]): { positional: string[]; flags: Record<string, string> } {
  const positional: string[] = [];
  const flags: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        flags[key] = next;
        i++;
      } else {
        flags[key] = "true";
      }
    } else {
      positional.push(a);
    }
  }
  return { positional, flags };
}

function splitPaths(flags: Record<string, string>, verb: string): string[] {
  const paths = (flags.paths ?? "")
    .split(",")
    .map((p) => p.trim())
    .filter((p) => p !== "");
  if (paths.length === 0) die(`${verb}: pass --paths <comma-separated repo-relative paths>`);
  return [...new Set(paths)];
}

// ---------------------------------------------------------------- layout

type Ctx = {
  projectDir: string;
  repo: string;
  repoDir: string; // source root actually scanned
  storeDir: string; // codekb/<repo>/
  recordDir: string; // codekb/.record/<repo>/
  excludes: string[]; // fingerprint exclusions inside repoDir
};

function isValidRepoName(repo: string): boolean {
  return /^[A-Za-z0-9._-]+$/.test(repo) && repo !== "." && repo !== "..";
}

function resolveCtx(flags: Record<string, string>): Ctx {
  const projectDir = resolve(flags.project ?? process.cwd());
  const repo = flags.repo && flags.repo.length > 0 ? flags.repo : basename(projectDir);
  if (!isValidRepoName(repo)) die(`Invalid --repo "${repo}": a repo name must be one path segment.`);
  // multi-repo layout: `<project>/<repo>/` sibling directory; otherwise the
  // project root itself is the repository (lone-repo layout).
  const sibling = join(projectDir, repo);
  const repoDir = existsSync(sibling) && statSync(sibling).isDirectory() ? sibling : projectDir;
  return {
    projectDir,
    repo,
    repoDir,
    storeDir: join(projectDir, CODEKB_ROOT, repo),
    recordDir: join(projectDir, CODEKB_ROOT, ".record", repo),
    excludes: repoDir === projectDir ? [CODEKB_ROOT] : [],
  };
}

function relStore(ctx: Ctx): string {
  return `${CODEKB_ROOT}/${ctx.repo}/`;
}
function relRecord(ctx: Ctx): string {
  return `${CODEKB_ROOT}/.record/${ctx.repo}/`;
}

// ---------------------------------------------------------------- lock

let activeLock: string | null = null;
process.on("exit", () => {
  if (activeLock !== null) {
    try {
      rmdirSync(activeLock);
    } catch {
      /* already released */
    }
    activeLock = null;
  }
});

function withLock<T>(ctx: Ctx, fn: () => T): T {
  mkdirSync(ctx.recordDir, { recursive: true });
  const lock = join(ctx.recordDir, ".lock");
  const deadline = Date.now() + 30_000;
  for (;;) {
    try {
      mkdirSync(lock);
      break;
    } catch {
      try {
        const age = Date.now() - statSync(lock).mtimeMs;
        if (age > 120_000) {
          rmdirSync(lock);
          continue;
        }
      } catch {
        continue;
      }
      if (Date.now() > deadline) die(`codekb: lock busy for repo "${ctx.repo}" (${lock})`);
      Bun.sleepSync(100);
    }
  }
  activeLock = lock; // released in finally, or by the exit hook when die() exits inside fn
  try {
    return fn();
  } finally {
    try {
      rmdirSync(lock);
    } catch {
      /* ignore */
    }
    activeLock = null;
  }
}

// ---------------------------------------------------------------- scope block

export type ReScope = {
  kind: "full" | "partial";
  intent: string;
  fingerprint: string | null;
  analyzedPaths: string[];
  analyzedComponents: string[];
  shallowPaths: string[];
};
export type ReScopeParse =
  | { ok: true; scope: ReScope }
  | { ok: false; reason: "absent" | "malformed"; detail: string };

function extractScopeBlock(body: string): string | null {
  const lines = body.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (/^```ya?ml\s*$/.test(lines[i].trim())) {
      const inner: string[] = [];
      let j = i + 1;
      for (; j < lines.length; j++) {
        if (/^```\s*$/.test(lines[j].trim())) break;
        inner.push(lines[j]);
      }
      const block = inner.join("\n");
      if (/^\s*scope_version\s*:/m.test(block)) return block;
      i = j;
    }
  }
  return null;
}

export function parseReScope(body: string): ReScopeParse {
  const block = extractScopeBlock(body);
  if (block === null) return { ok: false, reason: "absent", detail: "no fenced yaml scope_version block found" };
  const scope: ReScope = { kind: "partial", intent: "", fingerprint: null, analyzedPaths: [], analyzedComponents: [], shallowPaths: [] };
  let section: "analyzed" | "shallow" | null = null;
  let list: "paths" | "components" | null = null;
  let sawKind = false;
  for (const raw of block.split("\n")) {
    const t = raw.trim();
    if (t === "" || t.startsWith("#")) continue;
    const indent = raw.length - raw.trimStart().length;
    if (indent === 0) {
      section = null;
      list = null;
      if (t.startsWith("scope_version:")) {
        const v = t.slice("scope_version:".length).trim();
        if (v !== "1") return { ok: false, reason: "malformed", detail: `unknown scope_version: ${v}` };
      } else if (t.startsWith("kind:")) {
        const k = t.slice("kind:".length).trim();
        if (k !== "full" && k !== "partial") return { ok: false, reason: "malformed", detail: `kind must be full|partial, got: ${k}` };
        scope.kind = k;
        sawKind = true;
      } else if (t.startsWith("intent:")) {
        scope.intent = t.slice("intent:".length).trim();
      } else if (t.startsWith("fingerprint:")) {
        const f = t.slice("fingerprint:".length).trim();
        scope.fingerprint = f === "" || f === "unknown" ? null : f;
      } else if (t === "analyzed:") section = "analyzed";
      else if (t === "shallow:") section = "shallow";
    } else if (section !== null && !t.startsWith("-") && t.endsWith(":")) {
      list = t === "paths:" ? "paths" : t === "components:" ? "components" : null;
    } else if (section !== null && list !== null && t.startsWith("-")) {
      const item = t.slice(1).trim();
      if (item === "") continue;
      if (section === "analyzed" && list === "paths") scope.analyzedPaths.push(item);
      else if (section === "analyzed" && list === "components") scope.analyzedComponents.push(item);
      else if (section === "shallow" && list === "paths") scope.shallowPaths.push(item);
    }
  }
  if (!sawKind) return { ok: false, reason: "malformed", detail: "missing kind: line" };
  if (scope.kind === "partial" && scope.analyzedPaths.length === 0)
    return { ok: false, reason: "malformed", detail: "kind: partial requires analyzed.paths entries" };
  if (scope.kind === "partial" && scope.analyzedPaths.includes("./"))
    return { ok: false, reason: "malformed", detail: "repository-root coverage (./) requires kind: full" };
  if (scope.kind === "full" && !scope.analyzedPaths.includes("./"))
    return { ok: false, reason: "malformed", detail: "kind: full requires repository-root coverage (analyzed.paths must include ./)" };
  return { ok: true, scope };
}

export function scopePathCovered(incoming: string[], storePath: string): boolean {
  return incoming.some((p) => p === storePath || (p.endsWith("/") && storePath.startsWith(p)));
}

// ---------------------------------------------------------------- fingerprints

// git write-tree over a temp index restricted to <paths> (working tree, ignored
// files excluded). null when not a git tree / invalid pathspec.
export function scopeFingerprint(repoDir: string, paths: string[], excludedPaths: string[] = []): string | null {
  if (paths.length === 0) return null;
  const norm = (p: string) => {
    let n = p.replaceAll("\\", "/").replace(/^(?:\.\/)+/, "").replace(/\/+$/, "");
    return n === "." ? "" : n;
  };
  const exclusionsN = excludedPaths.map(norm);
  const surviving = paths
    .map((original) => ({ original, n: norm(original) }))
    .filter(({ n }) => !exclusionsN.some((e) => e === n || n.startsWith(`${e}/`)));
  if (surviving.length === 0) return null;
  const exclusions = exclusionsN
    .filter((e) => surviving.some(({ n }) => n === "" || e.startsWith(`${n}/`)))
    .map((e) => `:(exclude,literal)${e}`);
  const inTree = spawnSync("git", ["rev-parse", "--is-inside-work-tree"], { cwd: repoDir, encoding: "utf-8" });
  if (inTree.status !== 0 || inTree.stdout.trim() !== "true") return null;
  const indexFile = join(tmpdir(), `.codekb-scope-index-${randomUUID()}`);
  const env = { ...process.env, GIT_INDEX_FILE: indexFile };
  try {
    const add = spawnSync("git", ["add", "-A", "--", ...surviving.map((s) => s.original), ...exclusions], { cwd: repoDir, env, encoding: "utf-8" });
    if (add.status !== 0) return null;
    const staged = spawnSync("git", ["ls-files", "-z"], { cwd: repoDir, env, encoding: "utf-8" });
    if (staged.status !== 0 || staged.stdout.length === 0) return null;
    const wt = spawnSync("git", ["write-tree"], { cwd: repoDir, env, encoding: "utf-8" });
    if (wt.status !== 0) return null;
    const hash = wt.stdout.trim();
    return /^[0-9a-f]{40,64}$/.test(hash) ? hash : null;
  } finally {
    try {
      unlinkSync(indexFile);
    } catch {
      /* inert */
    }
  }
}

function normalizeGenerationPath(path: string): string | null {
  const portable = path.trim().replaceAll("\\", "/");
  if (portable === "" || portable.startsWith("/") || /^[A-Za-z]:\//.test(portable) || /[*?[\]]/.test(portable)) return null;
  const segments = portable.split("/").filter((s) => s !== "" && s !== ".");
  if (segments.some((s) => s === "..")) return null;
  return segments.length === 0 ? "." : segments.join("/");
}

// byte-exact tree hash (non-git fallback + store generation)
function treeGeneration(rootDir: string, paths: string[], excludedPaths: string[] = []): string | null {
  const normalized = [...new Set(paths.map(normalizeGenerationPath))];
  if (normalized.includes(null) || normalized.length === 0) return null;
  const excludes = new Set([".git", ...excludedPaths].map(normalizeGenerationPath).filter((p): p is string => p !== null));
  const root = resolve(rootDir);
  const seen = new Set<string>();
  const hash = createHash("sha256");
  const isExcluded = (p: string) => [...excludes].some((e) => p === e || p.startsWith(`${e}/`));
  const visit = (abs: string, portable: string): boolean => {
    if (portable !== "." && isExcluded(portable)) return true;
    if (seen.has(portable)) return true;
    seen.add(portable);
    let st: ReturnType<typeof lstatSync>;
    try {
      st = lstatSync(abs);
    } catch {
      return false;
    }
    if (st.isSymbolicLink()) {
      hash.update(`L\0${portable}\0${readlinkSync(abs)}\0`);
      return true;
    }
    if (st.isDirectory()) {
      hash.update(`D\0${portable}\0`);
      let names: string[];
      try {
        names = readdirSync(abs).sort();
      } catch {
        return false;
      }
      for (const name of names) {
        const child = portable === "." ? name : `${portable}/${name}`;
        if (!visit(join(abs, name), child)) return false;
      }
      return true;
    }
    if (!st.isFile()) return false;
    hash.update(`F\0${portable}\0${st.size}\0`);
    hash.update(readFileSync(abs));
    hash.update("\0");
    return true;
  };
  for (const portable of normalized as string[]) {
    const abs = portable === "." ? root : resolve(root, ...portable.split("/"));
    const rel = relative(root, abs);
    if (rel.startsWith(`..${sep}`) || rel === ".." || isAbsolute(rel)) return null;
    hash.update(`S\0${portable}\0`);
    if (!visit(abs, portable)) return null;
  }
  return hash.digest("hex");
}

export function sourceFingerprint(repoDir: string, paths: string[], excludes: string[] = []): string | null {
  const git = scopeFingerprint(repoDir, paths, excludes);
  if (git !== null) return `git:${git}`;
  const tree = treeGeneration(repoDir, paths, excludes);
  return tree === null ? null : `tree:${tree}`;
}

export function storeGeneration(storeDir: string): string {
  if (!existsSync(storeDir)) return "none";
  const g = treeGeneration(storeDir, ["./"]);
  if (g === null) throw new Error(`cannot compute CodeKB store generation for ${storeDir}`);
  return `sha256:${g}`;
}

// ---------------------------------------------------------------- attempt & receipts

type Attempt = { id: string; started_at: string; intent: string; breadth?: string; decision?: string };
type Receipt = {
  event: "PIPELINE_LINK_COMPLETED" | "ARTIFACT_REUSED";
  attempt: string;
  repo: string;
  link?: Link;
  position?: string;
  artifact?: string;
  sha256?: string;
  mtime?: string;
  store_generation?: string;
  decision?: string;
  at: string;
};

function attemptPath(ctx: Ctx): string {
  return join(ctx.recordDir, "attempt.json");
}
function receiptsPath(ctx: Ctx): string {
  return join(ctx.recordDir, "receipts.jsonl");
}
function readAttempt(ctx: Ctx): Attempt | null {
  const p = attemptPath(ctx);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as Attempt;
  } catch {
    return null;
  }
}
function readReceipts(ctx: Ctx, attempt: string): Receipt[] {
  const p = receiptsPath(ctx);
  if (!existsSync(p)) return [];
  return readFileSync(p, "utf-8")
    .split("\n")
    .filter((l) => l.trim() !== "")
    .map((l) => JSON.parse(l) as Receipt)
    .filter((r) => r.attempt === attempt);
}
function appendReceipt(ctx: Ctx, r: Receipt): void {
  mkdirSync(ctx.recordDir, { recursive: true });
  appendFileSync(receiptsPath(ctx), `${JSON.stringify(r)}\n`);
}
function sha256Of(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function handleAttempt(ctx: Ctx, positional: string[], flags: Record<string, string>): void {
  const sub = positional[0];
  if (sub === "start") {
    mkdirSync(ctx.recordDir, { recursive: true });
    const attempt: Attempt = {
      id: randomUUID(),
      started_at: new Date().toISOString(),
      intent: flags.intent ?? `adhoc-${new Date().toISOString().slice(0, 10)}`,
      ...(flags.breadth ? { breadth: flags.breadth } : {}),
      ...(flags.decision ? { decision: flags.decision } : {}),
    };
    writeFileSync(attemptPath(ctx), `${JSON.stringify(attempt, null, 2)}\n`);
    // clear transient leftovers from an interrupted attempt
    rmSync(join(ctx.recordDir, ".stage"), { recursive: true, force: true });
    rmSync(join(ctx.recordDir, "scope-draft.md"), { force: true });
    process.stdout.write(
      flags.json === "true"
        ? `${JSON.stringify(attempt)}\n`
        : `ATTEMPT ${attempt.id}\nSTARTED_AT ${attempt.started_at}\nINTENT ${attempt.intent}\nRECORD ${relRecord(ctx)}\n`,
    );
    return;
  }
  if (sub === "status") {
    const attempt = readAttempt(ctx);
    if (!attempt) {
      process.stdout.write(flags.json === "true" ? `{"attempt":null,"completed":[],"reused":false}\n` : `NO_ATTEMPT: run \`attempt start\` first.\n`);
      return;
    }
    const receipts = readReceipts(ctx, attempt.id);
    const completed = receipts.filter((r) => r.event === "PIPELINE_LINK_COMPLETED").map((r) => r.link);
    const reused = receipts.some((r) => r.event === "ARTIFACT_REUSED" && r.decision === "keep");
    const payload = { attempt: attempt.id, intent: attempt.intent, breadth: attempt.breadth ?? null, decision: attempt.decision ?? null, completed, reused, links: LINKS };
    process.stdout.write(
      flags.json === "true"
        ? `${JSON.stringify(payload)}\n`
        : `ATTEMPT ${attempt.id}\nINTENT ${attempt.intent}\nDECISION ${attempt.decision ?? "-"}\nCOMPLETED ${completed.join(",") || "-"}\nREUSED ${reused}\nNEXT ${reused ? "-" : LINKS.find((l) => !completed.includes(l)) ?? "done"}\n`,
    );
    return;
  }
  die("attempt: use `attempt start` or `attempt status`");
}

function handleLink(ctx: Ctx, flags: Record<string, string>): void {
  const link = flags.link as Link | undefined;
  if (!link || !LINKS.includes(link)) die(`link: pass --link ${LINKS.join("|")}`);
  const attempt = readAttempt(ctx);
  if (!attempt) die("link: no current attempt; run `attempt start` first.");
  withLock(ctx, () => {
    const receipts = readReceipts(ctx, attempt.id);
    if (receipts.some((r) => r.event === "PIPELINE_LINK_COMPLETED" && r.link === link))
      die(`link: "${link}" already completed this attempt for repo "${ctx.repo}".`);
    const index = LINKS.indexOf(link);
    if (index > 0) {
      const prev = LINKS[index - 1];
      const prevReceipt = receipts.find((r) => r.event === "PIPELINE_LINK_COMPLETED" && r.link === prev);
      if (!prevReceipt) die(`link: "${link}" is out of order; position ${index + 1}/${LINKS.length} requires a current-attempt receipt for "${prev}".`);
      // edit-after-receipt invalidates upstream
      if (prevReceipt.artifact) {
        const abs = resolve(ctx.projectDir, prevReceipt.artifact);
        if (!existsSync(abs) || sha256Of(abs) !== prevReceipt.sha256)
          die(`link: upstream handoff ${prevReceipt.artifact} changed after its receipt; re-run the developer link (new attempt) before minting "${link}".`);
      }
    }
    const row: Receipt = { event: "PIPELINE_LINK_COMPLETED", attempt: attempt.id, repo: ctx.repo, link, position: `${index + 1}/${LINKS.length}`, at: new Date().toISOString() };
    if (link === "developer") {
      if (!flags.artifact) die(`link: pass --artifact ${relRecord(ctx)}developer-scan.md`);
      const expected = join(ctx.recordDir, "developer-scan.md");
      const artifact = resolve(ctx.projectDir, flags.artifact);
      if (artifact !== expected) die(`link: --artifact must resolve to ${relRecord(ctx)}developer-scan.md`);
      if (!existsSync(artifact)) die(`link: handoff file does not exist: ${flags.artifact}`);
      const st = lstatSync(artifact);
      if (!st.isFile() || st.isSymbolicLink()) die("link: handoff must be a regular file");
      if (st.mtimeMs < Date.parse(attempt.started_at)) die(`link: ${flags.artifact} was not written in the current stage attempt.`);
      const body = readFileSync(artifact, "utf-8");
      for (const h of ["## Developer Code Scan Results", "### Scan Coverage", "## Handoff Summary"]) {
        if (!body.includes(h)) die(`link: handoff is missing required heading "${h}"`);
      }
      row.artifact = relative(ctx.projectDir, artifact).replaceAll("\\", "/");
      row.sha256 = sha256Of(artifact);
      row.mtime = new Date(st.mtimeMs).toISOString();
    } else {
      // architect: the final link leaves the produces[] set complete in the store
      const missing = ARTIFACT_FILES.filter((f) => !existsSync(join(ctx.storeDir, f)));
      if (missing.length > 0) die(`link: store ${relStore(ctx)} is missing ${missing.join(", ")}; publish the candidate before minting the architect link.`);
      const parsed = parseReScope(readFileSync(join(ctx.storeDir, "reverse-engineering-timestamp.md"), "utf-8"));
      if (!parsed.ok) die(`link: store timestamp has an invalid Scope of Analysis block (${parsed.reason}: ${parsed.detail})`);
      row.store_generation = storeGeneration(ctx.storeDir);
    }
    appendReceipt(ctx, row);
    process.stdout.write(`PIPELINE_LINK_COMPLETED ${ctx.repo}:${link} ${row.position}\n`);
  });
}

function handleReuse(ctx: Ctx, flags: Record<string, string>): void {
  const attempt = readAttempt(ctx);
  if (!attempt) die("reuse: no current attempt; run `attempt start` first.");
  const missing = ARTIFACT_FILES.filter((f) => !existsSync(join(ctx.storeDir, f)));
  if (missing.length > 0) die(`reuse: cannot reuse ${relStore(ctx)}: missing ${missing.join(", ")}`);
  const verdict = statusVerdict(ctx);
  if (verdict.verdict !== "CURRENT") die(`reuse: store is ${verdict.verdict}, only a CURRENT store may be reused.`);
  appendReceipt(ctx, { event: "ARTIFACT_REUSED", attempt: attempt.id, repo: ctx.repo, decision: "keep", store_generation: storeGeneration(ctx.storeDir), at: new Date().toISOString() });
  attempt.decision = "reuse";
  writeFileSync(attemptPath(ctx), `${JSON.stringify(attempt, null, 2)}\n`);
  process.stdout.write(`ARTIFACT_REUSED ${ctx.repo} keep ${relStore(ctx)}\n`);
}

// ---------------------------------------------------------------- scope-diff

function statusVerdict(ctx: Ctx): Record<string, unknown> & { verdict: string } {
  const storePath = join(ctx.storeDir, "reverse-engineering-timestamp.md");
  if (!existsSync(storePath)) return { verdict: "NO_STORE" };
  const parsed = parseReScope(readFileSync(storePath, "utf-8"));
  if (!parsed.ok) return { verdict: "UNKNOWN_SCOPE", reason: parsed.reason, detail: parsed.detail };
  const store = parsed.scope;
  const current = store.analyzedPaths.length > 0 ? scopeFingerprint(ctx.repoDir, store.analyzedPaths, ctx.excludes) : null;
  if (store.fingerprint === null || current === null) {
    return { verdict: "UNVERIFIED", store_intent: store.intent, kind: store.kind, analyzed_paths: store.analyzedPaths, detail: store.fingerprint === null ? "store has no fingerprint" : "fingerprint not computable here" };
  }
  return { verdict: store.fingerprint === current ? "CURRENT" : "STALE", store_intent: store.intent, kind: store.kind, analyzed_paths: store.analyzedPaths, store_fingerprint: store.fingerprint, current_fingerprint: current };
}

function handleScopeDiff(ctx: Ctx, flags: Record<string, string>): void {
  const asJson = flags.json === "true";
  const emit = (payload: Record<string, unknown>, human: string) => {
    process.stdout.write(asJson ? `${JSON.stringify({ repo: ctx.repo, store: relStore(ctx), ...payload })}\n` : `${human}\n`);
  };
  if (flags.mint === "true") {
    const paths = splitPaths(flags, "scope-diff --mint");
    const fp = scopeFingerprint(ctx.repoDir, paths, ctx.excludes) ?? "unknown";
    process.stdout.write(asJson ? `${JSON.stringify({ repo: ctx.repo, fingerprint: fp, paths })}\n` : `${fp}\n`);
    return;
  }
  const storePath = join(ctx.storeDir, "reverse-engineering-timestamp.md");
  if (!existsSync(storePath)) {
    emit({ verdict: "NO_STORE" }, `NO_STORE: no reverse-engineering-timestamp.md at ${relStore(ctx)} - first scan, nothing to compare.`);
    return;
  }
  const parsed = parseReScope(readFileSync(storePath, "utf-8"));
  if (!parsed.ok) {
    emit({ verdict: "UNKNOWN_SCOPE", reason: parsed.reason, detail: parsed.detail }, `UNKNOWN_SCOPE (${parsed.reason}): ${parsed.detail}. The store predates scope tracking. A focused merge may retain its prose, but prior paths and components are not claimed as verified coverage until rescanned.`);
    return;
  }
  const store = parsed.scope;
  if (flags.compare !== undefined) {
    const incomingPath = flags.compare;
    if (!incomingPath || !existsSync(incomingPath)) die(`scope-diff --compare: file not found: ${incomingPath || "(missing path)"}`);
    const ip = parseReScope(readFileSync(incomingPath, "utf-8"));
    if (!ip.ok) {
      emit({ verdict: "UNKNOWN_SCOPE", reason: ip.reason, detail: `incoming: ${ip.detail}` }, `UNKNOWN_SCOPE (incoming ${ip.reason}): ${ip.detail}.`);
      return;
    }
    const incoming = ip.scope;
    const downgrade = store.kind === "full" && incoming.kind !== "full";
    const discardedPaths = incoming.kind === "full" ? [] : downgrade ? [...store.analyzedPaths] : store.analyzedPaths.filter((p) => !scopePathCovered(incoming.analyzedPaths, p));
    const discardedComponents = incoming.kind === "full" ? [] : store.analyzedComponents.filter((c) => !incoming.analyzedComponents.includes(c));
    const narrower = discardedPaths.length > 0 || discardedComponents.length > 0;
    const payload = { verdict: narrower ? "NARROWER" : "COVERS", store_intent: store.intent, incoming_intent: incoming.intent, discarded_paths: discardedPaths, discarded_components: discardedComponents };
    if (narrower) {
      emit(payload, `NARROWER: the incoming scope no longer claims verified deep coverage for:\n${discardedPaths.map((p) => `  - ${p}`).join("\n")}${discardedComponents.length > 0 ? `\n  components: ${discardedComponents.join(", ")}` : ""}\n(store intent: ${store.intent || "unrecorded"}; incoming intent: ${incoming.intent || "unrecorded"})`);
    } else emit(payload, "COVERS: the incoming scan covers everything the store analyzed.");
    return;
  }
  const v = statusVerdict(ctx);
  const lines = store.analyzedPaths.map((p) => `  - ${p}`).join("\n");
  if (v.verdict === "UNVERIFIED") {
    emit(v, `UNVERIFIED: the store (intent: ${store.intent || "unrecorded"}) analyzed:\n${lines}\nbut ${store.fingerprint === null ? "recorded no fingerprint" : "the current tree's fingerprint cannot be computed"} - freshness unknown.`);
    return;
  }
  emit(
    v,
    v.verdict === "CURRENT"
      ? `CURRENT: the analyzed paths are unchanged since the store was built (intent: ${store.intent || "unrecorded"}, coverage: ${store.kind}):\n${lines}`
      : `STALE: the analyzed paths have changed since the store was built (intent: ${store.intent || "unrecorded"}):\n${lines}`,
  );
}

// ---------------------------------------------------------------- snapshot / publish

function handleSnapshot(ctx: Ctx, flags: Record<string, string>): void {
  const paths = splitPaths(flags, "snapshot");
  const snap = withLock(ctx, () => {
    const fp = sourceFingerprint(ctx.repoDir, paths, ctx.excludes);
    if (fp === null) die(`snapshot: cannot fingerprint source paths: ${paths.join(", ")}`);
    return { repo: ctx.repo, store: relStore(ctx), paths, store_generation: storeGeneration(ctx.storeDir), source_fingerprint: fp };
  });
  process.stdout.write(
    flags.json === "true"
      ? `${JSON.stringify(snap)}\n`
      : `STORE_GENERATION ${snap.store_generation}\nSOURCE_FINGERPRINT ${snap.source_fingerprint}\nSOURCE_PATHS ${snap.paths.join(",")}\n`,
  );
}

function readCandidate(ctx: Ctx, stagedFlag: string | undefined): { files: Map<string, Buffer>; scope: ReScope } {
  if (!stagedFlag) die("publish: pass --staged <directory-containing-all-nine-artifacts>");
  const stagedPath = resolve(ctx.projectDir, stagedFlag);
  const rel = relative(ctx.projectDir, stagedPath);
  if (rel === "" || rel === ".." || rel.startsWith(`..${sep}`) || isAbsolute(rel)) die("publish: --staged must resolve inside the project directory");
  let st: ReturnType<typeof lstatSync>;
  try {
    st = lstatSync(stagedPath);
  } catch {
    die(`publish: staged directory not found: ${stagedFlag}`);
  }
  if (!st.isDirectory() || st.isSymbolicLink()) die("publish: --staged must be a real directory, not a symlink");
  const entries = readdirSync(stagedPath).sort();
  const required = [...ARTIFACT_FILES].sort();
  if (JSON.stringify(entries) !== JSON.stringify(required))
    die(`publish: staged directory must contain exactly the nine CodeKB artifacts; found: ${entries.join(", ") || "(empty)"}`);
  const files = new Map<string, Buffer>();
  for (const name of required) {
    const p = join(stagedPath, name);
    const s = lstatSync(p);
    if (!s.isFile() || s.isSymbolicLink()) die(`publish: staged artifact must be a regular file: ${name}`);
    files.set(name, readFileSync(p));
  }
  const parsed = parseReScope(files.get("reverse-engineering-timestamp.md")!.toString("utf-8"));
  if (!parsed.ok) die(`publish: staged reverse-engineering-timestamp.md has an invalid Scope of Analysis block (${parsed.reason}: ${parsed.detail})`);
  return { files, scope: parsed.scope };
}

function handlePublish(ctx: Ctx, flags: Record<string, string>): void {
  const expectedStore = flags["expect-store"];
  const expectedSource = flags["expect-source"];
  if (!expectedStore || !expectedSource) die("publish: pass --expect-store <generation> and --expect-source <fingerprint> from snapshot");
  const sourcePaths = splitPaths(flags, "publish");
  const candidate = readCandidate(ctx, flags.staged);
  for (const p of candidate.scope.analyzedPaths) {
    if (!sourcePaths.includes("./") && !scopePathCovered(sourcePaths, p))
      die(`publish: snapshot paths do not cover candidate analyzed path "${p}"; take a fresh snapshot over the complete candidate scope`);
  }
  const result = withLock(ctx, () => {
    const currentStore = storeGeneration(ctx.storeDir);
    if (currentStore !== expectedStore)
      die(`CODEKB_STORE_CHANGED: expected ${expectedStore}, found ${currentStore}. Re-read the current store, re-merge the staged scan, take a fresh snapshot, and retry.`);
    const currentSource = sourceFingerprint(ctx.repoDir, sourcePaths, ctx.excludes);
    if (currentSource === null || currentSource !== expectedSource)
      die(`CODEKB_SOURCE_CHANGED: expected ${expectedSource}, found ${currentSource ?? "unavailable"}. Re-scan the affected source, re-synthesize all nine artifacts, take a fresh snapshot, and retry.`);
    const candidateFp = scopeFingerprint(ctx.repoDir, candidate.scope.analyzedPaths, ctx.excludes);
    if (candidate.scope.fingerprint !== candidateFp && !(candidate.scope.fingerprint === null && candidateFp === null))
      die(`CODEKB_CANDIDATE_STALE: staged fingerprint ${candidate.scope.fingerprint ?? "unknown"} does not match the current source ${candidateFp ?? "unknown"}. Re-mint the timestamp and retry.`);
    const txn = join(ctx.recordDir, ".txn", `${process.pid}-${randomUUID()}`);
    const next = join(txn, "next");
    const backup = join(txn, "backup");
    mkdirSync(next, { recursive: true });
    try {
      for (const [name, bytes] of candidate.files) writeFileSync(join(next, name), bytes);
      mkdirSync(dirname(ctx.storeDir), { recursive: true });
      const had = existsSync(ctx.storeDir);
      if (had) renameSync(ctx.storeDir, backup);
      try {
        renameSync(next, ctx.storeDir);
      } catch (e) {
        if (had && existsSync(backup) && !existsSync(ctx.storeDir)) renameSync(backup, ctx.storeDir);
        throw e;
      }
      rmSync(backup, { recursive: true, force: true });
      return { repo: ctx.repo, published: relStore(ctx), generation: storeGeneration(ctx.storeDir) };
    } finally {
      rmSync(txn, { recursive: true, force: true });
      rmSync(join(ctx.recordDir, ".txn"), { recursive: true, force: true });
    }
  });
  process.stdout.write(flags.json === "true" ? `${JSON.stringify(result)}\n` : `PUBLISHED ${result.published} ${result.generation}\n`);
}

// ---------------------------------------------------------------- sensor (required-sections)

function h2s(body: string): string[] {
  const out: string[] = [];
  let inFence = false;
  for (const line of body.split(/\r?\n/)) {
    if (/^```/.test(line.trim())) inFence = !inFence;
    if (inFence) continue;
    const m = /^##\s+(.+?)\s*$/.exec(line);
    if (m) out.push(m[1].trim());
  }
  return out;
}

function handleSensor(flags: Record<string, string>): void {
  const dir = flags.dir;
  if (!dir) die("sensor: pass --dir <artifact directory>");
  const templatesDir = flags.templates ? resolve(flags.templates) : resolve(dirname(new URL(import.meta.url).pathname), "..", "templates");
  const findings: Record<string, unknown>[] = [];
  let pass = true;
  for (const name of ARTIFACT_FILES) {
    const p = join(dir, name);
    if (!existsSync(p)) {
      findings.push({ artifact: name, pass: false, reason: "missing" });
      pass = false;
      continue;
    }
    const body = readFileSync(p, "utf-8");
    const headings = h2s(body);
    const stem = name.replace(/\.md$/, "");
    const isMarker = stem === "reverse-engineering-timestamp";
    const tpl = join(templatesDir, name);
    let expected: string[] = [];
    let template = "none";
    if (!isMarker && existsSync(tpl)) {
      expected = h2s(readFileSync(tpl, "utf-8"));
      template = "applied";
    }
    const missing = expected.filter((h) => !headings.includes(h));
    const extraChecks: string[] = [];
    if (stem === "architecture" && !headings.some((h) => /interaction diagrams/i.test(h))) extraChecks.push("architecture.md must include an `## Interaction Diagrams` section");
    if (isMarker) {
      const parsed = parseReScope(body);
      if (!parsed.ok) extraChecks.push(`Scope of Analysis block ${parsed.reason}: ${parsed.detail}`);
    }
    const ok = headings.length >= 2 && missing.length === 0 && extraChecks.length === 0;
    if (!ok) pass = false;
    findings.push({ artifact: name, pass: ok, h2_count: headings.length, template, template_missing: missing, notes: extraChecks });
  }
  if (flags.json === "true") {
    process.stdout.write(`${JSON.stringify({ pass, severity: "advisory", findings })}\n`);
    return;
  }
  process.stdout.write(`required-sections (advisory): ${pass ? "PASS" : "FINDINGS"}\n`);
  for (const f of findings) {
    const line = f.pass ? `  ok   ${f.artifact} (${f.h2_count} H2${f.template === "applied" ? ", template" : ""})` : `  WARN ${f.artifact}: ${f.reason ?? ""}${(f.template_missing as string[] | undefined)?.length ? ` missing H2: ${(f.template_missing as string[]).join(" | ")}` : ""}${(f.notes as string[] | undefined)?.length ? ` ${(f.notes as string[]).join("; ")}` : ""}${(f.h2_count as number) < 2 ? " fewer than 2 H2 headings" : ""}`;
    process.stdout.write(`${line}\n`);
  }
}

// ---------------------------------------------------------------- main

const HELP = `codekb.ts — reverse-engineering CodeKB engine
  path            [--repo r]
  attempt start   [--repo r] [--intent slug] [--breadth full|focused] [--decision full|focused|reuse]
  attempt status  [--repo r] [--json]
  scope-diff      [--repo r] [--json]
  scope-diff      --mint --paths a/,b.ts [--repo r]
  scope-diff      --compare <timestamp.md> [--repo r] [--json]
  snapshot        --paths a/,b/ [--repo r] [--json]
  publish         --staged <dir> --paths <snapshot paths> --expect-store G --expect-source F [--repo r] [--json]
  link            --link developer --artifact codekb/.record/<repo>/developer-scan.md [--repo r]
  link            --link architect [--repo r]
  reuse           [--repo r]
  sensor          --dir <artifact dir> [--templates <dir>] [--json]
All verbs accept --project <dir> (default: cwd).`;

const { positional, flags } = parseArgs(process.argv.slice(2));
const verb = positional.shift();
switch (verb) {
  case "path": {
    const ctx = resolveCtx(flags);
    process.stdout.write(`${relStore(ctx)}\n`);
    break;
  }
  case "attempt":
    handleAttempt(resolveCtx(flags), positional, flags);
    break;
  case "scope-diff":
    handleScopeDiff(resolveCtx(flags), flags);
    break;
  case "snapshot":
    handleSnapshot(resolveCtx(flags), flags);
    break;
  case "publish":
    handlePublish(resolveCtx(flags), flags);
    break;
  case "link":
    handleLink(resolveCtx(flags), flags);
    break;
  case "reuse":
    handleReuse(resolveCtx(flags), flags);
    break;
  case "sensor":
    handleSensor(flags);
    break;
  case "help":
  case undefined:
    process.stdout.write(`${HELP}\n`);
    break;
  default:
    die(`unknown verb "${verb}"\n${HELP}`);
}
