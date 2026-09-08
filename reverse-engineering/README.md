# reverse-engineering — one core, many harnesses

AI-DLC(`aidlc-workflows`)의 `reverse-engineering` 스테이지를 단독 스킬로 발췌한
것입니다. brownfield 코드베이스를 스캔해 `codekb/<repo>/` 아래에 9개의 역공학
문서(business-overview, architecture, code-structure, api-documentation,
component-inventory, technology-stack, dependencies, code-quality-assessment,
reverse-engineering-timestamp)를 만들고, 재실행 시 기존 store 를
재사용/전체 재스캔/집중 스캔으로 병합합니다.

원본 저장소와 같은 방식으로 **하네스 중립 소스 하나**에서 **하네스별 배포
트리**를 생성합니다.

```
reverse-engineering/
├── core/                       # 하네스 중립 소스 (여기만 편집)
│   ├── SKILL.md                #   conductor: Step 1~5, {{SKILL_DIR}} 토큰 사용
│   ├── agents/                 #   developer / architect 페르소나 (name + description 만)
│   ├── knowledge/              #   스캔 가이드, 문서 템플릿 + Scope of Analysis 규칙, RE 체크리스트
│   ├── templates/              #   8개 prose 문서의 H2 골격
│   └── scripts/codekb.ts       #   결정적 툴: scope-diff / snapshot / publish / link / reuse / sensor
├── harness/<name>/             # 얇은 하네스 어댑터
│   ├── harness.json            #   설치 경로, 호출 방식, 에이전트 파일 포맷
│   ├── dispatch.md             #   이 하네스에서 링크를 위임하는 방법 (+ inline fallback)
│   └── question-rendering.md   #   구조화 질문 렌더링 (없으면 _shared/question-numbered.md)
├── build.ts                    # bun build.ts → dist/ ; bun build.ts --check 드리프트 가드
└── dist/<name>/, <name>-global/ # 생성물: 프로젝트 로컬 / 사용자 전역 배포판 (각 INSTALL.md 참고)
```

## 지원 하네스

하네스마다 **프로젝트 로컬** 배포판(`dist/<name>/`)과 **사용자 전역** 배포판
(`dist/<name>-global/`)이 함께 생성됩니다. 둘은 설치 경로만 다르고 내용은 같습니다.

| harness | 프로젝트 로컬 (스킬 / 에이전트) | 사용자 전역 (스킬 / 에이전트) | 위임 메커니즘 | 질문 렌더링 | 호출 |
|---|---|---|---|---|---|
| claude | `.claude/skills/reverse-engineering/` / `.claude/agents/*.md` | `~/.claude/skills/…` / `~/.claude/agents/` | Agent 툴 `subagent_type` | AskUserQuestion | `/reverse-engineering` |
| kiro | `.kiro/skills/…` / `.kiro/agents/*.json` + `.md` | `~/.kiro/skills/…` / `~/.kiro/agents/` | `subagent` 툴 (crew schema) | 번호 목록 | `/reverse-engineering` |
| kiro-ide | `.kiro/skills/…` / `.kiro/agents/*.md` (tools + permissions) | `~/.kiro/skills/…` / `~/.kiro/agents/` | `subagent` 툴 | 번호 목록 | `/reverse-engineering` |
| codex | `.agents/skills/…` / `.codex/agents/*.toml` + `.md` | `~/.codex/skills/…` / `~/.codex/agents/` | `spawn_agent` role | `request_user_input` → 번호 목록 | `$reverse-engineering` |
| cursor | `.cursor/skills/…` / `.cursor/agents/*.md` | `~/.cursor/skills/…` / `~/.cursor/agents/` | `task` 툴 | 번호 목록 | `/reverse-engineering` |
| opencode | `.opencode/skills/…` + `.opencode/command/` / `.opencode/agents/*.md` | `~/.config/opencode/skills/…` + `commands/` / `~/.config/opencode/agents/` | `task` 툴 | 번호 목록 | `/reverse-engineering` |
| copilot | `.github/skills/…` / `.github/agents/*.md` | `~/.copilot/skills/…` / `~/.copilot/agents/` | 커스텀 에이전트 호출 | 번호 목록 | `/reverse-engineering` |

모든 하네스의 `dispatch.md` 에 **inline fallback** 이 있습니다. 위임 툴이 없는
세션에서는 conductor 가 페르소나 파일과 지식을 직접 읽고 같은 파일(handoff,
스테이징 후보)을 쓰고 같은 영수증을 발급합니다.

## 설치

먼저 빌드합니다(소스를 편집했을 때만 필요, `dist/` 는 이미 생성되어 있음):

