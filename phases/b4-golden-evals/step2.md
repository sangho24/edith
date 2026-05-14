# step2 · repo-golden

repo skill (F7 `pr_review` tool)에 golden eval 케이스를 추가한다.

## 선행조건 (읽을 것)
- `docs/05_cc_harness.md`
- `harness/tools/pr.py` — `pr_review` tool의 input_schema·반환 형식
- `harness/skills/repo.py` — 현재 `eval_globs=[]` 인 skill manifest
- `evals/golden/f6_recall.yaml` — golden 형식 레퍼런스
- `tests/test_pr_review.py` — pr_review가 어떤 입력을 받는지 참고
- step1 산출물 `evals/golden/f8_paper.yaml` — 같은 패턴을 따른다

## 작업
1. `evals/golden/f7_pr_review.yaml` 생성. `pr_review` tool을 runtime을 통해 호출하는
   golden. fixtures로 diff 등 필요한 입력을 제공.
2. `harness/skills/repo.py`의 `eval_globs`에 `"evals/golden/f7_pr_review.yaml"` 추가.

## 수용 기준
- `f7_pr_review.yaml`이 f8_paper.yaml과 동일한 키 구조
- `inputs.llm_responses`가 `pr_review` tool_use 1회 + end_turn 1회
- `expected`에 `tool_calls_made: 1`, `policy_blocks: 0` 포함

## 검증
```
uv run harness eval --pattern 'f7_*.yaml'
uv run pytest tests/test_skills.py -q
```

## 하지 말 것
- `harness/tools/pr.py` 로직 수정 금지.
- papers/jd skill의 eval_globs 건드리지 말 것.
- step1이 만든 `f8_paper.yaml`을 수정·삭제하지 말 것.
