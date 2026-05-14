# step1 · papers-golden

papers skill (F8 `paper_triage` tool)에 golden eval 케이스를 추가한다.

## 선행조건 (읽을 것)
- `docs/05_cc_harness.md` — 빌드 하네스 step 작성 규약
- `harness/tools/paper.py` — `paper_triage` tool의 input_schema·반환 형식
- `harness/skills/papers.py` — 현재 `eval_globs=[]` 인 skill manifest
- `evals/golden/f6_recall.yaml` — runtime을 통한 tool 호출 golden의 형식 레퍼런스
- `harness/eval.py` — `_check_expected`가 지원하는 expected 키 (finalize_reason, n_steps, tool_calls_made, policy_blocks, output_contains, files_created, files_contain)

## 작업
1. `evals/golden/f8_paper.yaml` 생성. `paper_triage` tool을 runtime을 통해 호출하는
   golden 케이스. fixtures로 필요한 입력(arxiv URL 등)을 제공하고, MockLLM 응답 2개
   (tool_use → end_turn)를 구성한다. f6_recall.yaml의 구조를 그대로 따른다.
2. `harness/skills/papers.py`의 `eval_globs`에 `"evals/golden/f8_paper.yaml"` 추가.

## 수용 기준
- `f8_paper.yaml`이 `id`, `phase`, `component`, `fixtures`, `inputs`, `expected` 키를 가짐
- `inputs.llm_responses`가 `paper_triage` tool_use 1회 + end_turn 1회
- `expected`에 `tool_calls_made: 1`, `policy_blocks: 0` 포함

## 검증
```
uv run harness eval --pattern 'f8_*.yaml'
uv run pytest tests/test_skills.py -q
```
둘 다 통과해야 함 (test_skills.py가 eval_globs의 파일 실재 여부를 검증).

## 하지 말 것
- `harness/tools/paper.py` 로직 수정 금지 — 이 task는 eval 추가만. 기존 동작 변경 X.
- 다른 skill의 eval_globs 건드리지 말 것 — step2/step3이 담당.
- 네트워크를 실제로 부르는 fixture 금지 — MockLLM 응답으로 tool 출력을 가정한다.
