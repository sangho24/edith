# Roadmap v3 — Harness-First

> **참조**: Karpathy의 [LLM Wiki / Idea File (2026-04-03)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) + [jha0313/harness_framework](https://github.com/jha0313/harness_framework)
> **이전 문서**: `personal_ai_assistant_plan.md` (전략·비전·zone 격리 — 그대로 유효). 이 문서는 그 위의 **실행 로드맵**으로, v2의 Section 10(12주 phase)·Section 11(Track A)를 대체.
> **핵심 전환**: feature를 먼저 짓는 게 아니라, **하네스(eval·trace·policy) 먼저 → wiki 컴파일 → 그 위에 feature**.

---

## 0. TL;DR — 한 화면 요약

```
Week 0      Phase 0  Schema & Identity        (글만 씀, 코드 0줄)
Week 1-3    Phase 1  Harness Foundation       (측정·재현·롤백 환경)
Week 3-5    Phase 2  LLM Wiki Compilation     (Karpathy 3-layer)
Week 5-12   Phase 3  Features on Top          (F1~F12, 매주 1개)
Week 12+    Phase 4  Skill Platform           (H8 skill registry, F13~F15, 빌드 하네스)
```

**왜 이 순서인가**:
1. 측정 없이는 개선 없다 — harness 없이 feature 짜면 깨진 걸 모른다
2. wiki는 모든 feature의 메모리 — wiki 없이 짜면 feature마다 schema 달라져 drift
3. identity·schema는 코드보다 먼저 — CLAUDE.md가 모호하면 어떤 LLM도 일관 동작 못 함

---

## 1. Phase 0 — Schema & Identity (Week 0, 1-2일)

> **Karpathy의 Layer 3**: schema는 generic agent를 **disciplined wiki maintainer**로 바꾸는 config. 코드보다 먼저.

### 1.1 산출물 3개 — 모두 markdown

#### `identity.md` — 비서가 누구인지

```markdown
# Twin (가칭) — 상호님의 Knowledge Twin

## 어조
- 한국어 존댓말, 문장 짧게, 이모지 안 씀
- 불확실하면 "확실하지 않음" 명시
- 근거(support_refs) 없이 단정하지 않음

## 거절 룰
- 회사(Zone A) 데이터를 외부 LLM에 보내라는 요청 거절
- 학업 과제 본문 작성 거절 (구조·검토는 OK)
- 카톡 친구·동료 자동 응답 거절

## 우선순위 (충돌 시)
정확성 > 근거 명시 > 간결함 > 친절함

## 비서가 안 하는 것
- 매일 daily note (사람이 직접 — anti-atrophy)
- 비가역 외부 발송 (반드시 승인 후)
```

#### `CLAUDE.md` — agent가 무엇을 어떻게 하는지

```markdown
# CLAUDE.md — Knowledge Twin Schema

## 역할
당신은 사용자의 Knowledge Twin입니다. raw source를 wiki로 컴파일하고,
사용자의 질문에 wiki를 인용해서 답합니다. Q&A가 아니라 compilation.

## 디렉토리
- raw/        : 원본. **immutable**. 읽기만, 수정 금지.
- wiki/       : 당신이 관리하는 markdown. 자유롭게 쓰기·고치기.
- harness/    : 런타임·툴·eval. 본인이 만들지 않은 코드는 수정 금지.
- evals/      : 골든 테스트. 새 feature는 여기 케이스 먼저 추가.

## wiki 페이지 종류
- entities/<name>.md   : 사람·프로젝트·도구·회사
- concepts/<topic>.md  : 주제·개념
- summaries/<doc>.md   : 단일 문서 요약
- log.md               : 시계열 일지 (append only)
- INDEX.md             : 전체 목차 (자동 갱신)
- contradictions.md    : 모순 발견 시 기록 (사람 리뷰 대상)

## 페이지 frontmatter (필수)
---
type: entity | concept | summary
scope: personal | school | work
support_refs: [raw/path1, raw/path2]
confidence: high | medium | low
last_updated: 2026-04-28
---

## 답변 규칙
- 모든 답변에 wiki 페이지 또는 raw source 인용 (markdown link)
- 인용 못 할 정보는 "근거 없음 — 추론" 명시
- scope 다르면 (work + personal) cross-reference 금지

## 새 source 들어왔을 때
1. raw/에 그대로 저장 (수정 X)
2. 어떤 entity/concept과 관련되는지 추출
3. 해당 wiki 페이지 update — 새 fact는 추가, 모순되면 contradictions.md에 기록
4. log.md에 한 줄 append
```

#### 디렉토리 골격

```
~/twin/
├── identity.md
├── CLAUDE.md
├── README.md          # 1줄: "Knowledge Twin (Karpathy LLM Wiki + Harness)"
├── raw/               # Layer 1: 원본 (immutable)
│   ├── meetings/
│   ├── papers/
│   ├── emails/
│   ├── captures/      # 카톡 메모로 던진 텍스트
│   └── code_diffs/
├── wiki/              # Layer 2: LLM이 컴파일한 markdown
│   ├── entities/
│   ├── concepts/
│   ├── summaries/
│   ├── log.md
│   └── INDEX.md
├── harness/           # Phase 1에서 채움
├── evals/             # Phase 1에서 채움
│   └── golden/
└── personal.db        # 메타데이터·검색 인덱스 (Phase 1)
```

### 1.2 Phase 0 머지 기준

PR title: "feat: Phase 0 — schema & identity"

- [ ] `identity.md` 작성됨 (10-20줄)
- [ ] `CLAUDE.md` 작성됨 (30-60줄)
- [ ] 디렉토리 골격 git에 commit
- [ ] **demo**: `raw/captures/test.md`에 텍스트 던져보고 그 자리에 있는 거 확인 (LLM은 아직 아무것도 안 함)

> 코드 0줄. 이게 이 PR의 핵심. **글이 코드보다 먼저**.

---

## 2. Phase 1 — Harness Foundation (Week 1-3)

> "어떤 feature를 얹어도 측정·재현·롤백 가능한 환경"
> Phase 1이 끝나면, 모든 후속 feature는 **eval 통과한 것만 머지**된다.

### 2.1 7개 컴포넌트

| ID | 컴포넌트 | 1줄 정의 | Week |
|---|---|---|---|
| H1 | **Runtime Loop** | input → action → observation → repeat (with budget) | 1 |
| H2 | **Tool Registry** | typed tools 9개로 시작, schema 명시 + policy hook | 1 |
| H3 | **Trace Capture** | 모든 run을 JSONL로 기록, 사후 query 가능 | 1-2 |
| H4 | **Eval Harness** | 골든 케이스(YAML) 일괄 실행, regression 감지 | 2 |
| H5 | **Policy Engine** | tool 호출 전 scope·approval·PII 검사 | 2 |
| H6 | **Observability** | trace/error/cost dashboard + 주간 자동 report | 2-3 |
| H7 | **Memory Hooks** | wiki R/W 시 support_refs·confidence 자동 삽입 | 3 |

### 2.2 H1 — Runtime Loop (가장 먼저)

```python
# harness/runtime.py — 처음엔 50줄 안짜리
def run(task: str, budget: Budget) -> Trace:
    trace = Trace.start(task, identity=load("identity.md"),
                              schema=load("CLAUDE.md"))
    state = State.from_task(task)

    while not state.done() and trace.cost < budget:
        action = llm.next_action(state, tools=registry, trace=trace)
        if not policy.allow(action, state.scope):
            trace.record_blocked(action, reason="policy")
            break
        result = registry.execute(action)
        trace.record(action, result)
        state = state.update(result)

    return trace.finalize()
```

**불변량**:
- trace는 **append only**. 중간 수정 금지.
- budget 초과 시 **즉시 종료**. 무한루프 방지.
- 모든 action은 **policy 통과 후 실행**.

### 2.3 H2 — Tool Registry (9개로 시작)

```python
# harness/tools/__init__.py
TOOLS = {
    "wiki_read":    schema(path=str)              -> str,
    "wiki_write":   schema(path=str, content=str,
                           support_refs=list[str])-> bool,
    "wiki_search":  schema(query=str)             -> list[Hit],
    "raw_read":     schema(path=str)              -> str,  # 읽기만
    "raw_list":     schema(dir=str)               -> list[str],
    "capture_text": schema(text=str, scope=str,
                           source=str)            -> str,  # raw/에 저장
    "query_db":     schema(sql=str)               -> rows,
    "request_approval": schema(action=Action,
                               preview=str)       -> str,  # queue id
    "emit_log":     schema(level=str, msg=str)    -> None,
}
```

각 tool은:
- **타입 명시** (Pydantic)
- **policy hook** 통과 후 실행
- **trace에 자동 기록** (input·output·latency)

> 추가 tool은 Phase 3에서 feature와 함께 등록.

### 2.4 H3 — Trace Capture

```jsonl
# harness/traces/2026-04-28T08:00:01.jsonl
{"t":0,"event":"start","task":"오늘 일정 요약","budget":2000}
{"t":1.2,"event":"action","tool":"wiki_search","args":{"query":"오늘"}}
{"t":1.5,"event":"observation","hits":3}
{"t":2.0,"event":"action","tool":"wiki_read","args":{"path":"log.md"}}
...
{"t":8.4,"event":"finalize","cost":847,"output":"..."}
```

쿼리 예시:
- `harness traces --grep "policy=blocked" --last 7d` → 정책 차단 사례
- `harness traces --task "morning_brief" --metric latency_p95` → 평균 latency
- `harness traces --replay <id>` → 같은 input으로 재실행

### 2.5 H4 — Eval Harness

```yaml
# evals/golden/morning_brief_basic.yaml
task: "morning_brief"
fixtures:
  - raw/captures/2026-04-01.md: |
      오늘 회의 3건. 점심 약속 X.
expected:
  must_contain: ["회의", "점심"]
  must_have_support_refs: true
  no_pii_leak: true
  scope_clean: personal  # work 데이터 인용 없어야
  max_length_chars: 200
```

```bash
$ harness eval --golden=evals/golden/*.yaml
✓ morning_brief_basic.yaml      pass (8.4s, 847 tokens)
✗ paper_triage_arxiv.yaml       fail — missing support_refs
✓ recall_with_citation.yaml     pass (3.2s, 412 tokens)
2/3 pass
```

**머지 기준**: PR이 골든 set 100% pass해야 머지. 새 feature는 PR 안에 새 골든 케이스 동봉 필수.

### 2.6 H5 — Policy Engine

```markdown
# harness/policies.md — 사람이 읽을 수 있는 정책

## scope 룰
- task scope = personal: work raw/* 접근 금지
- task scope = work: 외부 LLM 호출 금지 (사내 endpoint만)
- task scope = mixed: 작업 분리 후 각각 처리

## approval 룰
- write target ∈ external (Gmail send, Calendar create, Notion update)
  → request_approval 필수, expires=2h
- write target ∈ internal (raw/, wiki/, personal.db)
  → 자동 허용

## PII 룰
- 외부 LLM call payload에 다음 정규식 매치 → redact 또는 abort
  - 이메일주소, 전화번호, 주민번호, API key 패턴
```

코드는 markdown을 파싱해서 룰 적용 (`policy.allow(action)`).

### 2.7 H6 — Observability (단순하게 시작)

```bash
$ harness dash
─────────────────────────────────────────
Last 24h: 47 runs · 2 errors · $0.83 cost
p95 latency: 12.4s
─────────────────────────────────────────
Top errors:
  policy=blocked  (1) at 14:22
  budget_exceeded (1) at 18:01
```

매주 일요일 22시 자동 weekly report → `wiki/log.md`에 append.

### 2.8 H7 — Memory Hooks

`wiki_write` 호출 시 자동으로:
- `support_refs` (어느 raw에서 왔는지)
- `confidence` (검증된 fact vs 추론)
- `last_updated_at`

이 메타데이터가 wiki frontmatter에 자동 삽입. 사람이 직접 안 적어도 됨.

### 2.9 Phase 1 머지 기준 (Week 3 끝)

- [ ] H1-H7 모두 동작
- [ ] 골든 케이스 5개 이상 (간단한 거라도)
- [ ] `harness run "테스트"` 로 trace 생성 확인
- [ ] policy 차단 시나리오 1개 시연 (예: 외부 LLM에 PII 보내려는 케이스)

---

## 3. Phase 2 — LLM Wiki Compilation (Week 3-5)

> Karpathy 패턴 그대로: raw → wiki를 한 번 컴파일, 이후 wiki 위에서 동작.

### 3.1 컴파일 파이프라인 (W1, Week 3)

```bash
$ harness compile
[1/3] raw/captures/2026-04-25.md  → wiki/log.md (append) + entities/dr.kim.md (update)
[2/3] raw/papers/iclr_2026_x.md   → concepts/transformer_interp.md (append)
[3/3] raw/meetings/m_0426.md      → entities/projectA.md (update) + contradictions.md (1 new)
done.
```

내부 흐름:
1. `raw_list()` → 미컴파일 source 발견 (`compile_log.db`로 추적)
2. 한 source씩 LLM에게: "이 source를 wiki에 통합해라. 어느 entity/concept과 관련되는지 추출하고, 해당 페이지 update. 모순 시 contradictions.md."
3. wiki_write 호출 → support_refs에 원본 raw path 자동 삽입
4. compile_log에 "compiled" 마킹

### 3.2 첫 5개 씨앗 페이지 (W2, Week 3-4)

직접 작성하는 wiki 씨앗:
- `wiki/entities/사용자_본인.md` — 본인 fact (역할·관심·습관·anti-atrophy 룰)
- `wiki/entities/삼일PwC_AX.md` — placeholder (Zone A는 추후)
- `wiki/entities/학교.md`
- `wiki/concepts/transformer_interpretability.md` — 본인 관심 주제 1개
- `wiki/INDEX.md` — 전체 목차

씨앗이 있어야 LLM이 "이 source를 어디에 통합할지" 추론 가능.

### 3.3 Daily Compile Loop (W3, Week 4-5)

매일 22시 cron:
```bash
harness compile && harness eval --golden=evals/golden/wiki_*.yaml
```
- 그날 들어온 raw → wiki 컴파일
- 컴파일 후 wiki eval 실행 (consistency check)
- log.md에 일자별 변경 요약 append

### 3.4 Schema Discipline (W4, Week 5)

첫 4주 사용 후:
- CLAUDE.md를 다듬는다 (잘 안 지켜진 룰 발견 → 명료화 또는 deterministic check로 이전)
- 예: "support_refs 빠진 wiki 페이지 X개 발견" → CLAUDE.md에서 "필수"를 더 강조하거나, `wiki_write` 자체에서 support_refs 누락 시 reject

### 3.5 Phase 2 머지 기준 (Week 5 끝)

- [ ] `harness compile`로 raw → wiki 자동 통합 동작
- [ ] 5개 씨앗 페이지 + LLM이 추가한 페이지 ≥10개
- [ ] 매일 22시 cron 동작
- [ ] **demo**: 카톡 메모로 "오늘 김교수님 미팅에서 X 결정"보내고 5분 뒤, `wiki/entities/김교수.md`에 그 fact가 추가됐는지 확인

---

## 4. Phase 3 — Features on Top (Week 5-12)

이제 모든 feature는 **(1) eval 케이스 먼저 작성 → (2) 구현 PR이 그 eval pass해야 머지**.

### 4.1 12개 Feature 카탈로그

| Wk | F# | 제목 | Eval (먼저 작성) | 의존 |
|---|---|---|---|---|
| 5 | F1 | **Quick Capture (카톡→raw)** | 10개 sample text → scope 자동 분류 ≥9/10, raw/captures/에 저장 | H1-H7 |
| 6 | F2 | **Calendar Collector** | 1주일 일정 mock → 일정 정확 ≥95%, scope tagging 100% | H2 |
| 6 | F3 | **Gmail Triage** | 50개 mock 메일 → priority 정확 ≥85%, work 메일은 metadata만 | H2 |
| 7 | F4 | **Morning Briefing 통합** | brief에 일정+우선메일+Top3 모두, 길이 ≤200자, support_refs 100% | F1+F2+F3 |
| 8 | F5 | **Approval Queue + 첫 L3** | 10개 calendar 초안 → 미승인 자동 발송 0건, audit log 100% | H5 |
| 8 | F6 | **Memory Recall** | 30개 recall 쿼리 → support_refs 첨부율 100%, hallucination ≤2건 | W1-W3 |
| 9 | F7 | **Repo Skill (PR 1차 리뷰)** | 5개 sample PR → issue 발견 ≥80% (사람 리뷰 대비), false positive ≤20% | F6 |
| 10 | F8 | **Paper Triage** | 10개 arxiv → 핵심 contribution 정확, wiki cross-link ≥3개 | F6 |
| 10 | F9 | **JD Analyzer** | 5개 JD → fit score + 본인 이력서 fact 활용한 bullet 5개 | F6 |
| 11 | F10 | **Weekly Synthesis** | 주간 syn에 그 주 사건만 (이전 주 leak ≤1건), 새 cross-link ≥3개 | F1-F9 |
| 12 | F11 | **Home Hub Deploy** | docker compose up → 모든 골든 eval pass, 24h cron 무사고 | F1-F10 |
| 12 | F12 | **VPS Relay** | 노트북 닫힌 채 push 24시간 무사고, 백업 자동 | F11 |

### 4.2 Feature PR의 두 단계 룰

```
PR-eval (먼저)        PR-impl (나중)
- evals/golden/*.yaml - feature 코드
- mock fixtures        - 골든 케이스 100% pass
- (코드 0줄)           - 새 tool 등록 시 schema·policy hook 추가
                       - trace 자동 기록 확인
```

이 두 단계 룰이 없으면 "동작은 하는데 정확도 모르는 feature"가 쌓인다.

### 4.3 각 feature의 머지 기준

- [ ] eval 케이스 ≥3개 (golden YAML)
- [ ] 골든 100% pass
- [ ] policy 위반 0건 (trace로 검증)
- [ ] **demo**: 머지 직후 본인이 직접 해볼 수 있는 명령 1개
- [ ] 다음 주 머지 전까지 매일 1번 이상 사용 → 사용 안 했으면 폐기 후보

---

## 4.4 Phase 4 — 스킬 플랫폼 (로드맵 이후, Week 12+)

> F1-F12로 "비서가 동작한다"까지 왔다. Phase 4는 "비서를 **확장 가능하게** 만든다".
> 계기: [OpenClaw](https://github.com/openclaw/openclaw)와 비교했을 때 Edith의 약점이
> **확장성·생태계**(하드코딩된 tool registry, 단일 채널)였다. 깊이는 OpenClaw보다 낫지만 넓이가 없다.

### 4.4.1 H8 — Skill Registry (완료, 2026-05-14)

`harness/tools/`의 17개 tool을 하드코딩으로 등록하던 `build_default_registry()`를,
`harness/skills/`의 **선언적 skill manifest**로 전환.

```
harness/skills/
├── __init__.py       Skill dataclass + all_skills() + build_registry()
├── core.py           wiki·raw·util  (scope=any, 항상 on)
├── calendar.py       F2
├── mail.py           F3
├── ds_digest.py      F4  (scope=personal)
├── recall.py         F6
├── papers.py         F8
├── repo.py           F7
└── jd.py             F9  (scope=personal)
```

`Skill` = `name · scope · tools · eval_globs · channels · policy_keys`.
- `eval_globs` — CLAUDE.md "새 feature는 eval YAML 먼저" 룰을 manifest 레벨에서 강제.
  `tests/test_skills.py`가 glob이 실재 파일을 가리키는지 검증.
- `channels` — 멀티채널 단계(F13)에서 쓸 필드. 지금은 선언만.
- tool 파일은 이동하지 않음 — `harness/skills/`가 기존 tool 객체를 *그룹핑*. import 경로 28곳 안 깨짐.
- `build_default_registry()`는 `build_registry()`로 위임 — runtime/cli 하위호환 유지.

머지 기준: 328 tests pass · 10/10 golden eval pass (마이그레이션 전후 동일).

### 4.4.2 Phase 4 feature 카탈로그

| F# | 제목 | Eval (먼저 작성) | 상태 | 의존 |
|---|---|---|---|---|
| F13 | **멀티채널 surface** | `harness/integrations/channel.py` — `Channel` Protocol + `IncomingMessage` + `ChannelRegistry`. `TelegramChannel` 어댑터(실 환경) + `MockChannel`(테스트). 채널별 송수신 round-trip 테스트 | ✅ 2026-05-14 | H8 |
| F14 | **ds-digest skill 확장** | `GitHubPagesDigestSource`(latest.json fetch, fetch 함수 inject), `get_digest_source()` 팩토리. 네트워크·JSON 실패 graceful degrade. golden eval `f14_ds_digest.yaml` | ✅ 2026-05-14 | H8, F4 |
| F15 | **헬스 데이터 skill** | Apple Health(샤오미 Mi Band → Apple Health 동기화) 소스. scope=personal 고정 + policy 게이트. 수면·활동 fact를 wiki/concepts에 컴파일 | 진행 중 | H8, H5 |

> F13은 OpenClaw처럼 채널 14개를 다 만들지 않는다. 지금 실제 wired된 건 Telegram 하나 —
> 인터페이스만 추출해두고, EmailChannel·KakaoChannel은 **실제 호출부가 생길 때** 어댑터를 추가한다.
> caller 없는 채널은 유지보수 부채다.

> 멀티채널은 OpenClaw처럼 14개 다 하지 않는다. **실제 쓰는 것만** — 안 쓰는 채널은 유지보수 부채.
> 헬스는 가장 민감한 데이터다. F15는 policy 게이트 시연(미승인 cross-scope retrieve 0건)이 머지 기준.

### 4.4.3 빌드 하네스 (별도 트랙)

Phase 4부터 feature를 **빌드 하네스**로 짓는다 — `docs/05_cc_harness.md` 참조.
[jha0313/harness_framework](https://github.com/jha0313/harness_framework) 패턴을 Edith 규칙에 맞춰 옮긴 것.
런타임 하네스(`harness/`)가 "Edith가 어떻게 답하는가"를 규율한다면, 빌드 하네스는
"Edith를 어떻게 짓는가"를 step·가드레일·eval 게이트로 규율한다. 둘은 같은 eval을 공유.

---

## 5. 12주 한 흐름

```
Week  무엇                                              산출물
────  ─────────────────────────────────────────────────  ──────────────────────
0     Phase 0  identity.md / CLAUDE.md / 디렉토리         글 3장 + 빈 폴더
1     H1 Runtime + H2 Tool Registry                       harness/runtime.py + 9 tools
2     H3 Trace + H4 Eval + H5 Policy                      JSONL traces + 5 골든 케이스
3     H6 Obs + H7 Memory + W1 Compile pipeline            dashboard + harness compile
4     W2 5개 씨앗 페이지                                  wiki/entities/*, INDEX.md
5     W3 Daily compile cron + F1 Quick Capture            카톡 → raw → wiki 자동
6     F2 Calendar + F3 Gmail                              일정 list / 메일 priority
7     F4 Morning Briefing                                 매일 08시 카톡 push
8     F5 Approval + F6 Recall                             첫 L3 + recall with refs
9     F7 Repo Skill                                       PR 1차 리뷰 draft
10    F8 Paper + F9 JD                                    arxiv triage / 지원 패키지
11    F10 Weekly Synthesis                                일요 21시 이메일 (Knowledge Twin 정수)
12    F11 Home Hub + F12 VPS                              always-on 인프라
```

---

## 6. Phase 0의 첫 PR — 지금 시작

지금 머지할 PR. 코드 0줄.

```
PR title: feat: Phase 0 — schema & identity
변경:
+ identity.md         (10-20줄)
+ CLAUDE.md           (30-60줄)
+ raw/.gitkeep
+ wiki/.gitkeep
+ harness/.gitkeep
+ evals/.gitkeep
+ README.md           (1줄)

Demo:
1. raw/captures/hello.md 에 "테스트 메시지" 저장
2. ls raw/captures/ → 보임
3. (LLM은 아직 아무것도 안 함)

Why this PR is the foundation:
- "raw is immutable, wiki is LLM-owned, schema is the config"
  이 3가지 원칙이 코드 layout에 박힘
- 이후 모든 PR은 이 layout을 전제로 동작
```

---

## 7. 매주 주말 체크 (Track B 결합)

매주 일요일 30분, harness가 자동 생성한 weekly report를 본다:

```
─────────────────────────────────
Week 5 Report (Sun 22:00 auto-gen)
─────────────────────────────────
Trace 통계:
  · 총 run        : 142
  · policy 차단   : 3 (모두 의도된 redaction)
  · budget 초과   : 1 (Long paper triage — 다음 주 budget 조정)
  · 평균 cost     : $0.012/run

Eval 통계:
  · 골든 케이스    : 27개 (이번 주 +3)
  · pass rate     : 96.3%
  · 회귀          : 1건 (F4 morning_brief — fixture 변경 확인)

Wiki 통계:
  · 새 entity     : 8개
  · 새 concept    : 3개
  · contradictions: 2개 (사람 리뷰 필요 ↓)
─────────────────────────────────
```

이 report가 retro의 객관적 근거가 된다.

---

## 8. 왜 v3가 v2보다 나은가

| | v2 (Track A) | v3 (Harness-First) |
|---|---|---|
| 첫 PR | A1 Quick Capture (feature) | Phase 0 schema (글) → Phase 1 harness (infra) |
| 측정 | feature 개별 평가 | 모든 feature가 같은 골든 set로 측정 |
| 메모리 | feature마다 SQLite 직접 사용 | wiki라는 공통 layer (Karpathy 패턴) |
| 회귀 감지 | 수동 | golden eval 자동 |
| trace | feature가 알아서 | harness가 자동 기록 |
| schema 진화 | 분산 | CLAUDE.md 한 곳에 집중 |
| Karpathy 정합성 | ≈ | ✓ "compilation, not Q&A" |

요약: v3는 v2보다 **앞 4주가 무거워 보이지만, 5주차부터 feature 개발 속도가 훨씬 빠르고 안전**하다.

---

## 9. 참고

- [Karpathy LLM Wiki idea file (2026-04-03)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Beyond RAG: Karpathy's LLM Wiki Pattern (Level Up Coding)](https://levelup.gitconnected.com/beyond-rag-how-andrej-karpathys-llm-wiki-pattern-builds-knowledge-that-actually-compounds-31a08528665e)
- [The Andrej Karpathy LLM Wiki Idea (Reliability Whisperer)](https://reliabilitywhisperer.substack.com/p/the-andrej-karpathy-llm-wiki-idea)
- [jha0313/harness_framework](https://github.com/jha0313/harness_framework) — 빌드 하네스 패턴, `docs/05_cc_harness.md` 참조
- [openclaw/openclaw](https://github.com/openclaw/openclaw) — 멀티채널 비서 프레임워크, Phase 4 skill 플랫폼의 비교 대상
- [HKUDS/OpenHarness — "Open Agent Harness"](https://github.com/HKUDS/OpenHarness)
- [awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)
- [LangChain DeepAgents — agent harness 참조 구현](https://github.com/langchain-ai/deepagents)

---

## 10. 한 줄 정리

> **"비서를 짓기 전에 비서를 측정·재현·롤백할 수 있는 환경부터 만든다 (harness). 그 위에 LLM이 raw를 markdown wiki로 컴파일한다 (Karpathy). 그 위에서야 비로소 feature를 얹는다 (F1-F12). 앞 4주가 무거워 보이지만, 5주차부터의 속도와 안전이 그 비용을 모두 갚는다."**
