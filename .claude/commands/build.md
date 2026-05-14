# /build — Edith 빌드 하네스 워크플로우

Edith feature를 step 단위로 분해해 `phases/`에 적고, `scripts/execute.py`로 실행한다.
설계 전문: `docs/05_cc_harness.md`.

인자: `$ARGUMENTS` — 만들 task 한 줄 설명 (없으면 사용자에게 물어볼 것).

## Phase A — Exploration
`docs/01_strategy.md`·`docs/02_roadmap.md`·`docs/05_cc_harness.md`·`docs/06_design_backlog.md`와
관련 `harness/` 코드를 읽어 현재 상태를 파악한다. 넓은 탐색은 Explore 에이전트 병렬로.

## Phase B — Discussion
구현 전 **결정이 갈리는 지점**을 사용자에게 올린다. 합의 없이 Phase C로 가지 말 것.

## Phase C — Step Design (7+2 원칙)
PR 크기 step으로 분해. 각 step은:
1. 한 레이어/모듈만  2. self-contained (독립 세션이 step 파일만 읽고 작업 가능)
3. 선행조건을 경로로 명시  4. 시그니처만, 구현은 위임  5. 검증은 실행 가능한 명령
6. 주의사항은 "X 하지 마라 — Y 때문에"  7. kebab-case slug
8. (E1) feature step은 eval YAML을 step 1로  9. (E2) scope를 명시

## Phase D — File Creation
```
phases/index.json                  — 전체 task 목록
phases/<task-slug>/index.json       — step 배열 + 상태
phases/<task-slug>/step{N}.md       — 선행조건·작업·수용기준·검증·하지말것
```
`phases/b4-golden-evals/`를 레퍼런스로 삼을 것.

## Phase E — Execution
```
python scripts/execute.py <task-slug> --dry-run   # 실행 계획만 확인
python scripts/execute.py <task-slug>             # 실제 실행
```
executor가 가드레일(CLAUDE.md+identity.md) 주입·컨텍스트 누적·3회 재시도·step별 커밋을 처리.
실행 전 사용자에게 dry-run 결과를 보여주고 승인받을 것.
