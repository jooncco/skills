# skills

개인용 [Claude Code](https://claude.com/claude-code) 스킬 모음.

스킬 하나가 디렉터리 하나다. `.claude/skills/` 가 기대하는 모양 그대로라
심볼릭 링크만 걸면 바로 동작한다.

## 수록된 스킬

| 스킬 | 하는 일 |
|---|---|
| [`trading-journal`](trading-journal/) | 하루치 매매 스냅샷과 거래 내역으로 복기 노트를 만든다 |
| [`reverse-engineering`](reverse-engineering/) | brownfield 코드베이스를 스캔해 `codekb/` 아래에 역공학 문서 9종을 만든다. 하네스 중립 `core/` 에서 Claude·Kiro·Codex·Cursor·opencode·Copilot 배포판을 생성하는 다중 하네스 번들 |

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

`reverse-engineering` 은 예외다. 루트에 `SKILL.md` 가 없고 `core/` 소스에서 하네스별
`dist/` 를 생성하는 구조라 `install.sh` 로 링크할 수 없다. 설치는 해당 디렉터리의
`README.md` 대로 `dist/<harness>/` 안의 하네스 디렉터리를 프로젝트 루트(또는 홈)에
`cp -R` 로 병합한다.

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

스킬은 링크로 설치되므로 **어느 프로젝트에서 실행될지 모른다.** 그 프로젝트에
`.venv` 가 있는지, 거기에 필요한 패키지가 깔려 있는지 알 수 없다. 그러니 스크립트가
필요한 것을 스스로 챙기게 만든다.

파이썬이라면 [`uv`](https://docs.astral.sh/uv/) 가 이걸 두 줄로 해결한다:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0"]
# ///

from PIL import Image   # 설치한 적 없어도 그냥 된다
```

**첫 줄이 셔뱅(shebang)이다.** 파일을 실행하면 OS 가 맨 앞 두 글자 `#!` 를 보고,
그 줄의 나머지를 "이 파일을 처리할 명령"으로 삼는다.

| 조각 | 뜻 |
|---|---|
| `#!` | "아래 명령으로 이 파일을 실행해라". 반드시 **1번째 줄**이어야 한다 |
| `/usr/bin/env` | 프로그램을 `PATH` 에서 찾아준다. `uv` 가 어디 깔렸든 상관없어진다 |
| `-S` | 뒤에 인자를 여러 개 넘기게 해준다. 없으면 `env` 가 `"uv run --script"` 전체를 프로그램 **이름 하나**로 읽고 실패한다 |
| `uv run --script` | 아래 `# /// script` 블록을 읽어 임시 환경을 만들고 실행한다 |

그 아래 주석 블록이 [PEP 723](https://peps.python.org/pep-0723/) 형식의 의존성
선언이다. 파이썬 버전과 필요한 패키지를 파일 안에 적어두면, uv 가 실행할 때마다
맞는 환경을 준비한다(한 번 받아두면 캐시된다).

결과적으로 이렇게 된다:

```bash
chmod +x scripts/my_script.py   # 한 번만
./scripts/my_script.py          # 끝. python 도, pip install 도, venv 활성화도 없다
```

`requirements.txt` 도, 설치 안내도, "먼저 가상환경을 만드세요" 도 필요 없다.
의존성이 코드 바로 위에 있으니 서로 어긋날 일도 없다.

### 지켜야 할 것

- **경로를 스킬 위치 기준으로 잡는다.** 링크로 설치되므로 실행 시점의 작업
  디렉터리는 프로젝트마다 다르다
- **조용히 덮어쓰지 않는다.** 사용자가 채워 넣은 내용이 있을 수 있는 산출물은
  덮어쓰기 전에 읽고 확인한다
- **밖으로 나가는 동작은 사람이 누르게 한다.** 게시·전송·배포는 준비까지만 하고
  멈춘다
- **추측을 산출물에 적지 않는다.** 사용자가 판단할 자리는 비워 둔 채로 남긴다
