# step3 · jd-golden

jd skill (F9 `jd_analyze` tool)에 golden eval 케이스를 추가한다.

## 선행조건 (읽을 것)
- `docs/05_cc_harness.md`
- `harness/tools/jd.py` — `jd_analyze` tool의 input_schema·반환 형식
- `harness/skills/jd.py` — 현재 `eval_globs=[]`, `scope="personal"` skill manifest
- `evals/golden/f6_recall.yaml` — golden 형식 레퍼런스
- `tests/test_jd.py` — jd_analyze 입력 참고
- step1/step2 산출물 — 같은 패턴

## 작업
1. `evals/golden/f9_jd.yaml` 생성. `jd_analyze` tool을 runtime을 통해 호출하는 golden.
   **주의**: jd skill은 `scope="personal"` — golden의 `inputs.scope`를 `personal`로 둘 것
   (work로 두면 R3 정책에 막혀 `policy_blocks: 1`이 됨).
2. `harness/skills/jd.py`의 `eval_globs`에 `"evals/golden/f9_jd.yaml"` 추가.

## 수용 기준
- `f9_jd.yaml`이 동일한 키 구조, `inputs.scope: personal`
- `inputs.llm_responses`가 `jd_analyze` tool_use 1회 + end_turn 1회
- `expected`에 `tool_calls_made: 1`, `policy_blocks: 0` 포함

## 검증
```
uv run harness eval
uv run pytest -q
uv run ruff check harness tests
```
전체 골든 통과 + 전체 테스트 통과 + lint 클린. (이 step이 task의 마지막 —
전체 CI 게이트를 돌린다.)

## 하지 말 것
- `harness/tools/jd.py` 로직 수정 금지.
- step1/step2 산출물 수정·삭제 금지.
- `inputs.scope`를 personal 외 값으로 두지 말 것 — R3에 막힘.
