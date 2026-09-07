# skills

개인용 [Claude Code](https://claude.com/claude-code) 스킬 모음.

스킬 하나가 디렉터리 하나다. `.claude/skills/` 가 기대하는 모양 그대로라
심볼릭 링크만 걸면 바로 동작한다.

## 수록된 스킬

| 스킬 | 하는 일 |
|---|---|
| [`trading-journal`](trading-journal/) | 하루치 매매 스냅샷과 거래 내역으로 복기 노트를 만든다 |

각 스킬의 상세 사용법·필요 조건·설정은 해당 디렉터리의 `README.md` 에 있다.

## 설치

```bash
./install.sh trading-journal              # 현재 프로젝트의 .claude/skills 에
./install.sh trading-journal --global     # ~/.claude/skills 에 (모든 프로젝트)
./install.sh trading-journal ~/work/repo  # 지정한 프로젝트에
```

복사가 아니라 **링크**다. 여기서 `git pull` 하면 링크된 모든 프로젝트가 같이
갱신된다. 복사본을 뿌리면 프로젝트마다 설치 시점의 리비전에 멈춰 있고, 어느 것이
어느 버전인지 알 방법이 없다.

이미 무언가 있는 자리에는 덮어쓰지 않고 멈춘다 — 사람이 손댄 사본은 이 스크립트가
되돌릴 수 없는 유일한 것이다.

인자 없이 실행하면 사용법과 스킬 목록이 나온다.

## 레이아웃

```
skills/
├── install.sh
└── <skill-name>/
    ├── SKILL.md            # 진입점. frontmatter + Claude 가 따를 절차
    ├── README.md           # 사람이 읽는 설명. 무엇을·왜·무엇이 필요한지
    ├── reference/          # 실행 중 읽는 자료 (템플릿, 표, 체크리스트)
    └── scripts/            # 실행 파일
```

`SKILL.md` 와 `README.md` 는 독자가 다르다. `SKILL.md` 는 Claude 가 실행할 절차이고,
`README.md` 는 이 스킬을 쓸지 판단하려는 사람을 위한 것이다. 절차를 README 에
복사하지 않는다 — 둘은 반드시 갈라진다.

## 스킬 추가하기

디렉터리를 만들고 `SKILL.md` 에 frontmatter 를 쓴다:

```markdown
---
name: my-skill
description: 언제 이 스킬을 쓰는지. Claude 가 이 문장만 보고 발동을 판단하므로,
  기능이 아니라 사용자가 쓸 법한 표현을 담는다
user-invocable: true
allowed-tools: [Read, Write, Edit, Bash]
---
```

`description` 이 이 파일에서 가장 중요한 줄이다. 나머지 본문은 발동이 결정된 뒤에야
읽히므로, 여기가 부실하면 스킬은 존재하지 않는 것과 같다.

### 스크립트는 자립시킨다

`uv run --script` 셔뱅과 PEP 723 인라인 의존성을 쓰면 설치 절차도, 가상환경도
필요 없다. 링크된 어느 프로젝트에서 실행되든 동작해야 하므로, 특정 프로젝트의
`.venv` 나 전역 패키지에 기대지 않는다.

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0"]
# ///
```

### 지켜야 할 것

- **경로를 스킬 위치 기준으로 잡는다.** 링크로 설치되므로 실행 시점의 작업
  디렉터리는 프로젝트마다 다르다
- **조용히 덮어쓰지 않는다.** 사용자가 채워 넣은 내용이 있을 수 있는 산출물은
  덮어쓰기 전에 읽고 확인한다
- **밖으로 나가는 동작은 사람이 누르게 한다.** 게시·전송·배포는 준비까지만 하고
  멈춘다
- **추측을 산출물에 적지 않는다.** 사용자가 판단할 자리는 비워 둔 채로 남긴다