```bash
cd <이 폴더>
bun build.ts && bun build.ts --check
```

`dist/<harness>/` 안에는 하네스 디렉터리(`.claude/`, `.kiro/` …)가 **이미 포함**되어
있습니다. 따라서 복사 대상은 프로젝트 루트(전역은 홈 디렉터리)이며,
`cp -r dist/kiro/. project/.kiro` 처럼 하네스 디렉터리를 한 번 더 붙이면
`.kiro/.kiro/` 가 되어 동작하지 않습니다. 아래 명령은 각 dist 의 하네스 디렉터리만
골라 병합합니다(`cp -R` 은 기존 디렉터리와 병합하고 같은 이름의 파일만 덮어씁니다).
각 dist 루트의 `INSTALL.md` 는 안내문이므로 복사하지 않아도 됩니다.

같은 하네스의 로컬 배포판과 전역 배포판을 한 머신에 함께 두면, 하네스가 이름
충돌 시 **워크스페이스(프로젝트) 쪽을 우선**합니다(Claude Code, Kiro, Cursor,
Copilot, opencode 공통). SKILL.md 안의 스크립트 경로는 배포판마다 고정되어 있으므로
로컬 스킬이 전역 스크립트를 가리키는 식으로 섞이지는 않습니다.

전제: `bun`, `git` 이 PATH 에 있어야 합니다.

### Claude Code

```bash
# 프로젝트 로컬
cp -R dist/claude/.claude /path/to/project/
# 사용자 전역
cp -R dist/claude-global/.claude ~/
```

- 스킬 `…/skills/reverse-engineering/`, 서브에이전트 `…/agents/re-developer-agent.md`, `re-architect-agent.md`
- 호출: 프로젝트 루트에서 `/reverse-engineering <이 코드베이스에서 하려는 일>`

### Kiro CLI

```bash
# 프로젝트 로컬
cp -R dist/kiro/.kiro /path/to/project/
# 사용자 전역
cp -R dist/kiro-global/.kiro ~/
```

- 스킬 `…/skills/reverse-engineering/`, 커스텀 에이전트 `…/agents/re-*.json` + `.md`
  (`allowedCommands` 는 `codekb.ts`, 읽기 전용 `git`, `date` 만 허용, 쓰기는 `codekb/**` 만)
- 에이전트의 `resources` 가 스킬 지식을 `file://` 로 직접 참조하므로 Kiro 커스텀
  에이전트가 스킬을 자동 로드하지 않는 제약과 무관하게 동작합니다.
- 호출: `/reverse-engineering <설명>`

### Kiro IDE

```bash
# 프로젝트 로컬
cp -R dist/kiro-ide/.kiro /path/to/project/
# 사용자 전역
cp -R dist/kiro-ide-global/.kiro ~/
```

- 스킬 `…/skills/reverse-engineering/`, 에이전트 `…/agents/re-*.md` (frontmatter `tools` + `permissions`)
- Kiro CLI 와 IDE 를 함께 쓰면 두 배포판이 같은 `skills/` 경로를 공유합니다. 스킬
  파일은 동일하고 에이전트 파일만 포맷이 다르므로 둘 다 복사해도 충돌하지 않습니다.
- IDE 는 `~/.kiro/` 아래 디렉터리 심볼릭 링크를 따라가지 않으므로 전역 설치는 실제
  복사로 하세요.
- 호출: `/reverse-engineering <설명>`

### Codex CLI

```bash
# 프로젝트 로컬
cp -R dist/codex/.agents dist/codex/.codex /path/to/project/
# 사용자 전역
cp -R dist/codex-global/.codex ~/
```

- 로컬: 스킬 `.agents/skills/reverse-engineering/`, 에이전트 role `.codex/agents/re-*.toml` (+ `.md`)
- 전역: 스킬 `~/.codex/skills/reverse-engineering/`, 에이전트 role `~/.codex/agents/re-*.toml`
- 호출: `$reverse-engineering <설명>`
- 구조화 질문에 `request_user_input` 을 쓰려면 `config.toml` 에
  `[tools] experimental_request_user_input = { enabled = true }` 가 필요합니다. 없으면
  번호 목록으로 렌더됩니다. 멀티 에이전트 spawn 이 꺼져 있으면 `dispatch.md` 의
  inline fallback 으로 동작합니다.

### Cursor

```bash
# 프로젝트 로컬
cp -R dist/cursor/.cursor /path/to/project/
# 사용자 전역
cp -R dist/cursor-global/.cursor ~/
```

- 스킬 `…/skills/reverse-engineering/`, 서브에이전트 `…/agents/re-*.md`
  (frontmatter `name` 으로 자동 탐색, `task` 툴로 위임)
