# AGENTS.md — Edith 개발 가이드 (Codex / 코딩 에이전트용)

> 이 파일은 **코드를 고치는 에이전트**를 위한 dev 규약이다.
> Edith의 런타임 페르소나·운영 schema는 `identity.md` / `CLAUDE.md`에 따로 있다 — **그 둘은 절대 자동 수정하지 말 것**(사용자만 변경).

## 무엇인가
Edith = 사용자의 Knowledge-Twin 개인비서. 실 Gmail·Google Calendar를 읽어 아침 brief +
선제 제안을 만들고, 승인된 외부 액션을 정책 게이트 통해 실행한다. Python 3.12 / uv / FastAPI / Click.

## 빌드·검증 (커밋 전 필수)
```bash
make check     # ruff(line-length 100) + pyright(basic) + pytest  — 반드시 통과
make eval      # golden YAML 케이스 (CLAUDE.md: 골든 100% pass 못하면 머지 금지)
make test      # EDITH_LLM=mock uv run pytest
```
- 모든 PR은 `make check` **그린** + `make eval` **전부 pass** 여야 한다.
- 새 feature는 **golden 케이스 동봉**(evals/golden/*.yaml). `kind: runtime`(MockLLM) 또는
  `kind: call`(함수 직접 호출) 사용. eval 하니스는 hermetic(실 Gmail/네트워크 안 탐).
- 의존성: `uv run <cmd>`. 설치 `uv pip install -e ".[dev]"` (옵션: `.[google]` `.[mac]`).
- `.env`는 cli.py·server.py가 자동 로드. 테스트는 `EDITH_LLM=mock`.

## 불변 규칙 (정책 — 깨면 안 됨)
- **R1 raw/ immutable** — `raw/`는 읽기만. 코드로 수정·삭제 금지(seed_demo만 예외, skip-existing).
- **R2 external write → approval** — Gmail 발송·캘린더 생성·GitHub commit 등 외부 액션은
  `request_approval` → ApprovalQueue → ApprovalExecutor 경로만. 직접 발송 금지.
- **scope 분리** — work raw를 personal/school 컨텍스트로 retrieve 금지(policies R3).
- **secrets** — `.env`·`secrets/`·token은 **절대 커밋 금지**(이미 .gitignore). 토큰 0o600.
- `identity.md`·`CLAUDE.md`는 에이전트가 자동 수정하지 않는다.

## 아키텍처 (3-zone)
- `raw/` 원본(immutable) · `wiki/` 컴파일된 위키 · `harness/` 런타임·tool·정책.
- 핵심: `harness/runtime.py`(agent loop) · `harness/server.py`(FastAPI: `/ask` `/ui/*`) ·
  `harness/webui/index.html`(글래스 GUI 단일 페이지) ·
  `harness/mail.py`+`integrations/gmail.py`(메일, batch) · `harness/calendar.py`(+Google) ·
  `harness/morning.py`(brief) · `harness/initiative.py`(선제 체크인) ·
  `harness/propose.py`+`harness/approval.py`+`harness/executor.py`(제안→승인→실행) ·
  `harness/policies.py` · `harness/llm.py`(EDITH_MAX_TOKENS).
- tool은 `harness/tools/`에 구현하고 `harness/skills/<name>.py`의 Skill manifest로 등록.
  tool 추가 시 `tests/test_smoke.py`의 tool 개수·이름 집합도 갱신.

## 커밋 규약
- 메시지: `PR NN: <한 줄 요약> (NNN tests)` + 본문(무엇·왜). 끝에:
  `Co-Authored-By: <your-agent> <noreply@…>`
- 작은 단위로 자주 커밋. main에 직접 커밋(이 repo 관행). 푸시는 사용자 요청 시만.

## 지금 할 일
`docs/10_commercial_sprint.md`의 **상용화 스프린트** Tier 1 → 4 순서로 구현.
각 항목: 구현 + 테스트(필요시 golden) + `make check`/`make eval` 그린 + 커밋.
