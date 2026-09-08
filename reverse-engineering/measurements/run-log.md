# 측정 로그

측정 대상 코드베이스: `examples/ticket-triage/` (제출본에서는 스킬 실행 결과 `codekb/` 와 대조군 `docs-baseline/` 이 같은 폴더에 있음) — 23 파일 / 433 LOC Python 서비스
(FastAPI API + Redis 큐 워커 + 공유 도메인 패키지, 의도적 결함 포함).
각 런은 이 레포의 독립 복사본에서 수행.

## Run A — AFTER #1 (스킬, depth Standard)
| 링크 | 소요 | 서브에이전트 토큰 | 툴 호출 |
|---|---|---|---|
| link 1 developer (스캔) | 155.8s | 53,081 | 13 |
| link 2 architect (합성·발행) | 510.5s | 94,245 | 22 |
| **합계** | **666.3s (11분 6초)** | **147,326** | **35** |

게이트 결과: `COMPLETED developer,architect` / sensor `PASS` /
publish `sha256:1d81bf29…` (CAS 충돌 없음).

## Run B — AFTER #2 (스킬, depth Comprehensive)
독립 실행. 별도 에이전트가 같은 스킬을 자율적으로 발견해 실행한 결과이며,
스킬 산출물의 재현성 확인용으로 채택.

| 소요 | 토큰 | 툴 호출 |
|---|---|---|
| 1,437.7s (23분 58초) | 163,209 | 706 |

게이트 결과: `COMPLETED developer,architect` / sensor `PASS`.

## Run C — BEFORE (대조군, 스킬 없음)
동일 코드베이스, 동일 요청 문구, 스킬을 `~/.claude/skills`에서 격리한 상태로 실행.
→ 결과는 `baseline.json` (문서 4개 / 513줄, Mermaid 0, 파일 인용 10, 정규 산출물 0). `docs/README.md` 가 04~09 문서를 링크하지만 파일은 생성되지 않았다.

## Run D — 재실행 가드 (결정적, LLM 불필요)
`measurements/guard-demo.sh` — 출력은 `measurements/rerun-guard.txt`.
CURRENT → (소스 1파일 추가) → STALE → NARROWER 경고 →
CODEKB_STORE_CHANGED / CODEKB_SOURCE_CHANGED 거부 → store 무손상.
