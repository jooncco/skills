# skills

개인용 [Claude Code](https://claude.com/claude-code) 스킬 모음.

스킬 하나가 디렉터리 하나다. `.claude/skills/` 가 기대하는 모양 그대로라
심볼릭 링크만 걸면 바로 동작한다.

```
skills/
├── install.sh              # 스킬을 프로젝트에 링크
└── <skill-name>/
    ├── SKILL.md            # 진입점. frontmatter + 절차
    ├── reference/          # 템플릿·표 등 실행 중 읽는 자료
    └── scripts/            # 실행 파일. uv 인라인 의존성으로 자립
```

## 설치

```bash
./install.sh trading-journal              # 현재 프로젝트의 .claude/skills 에
./install.sh trading-journal --global     # ~/.claude/skills 에 (모든 프로젝트)
./install.sh trading-journal ~/work/repo  # 지정한 프로젝트에
```

복사가 아니라 **링크**다. 여기서 `git pull` 하면 링크된 모든 프로젝트가 같이
갱신된다. 복사본을 뿌리면 프로젝트마다 설치 시점의 리비전에 멈춰 있고, 어느 것이
어느 버전인지 알 방법이 없다.

이미 무언가 있는 자리에는 덮어쓰지 않고 멈춘다.

## 스킬

### trading-journal

하루치 매매를 복기 노트로 만든다. `/trading-journal 2026-09-07`

바탕화면의 MT5 스냅샷과 거래 내역을 대조해 거래에 번호를 매기고, 진입·청산 화살표가
보이도록 잘라낸 차트 이미지를 붙여 마크다운 일지를 저장한 뒤, 네이버 카페 글쓰기
화면을 채운 채로 멈춘다.

**핵심은 좌표를 사람이 찍지 않는다는 것.** 스크린샷의 축 라벨을 그리드선에 손으로
짝지으면 한 칸 틀렸을 때 배지가 통째로 밀리는데, 그림은 여전히 멀쩡해 보인다.
조용히 틀리는 실패다. 그래서 축 눈금(분/px, 가격/px)만 받고 **오프셋은 MT5 가 이미
그려둔 체결 화살표에서 역산한다** — 매수 `(58,130,247)`, 매도 `(221,83,62)`.
렌더할 때마다 배지가 실제 화살표 위에 있는지 검증해서 `matched 2/2` 로 보고한다.

| 파일 | 하는 일 |
|---|---|
| `scripts/fetch_trades.py` | 플랫폼 dashboard API 에서 KST 하루치 라운드트립을 받아 시간순 채번. sync 지연도 같이 경고 |
| `scripts/probe_axes.py` | 스크린샷의 그리드 주기를 검출. 대시가 성겨 임계값으로는 안 잡히므로 주기·위상으로 찾는다 |
| `scripts/annotate_chart.py` | 크롭 + 번호 배지. 축 역산, 배지 충돌 회피, 볼린저 밴드가 프레임에 들어올 때까지 세로 확장 |
| `scripts/build_specs.py` | 거래번호만 주면 스펙 생성부터 렌더까지. 축은 스냅샷당 한 번 풀고 재사용 |

일지 구조 — `근거` 칸과 `오답노트` 는 **비워 둔다.** 스킬이 채우면 그건 복기가
아니라 추측이다.

```
> 13건 · 8승 5패 · 합계 +84.2
## 매매 내역   # | 진입시각 | 진입가 | 방향 | 홀딩 | 청산시각 | 청산가 | 손익 | 근거
## 차트        ### #1 … ### #13   (거래 1건당 1장)
## 오답노트
```

**필요한 것**

- macOS — 바탕화면 스냅샷, 시스템 한글 폰트를 쓴다
- [`uv`](https://docs.astral.sh/uv/) — 스크립트가 PEP 723 인라인 의존성으로 Pillow 를
  가져온다. 가상환경을 따로 만들 필요 없다
- MT5 모바일 스냅샷 — 매매 History 1장 + 진입·청산 화살표가 찍힌 캔들 차트 여러 장
- [billion-dollar-baby](https://github.com/jooncco/billion-dollar-baby) 백엔드가
  `127.0.0.1:8000` 에 떠 있을 것. 거래 숫자는 여기서 온다

**설정** — `~/.claude/trading-journal.json`

```json
{
  "journal_dir": "…/notes/PROJECT/2026-07-BILLION-DOLLAR-BABY",
  "account_id": "hantec",
  "api": "http://127.0.0.1:8000",
  "cafe_url": "https://cafe.naver.com/…"
}
```

`journal_dir` 은 매 실행마다 기본값으로 제시되고, 다른 경로를 고르면 갱신된다.

**게시는 등록 직전까지만 한다.** 로그인된 Chrome 으로 글쓰기 화면을 채우고 멈춘다.
등록 버튼은 사람이 누른다 — 계정 정보를 다루지 않고, 나가기 전에 눈으로 확인할 수
있다.

## 스킬 추가하기

디렉터리를 만들고 `SKILL.md` 에 frontmatter 를 쓴다:

```markdown
---
name: my-skill
description: 언제 이 스킬을 쓰는지. Claude 가 이 문장만 보고 발동을 판단한다
user-invocable: true
allowed-tools: [Read, Write, Edit, Bash]
---
```

실행 파일은 `scripts/` 에 두고 자립시킨다 — `uv run --script` 셔뱅과 인라인
의존성이면 설치 절차가 없다.

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10.0"]
# ///
```