- 호출: `/reverse-engineering <설명>`

### opencode

```bash
# 프로젝트 로컬
cp -R dist/opencode/.opencode /path/to/project/
# 사용자 전역
cp -R dist/opencode-global/.config ~/
```

- 로컬: 스킬 `.opencode/skills/reverse-engineering/`, 커맨드 `.opencode/command/reverse-engineering.md`,
  서브에이전트 `.opencode/agents/re-*.md` (`mode: subagent`, `permission.task: deny`)
- 전역: `~/.config/opencode/skills/…`, `~/.config/opencode/commands/reverse-engineering.md`,
  `~/.config/opencode/agents/re-*.md`
- 호출: `/reverse-engineering <설명>` (커맨드가 SKILL.md 를 읽어 conductor 로 동작)

### GitHub Copilot

```bash
# 프로젝트 로컬
cp -R dist/copilot/.github /path/to/project/
# 사용자 전역
cp -R dist/copilot-global/.copilot ~/
```

- 로컬: 스킬 `.github/skills/reverse-engineering/`, 커스텀 에이전트 `.github/agents/re-*.md`
- 전역: `~/.copilot/skills/reverse-engineering/`, `~/.copilot/agents/re-*.md`
  (`copilot skill add dist/copilot-global/.copilot/skills/reverse-engineering` 으로 등록해도 됩니다)
- 로컬 설치는 이미 `.github/` 가 있는 저장소에서도 `skills/` 와 `agents/` 하위만 추가하며
  워크플로 파일은 건드리지 않습니다.
- 호출: `/reverse-engineering <설명>`

### 설치 확인 (모든 하네스 공통)

```bash
cd /path/to/project
bun <스킬 경로>/scripts/codekb.ts help        # 예: bun .kiro/skills/reverse-engineering/scripts/codekb.ts help
bun <스킬 경로>/scripts/codekb.ts scope-diff  # 첫 실행이면 NO_STORE
```

전역 설치라면 `<스킬 경로>` 가 `~/.kiro/skills/reverse-engineering` 처럼 홈 기준이
됩니다. 각 배포판의 SKILL.md 상단 Conventions 절에 그 배포판의 정확한 경로가 적혀 있습니다.

### 제거

설치한 스킬 디렉터리 `…/skills/reverse-engineering/` 와 에이전트 파일
`…/agents/re-developer-agent.*`, `…/agents/re-architect-agent.*` 를 지우면 됩니다
(opencode 는 `command(s)/reverse-engineering.md` 포함, Codex 로컬은
`.agents/skills/reverse-engineering/` 와 `.codex/agents/re-*`). 생성된 지식 베이스
`codekb/` 는 별도이므로 필요하면 남겨 두세요.

## 원본 대비 바뀐 점

| 원본 (aidlc-workflows) | 이 스킬 |
|---|---|
| `aidlc/spaces/<space>/codekb/<repo>/` | `codekb/<repo>/` |
| `<record>/inception/reverse-engineering/` | `codekb/.record/<repo>/` |
| `aidlc-utility.ts codekb-scope-diff / -snapshot / -publish / -path` | `codekb.ts scope-diff / snapshot / publish / path` |
| `aidlc-log.ts link` (감사 이벤트) | `codekb.ts link` (receipts.jsonl) |
| `aidlc-state.ts reuse-artifact` | `codekb.ts reuse` |
| `aidlc-orchestrate.ts report` (라이프사이클) | 없음 — `attempt status` + 승인 질문 |
| intent 는 intents.json 에서 읽음 | `--intent` 또는 인자에서 슬러그 도출 |
| 하네스별 SKILL.md 를 손으로 작성 | SKILL.md 는 중립, 하네스 차이는 `dispatch.md` / `question-rendering.md` 두 annex 로 격리 |

재실행 가드의 5가지 판정, 재사용/전체/집중 질문, 스냅샷 → 스캔 → 합성 →
compare → CAS publish, 링크 영수증 순서 강제, NARROWER 경고, focused 병합 시
analyzed/shallow 강등 규칙은 원본과 동일합니다.

## 알려진 한계

- brownfield 판정은 SKILL.md 의 프로즈 규칙입니다. 빈 레포에서 conductor 가
  규칙을 무시하면 툴은 막지 않고 거의 빈 문서 9개를 `fingerprint: unknown`
  으로 발행하며, 다음 실행은 UNVERIFIED 가 됩니다.
- Kiro/Codex 의 에이전트 권한(허용 명령, 쓰기 경로)은 보수적으로 잡았습니다.
  스캔 중 다른 셸 명령이 필요하면 하네스가 확인을 요청합니다.
