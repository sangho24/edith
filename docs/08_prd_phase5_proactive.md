# 08 · PRD — Phase 5: 선제적·자기확장 Knowledge Twin

> 2026-05-14 v0.1 · 기획서 + PRD
> 대상: Edith를 "pull-only 컴파일러"에서 "감사 가능한 선제적·self-extending twin"으로 끌어올리는 8개 서브시스템의 통합 설계·구현 기준 문서.
> 선행 문서: `docs/01_strategy.md`(비전), `docs/05_cc_harness.md`(빌드 하네스), `docs/06_design_backlog.md`(기술부채), `docs/07_external_skills_catalog.md`(MCP/skill ROI).

---

## 0. 한 줄 요약 + 차별점

**한 줄**: Phase 5는 Edith가 (1) 외부 생태계(MCP)를 추천·연결하고, (2) 하루를 선제적으로 묻고, (3) 워크플로우를 근거와 함께 제안·설명하고, (4) 승인되면 실제 코딩으로 skill을 자동 저작하고, (5) 반복 패턴을 감지해 다음을 자동 트리거하는 — **닫힌 self-improving 루프**를 기존 harness 위에 얹는다. 단, 모든 자율성은 approval-before-action·scope 격리·eval-first·인용 규율이라는 4개 게이트를 통과해야 한다.

### 0.1 Hermes / OpenClaw / Manus 대비 차별점

| 축 | 일반 agent (Hermes·Manus류) | OpenClaw류 | **Edith Phase 5** |
|---|---|---|---|
| 메모리 | 블랙박스 임베딩 ("그렇게 기억해요") | 세션 메모 | **감사 가능** — 모든 학습 선호가 `support_refs`(raw/approval) 근거로 인용됨 |
| 선제성 | 자유롭게 push | 알림 폭주 | **정책 게이트** — identity.md Push 표(평일 ≤4회·quiet hours·deep work toggle)를 코드로 강제 |
| 자기확장 | self-edit 자율 | 14채널·N MCP 다 만듦 | **이중 승인** — skill 저작(코딩)과 등록(런타임 노출)을 분리, 각각 사람 승인 |
| 안전 | 사후 가드 | 신뢰 기반 | **사전 게이트** — R1-R4 정책 + budget + trace append-only를 신규 surface도 통과 |
| 확장 철학 | 최대주의 | 채널 최대 | **"실제 쓰는 것만"** — caller 없는 채널/MCP = 부채로 간주, v1은 무인증 read MCP만 |

핵심 정체성: **"화려한 자율성이 아니라 추적 가능한 단순 흐름"** (Observability Over Cleverness). Edith가 무엇을 왜 스스로 했는지 trace + 인용으로 100% 설명 가능해야 한다.

---

## 1. 비전·문제 정의

### 1.1 상호님의 5개 요구사항 (비전)

1. **생태계 연동** — 메신저(카톡)·노션·구글·유튜브 등 외부 MCP/skill을 Edith가 추천하고 연결한다.
2. **선제적 주도** — 하루 일과를 먼저 묻고, 워크플로우를 납득가게 설명·제안한다.
3. **실행으로 일 해결** — 승인되면 실제 코딩 또는 외부 행동으로 일을 처리한다.
4. **skill 자동 생성** — LLM이 쓸 plugin/skill을 (반자율로) 저작·검증·등록한다.
5. **시간/맥락 기반 트리거** — 반복 작업을 감지해 시각·컨텍스트에 맞춰 다음 액션을 선제 추천한다.

### 1.2 현재의 공백 (gaps 요약)

- **MCP runtime bridge가 0건** — Python harness가 SDK deferred `mcp__*` tool을 실제로 호출하는 경로가 코드·테스트 어디에도 없다.
- **proactive planner가 0건** — morning.py는 rule-based 정적 합성. "왜 지금/왜 이걸"을 추론·설명·학습하는 레이어가 없다.
- **스케줄러 실체 불확실** — `.github/workflows/`는 존재하지 않음. 유일한 실 스케줄러는 `docker/docker-compose.yml`의 `edith-cron` 컨테이너(supercronic-style)이나 어느 서브시스템도 여기에 wiring돼 있지 않다.
- **per-item scope 태그 없음** — `Message`/`ApprovalRequest`에 scope 필드가 없어 데이터 항목 단위 격리가 불가능. R3는 tool-name 기반.
- **send-side PII 게이트 미연결** — `redact_pii`/`check_external_payload`가 LLM 호출·`Channel.send` 경로 어디에도 wiring 안 됨.
- **executor 2종뿐** — `github_workflow_update_cron`·`gmail_send`만 구현. calendar/notion/kakao/slack은 'executor 없음' 에러(B5).
- **personal.db = placeholder** — 선호 학습용 구조화 메모리가 없다.

### 1.3 핵심 긴장 (이 PRD가 풀어야 할 것)

> identity.md의 "조용한 비서"(평일 push ≤4회) ↔ 비전2의 "선제적으로 먼저 묻기" ↔ CLAUDE.md "묻지 않은 것 답변 안 함" — 이 셋을 **단일 push budget + anti-atrophy 정책 + 자율성 레벨 매트릭스**로 한 번에 조정한다(§7).

---

## 2. 재사용 vs 신규 (Ground 요약)

Phase 5는 **신규 인프라를 거의 만들지 않는다**. 기존 13개 자산 위에 얇은 레이어를 얹는다.

| 기존 자산 | 파일 | Phase 5에서의 역할 |
|---|---|---|
| Runtime Loop + Policy Gate | `harness/runtime.py` | 모든 신규 tool이 budget·trace·policy 게이트를 그대로 상속 |
| Policy Engine (R1-R4) | `harness/policies.py` | **확장 필요** — R2 동적 tool, R5(send-side PII), R6(push 정책) |
| Approval Queue | `harness/approval.py` | **확장 필요** — `scope` 필드 추가, expires 호출부 명시 |
| ApprovalExecutor | `harness/executor.py` | **확장 필요** — calendar_create·kakao_send·notion_update·build_skill·mcp_connect executor |
| Skill Registry (manifest) | `harness/skills/__init__.py` | 신규 skill = 파일1+YAML1. 단 동적 등록 시 캐시 무효화 필요 |
| Channel 추상화 | `harness/integrations/channel.py` | KakaoMemoChannel 어댑터 1개 추가 (실 caller 생긴 후) |
| Morning Brief | `harness/morning.py` | proactive/추천/제안 슬롯이 여기에 묶임 (push 1회 budget) |
| 빌드 하네스 StepExecutor | `scripts/execute.py` | code-to-skill의 코딩 엔진 (신규 0줄) |
| Eval Harness | `harness/eval.py` | **확장 필요(STEP 0c)** — registry 주입 + 직접 함수 호출 케이스 타입 |
| GitHub cron 관리 | `harness/integrations/github_workflow.py` | **확장 필요** — dow/주간 cron 지원, commit/push 경로 |
| Daily Compile Loop | `harness/daily.py` | 패턴 마이닝·선호 도출이 daily 5단계로 편입 |
| Trace (append-only) | `harness/state.py`, `harness/traces.py` | 패턴 마이닝·감사 로그의 single source of truth |
| docker edith-cron | `docker/docker-compose.yml` | **실 스케줄러** — run_checkin/mine_patterns/tick을 여기에 wiring(STEP 0b) |

**신규 모듈(최소)**: `harness/mcp/` (bridge·recommender), `harness/initiative.py`, `harness/triggers/`, `harness/propose.py`, `harness/self_author/`, `harness/patterns.py`, `harness/memory/`. 단 §6 로드맵이 각각을 최소 수직 슬라이스로 잘라낸다.

---

## 3. 시스템 아키텍처

8개 서브시스템은 모두 기존 5개 게이트(runtime·policy·approval·executor·trace) 위에 얹힌다. **신규 surface도 같은 게이트를 통과한다.**

```
                          ┌──────────────────────────────────────────────┐
   INBOUND                │           SCHEDULER (STEP 0b)                  │
   ┌──────────┐           │  docker edith-cron / .github/workflows        │
   │ Telegram │           │  매 tick → run_checkin · mine_patterns · tick  │
   │ Kakao    │──┐        └───────────────┬───────────────────────────────┘
   │ capture  │  │                        │
   └──────────┘  │                        ▼
                 │            ┌────────────────────────────┐
   ┌──────────┐  │            │  ② Initiative Engine        │  ⑤ Pattern
   │ /명령    │──┤            │  run_checkin → Suggestion    │←── Mining
   │ webhook  │  │            │  → Gate → PushGate           │   (patterns.py)
   └──────────┘  │            └──────────┬─────────────────┘
                 │                       │ suggest
                 ▼                       ▼
        ┌─────────────────┐   ┌────────────────────────────┐
        │  RUNTIME LOOP   │   │  ④ Workflow Proposal        │
        │ (runtime.py)    │   │  planner → Proposal → explain │
        │  input→tool→obs │   │  (propose.py)                │
        └───┬─────────────┘   └──────────┬─────────────────┘
            │                            │ accept
   ┌────────▼─────────────────────────────▼──────────────────┐
   │            POLICY GATE  (policies.allow + R5/R6)         │ ← ① MCP tools
   │   R1 raw  R2 external→approval  R3 scope  R4/R5 PII       │   (make_mcp_tool)
   └────────┬─────────────────────────────┬──────────────────┘
            │ internal write                │ external write
            ▼                               ▼
   ┌─────────────────┐          ┌────────────────────────────┐
   │ wiki / raw / db │          │  APPROVAL QUEUE (approval)  │
   │ (자동 허용)      │          │  pending→approved→executed   │
   └─────────────────┘          └──────────┬─────────────────┘
            ▲                               ▼
            │                    ┌────────────────────────────┐
   ⑥ Memory │                    │  APPROVAL EXECUTOR (B5+)    │
   feedback ─┘                   │  gmail·calendar·kakao·       │
   (memory/)                     │  mcp_connect·build_skill     │
                                 └──────────┬─────────────────┘
                                            │ build_skill
                                            ▼
                                 ┌────────────────────────────┐
                                 │  ③ StepExecutor (execute.py) │
                                 │  phases/skill-<slug>/step1-3  │
                                 └──────────┬─────────────────┘
                                            ▼
                                 ┌────────────────────────────┐
                                 │  ④ self-author validate +    │
                                 │  register (2nd approval)     │ → all_skills() 한 줄
                                 └────────────────────────────┘
            ▲
            │  ⑦ context-triggers: calendar lookahead / signal → dispatch → Channel.send
            │  ⑧ (모든 send 직전) R5 PII chokepoint
   ┌────────┴───────────────────────────────────────────────┐
   │              OUTBOUND  Channel.send (PII gate 통과 필수)   │
   │              Telegram / KakaoMemo / (graceful degrade)    │
   └──────────────────────────────────────────────────────────┘
   ALL: Trace append-only (state.py) · Budget (runtime.py) 상속
```

**불변**: 외부 write는 반드시 Policy Gate → Approval Queue → Executor 경로만 탄다. 어떤 서브시스템도 이 경로를 우회하지 않는다. internal write(wiki/raw/db/suggestions/patterns json)는 자동 허용.

---

## 4. 서브시스템별 상세 명세

각 서브시스템은 **적대적 검토에서 드러난 결함을 "⚠️ 주의/완화"로 반영하고, 과설계는 잘라냈다.**

### 4.1 ① MCP 생태계 연동 엔진 (mcp-ecosystem)

**책임**: 부착 가능한 MCP(YouTube/Naver/Kakao/Google/Notion)를 추천하고, 무인증 read MCP를 1급 tool로 래핑해 runtime 게이트를 그대로 상속시킨다.

**핵심 결정**: docs/06 F1을 **(b) harness/tools 1:1 래핑 + `make_mcp_tool()` 팩토리**로 확정. runtime이 직접 MCP client가 되면(a안) policy·trace를 우회하므로 거부.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| MCP bridge spike (`harness/mcp/bridge.py`) | SDK deferred `mcp__*` tool | **new (STEP 0, blocking)** |
| `make_mcp_tool()` + `McpToolSpec` | tools/`__init__.py`, telegram http_post inject 패턴 | extend |
| `harness/mcp/recommender.py` | morning.py deterministic 합성, traces.py | new |
| `harness/skills/mcp_*.py` (youtube/naver) | skills/`__init__.py` manifest | extend |
| `recommend_mcp` tool + `/recommend` | core.py, server.py webhook | extend |

**data_model**:
- `McpToolSpec(mcp_tool_name, edith_tool_name, input_schema, is_external_write: bool, scope, auth_kind)`. v1은 `auth_kind='none'`(YouTube/Naver)만.
- `Recommendation(mcp_id, score, reason_text, requires_auth, scope, caution)` — 비영속. 점수 = w1·키워드매칭 + w2·roi_tier(docs/07). w3(trace 빈도)는 데이터 쌓인 뒤(v2).
- `mcp_state.json`(gitignore) — `{mcp_id: {enabled, connected_at, approved_via}}`.

**user_flow**: "이 유튜브 강연 자막 정리해줘 <url>" → `recommend_mcp`가 youtube를 1위(reason='docs/07 R2 + read-only 무인증')로 반환 → youtube가 enabled=False라 직접 호출 못 함 → `request_approval(action='mcp_connect')` → 승인 → mcp_state.json enabled 기록 → 다음 run부터 `youtube_transcript` 노출.

**eval**: `mcp_recommend_youtube.yaml`(youtube 1위·reason에 docs/07 근거), `mcp_connect_approval_gate.yaml`(enabled=False면 직접 호출 차단), `mcp_scope_isolation.yaml`, `make_mcp_tool` 단위테스트.

**⚠️ 주의/완화 (검토 반영)**:
- **R2/R3 상속은 거짓** — `make_mcp_tool`이 만든 동적 tool 이름은 `EXTERNAL_WRITE_TOOLS` 집합·`tool_scopes()` lru_cache에 없어 게이트를 안 거친다. → **요구사항**: MCP tool 등록 시 `EXTERNAL_WRITE_TOOLS`·`tool_scopes` 동기 갱신 + `lru_cache` 무효화(STEP 2). v1 무인증 read MCP만이라 외부 write tool은 v1에 없음.
- **bridge 미검증** — `mcp_call_fn`이 전부 Mock. **STEP 0 spike**(youtube_transcript 1개 실 PlayMCP end-to-end 호출)가 모든 컴포넌트의 차단 선행조건.
- **범위 축소** — v1 = youtube/naver(무인증) + `/recommend`(pull-only). credential store·OAuth·brief 슬롯·kakao/notion executor는 spike 성공 후로 분리.
- **discovery 흡수** — static_catalog는 mcp_registry manifest와 90% 중복. 별도 discovery 모듈 만들지 않고 manifest 하나로 통합.
- **MCP 응답을 wiki 인용** — MCP read 결과는 raw/ 파일이 아니므로 support_refs 규율 충돌. → MCP 결과를 `raw/captures/`에 먼저 capture_text로 저장한 뒤 wiki 컴파일(인용 규율 유지).

### 4.2 ② 선제적 주도 엔진 (proactive-engine)

**책임**: morning.py를 "후보 Suggestion 생성 → 게이트 → 우선순위 → push" 파이프라인으로 일반화. 단방향·rule-only로 시작.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| `harness/initiative.py` (`run_checkin`) | morning.compose_brief, daily.py 멱등 패턴 | new |
| `Suggestion` dataclass | approval.py preview/params 분리 패턴 | new |
| `SuggestionGenerator` (urgent 미답 메일만) | morning.py 신호 dict | new |
| `PushGate` (weekday_cap만) | identity.md Push 표 | new |
| suppression (N일 단순 침묵) | feedback jsonl | new |

**data_model**:
- `Suggestion(id, category, scope, title, why, signal_key, score, action_hint, created_at, slot, status)`. status: proposed→shown→(accepted|rejected|snoozed|expired).
- `suggestions.json`·`suggestion_feedback.jsonl`(append-only). `signal_key = category+coarse-signal`(예: `reply_reminder:from=advisor`).

**user_flow**: 평일 08:00 cron → `run_checkin('morning')` → compose_brief 신호 + 거절 이력 → 후보 생성 → Gate(anti-atrophy nudge 강등 + suppression) → PushGate(morning=1푸시) → "오늘 일정 2건·urgent 메일 1건. 제안: 김교수님 답장 초안(2일째 미답)." → `/skip`이면 record_feedback로 signal_key를 N일 suppress.

**eval**: `i1_checkin_basic`(빈 신호→push 0), `i2_suppression`, `i3_anti_atrophy`(action_hint 없는 nudge로만 강등), `i4_push_frequency`(당일 4건→거부).

**⚠️ 주의/완화**:
- **트리거 부재가 blocking** — `.github/workflows/` 없음, github_workflow_update_cron은 로컬 YAML만 수정. → **STEP 0b**(docker edith-cron에 run_checkin wiring) 선행.
- **eval-first 강제 불가** — `run_case`는 runtime.run(MockLLM)만 구동. suppression/ledger 단언 불가. → **STEP 0c**(eval 러너에 직접 함수 호출 케이스 타입) 선행.
- **scope 모래성** — Message에 per-item scope 없음. → **STEP 0d**(per-item scope 태깅) 선행. 그 전엔 i6_scope_block 통과 불가.
- **과설계 컷** — 10 컴포넌트 → v1은 single SuggestionGenerator + weekday_cap PushGate + N일 suppression. 양방향 1-tap·trust ladder·LLM why·KakaoChannel은 v2.
- **push 분류** — 비서 자신의 outbound push가 external write(R2)인지 internal notify인지 **§8 결정 필요**.

### 4.3 ③ 컨텍스트 트리거 (context-triggers)

**책임**: identity.md push 표를 실행 가능한 trigger rule로 코드화. `evaluate(now, signals, state)` 순수함수 + dispatch.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| `harness/triggers/rules.py` (TriggerRule) | identity.md 표, github_workflow cron 포맷 | new |
| `harness/triggers/evaluator.py` (순수함수) | github_workflow.parse_cron, daily.py | new |
| `harness/triggers/dispatch.py` | morning, channel, approval, trace | new |
| `trigger_state.json` (de-dup·rate) | approvals.json 패턴 | new |

**data_model**: `TriggerRule(name, kind['cron'|'calendar_lookahead'|'signal'], schedule, action[allowlist], channel, scope, quiet_hours, toggle_key, max_per_month, eval_globs)`. `FiredTrigger(rule_name, fired_at, reason)`.

**v1 RULES (3개만)**: `morning_brief`·`eod_checkin`·`weekly_synth` (cron only). meeting_prep(calendar_lookahead)·surprise_resurface(LLM proactive)·daily_digest는 별 PR.

**eval**: `f18_triggers_cron_match`(**tick-window 기반**, exact-minute 아님), `f18_triggers_dedup`(slot=날짜+rule), `f18_triggers_quiet_hours`, `f18_triggers_toggle_deepwork`.

**⚠️ 주의/완화**:
- **cron-match vs 드리프트 자기모순** — GH cron은 08:20 발화 가능한데 eval은 08:00 exact 요구. → **cron 매칭을 tick-window로 재정의**(`tick 간격 내 1회`, slot=날짜+rule). dedup slot 명시.
- **parse_cron_to_kst 한계** — 'M H * * *' 일일 cron만 처리, dow/dom는 None. KST→UTC day-shift(KST 08:00 = UTC 전날 23:00) 시 요일 cron 깨짐. → weekly_synth는 별도 매처 or parse_cron 확장.
- **scope·PII 미강제** — compose_brief는 scope 인자 없는 단일 messages.json. → scope-aware 리팩터(STEP 0d) 선행. **PII는 Channel.send 직전 단일 chokepoint로 강제**(R5, §4.8).
- **과설계 컷** — KakaoMemoChannel·signal CLI(app_focus)·.github/workflows·VPS relay 전부 인프라 PR로 분리. v1 = evaluate+dispatch+trigger_state+MockChannel.
- **catch-up 정책** — tick 누락 시 late-fire vs skip-stale **§8 결정 필요**. v1 default: morning_brief는 당일 마지막 tick에서 1회 보장(skip-stale은 quiet hours 밖이면).

### 4.4 ④ 워크플로우 제안 + 납득 설명 (workflow-proposal)

**책임**: ApprovalRequest를 깨지 않고 그 위에 Proposal(설명 첨부된 다단계 액션 계획)을 얹는다.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| `harness/propose.py` (Proposal+Store+render) | approval.py, state.py | new |
| 검증 코어 (planner = thin caller) | morning, recall, llm, policies | new |
| `propose_workflow` tool | tools/util.py | new |
| server.py `/ui/proposals/decide` | server.py approvals 패턴 | extend |

**data_model**: `Proposal(id, title, trigger['task'|'morning_brief'], rationale, steps, scope, status['proposed'|'closed'])` + `ProposalStep(idx, intent, explanation, expected_outcome, risk_note, support_refs, action_type, params, reversible, risk_score, inferred, queued_approval_id)`. ApprovalRequest 스키마 무변경 — accept 시 step별로 풀려 큐로 내려감. preview = explanation+expected+support_refs 합성.

**user_flow**: "ICLR 리뷰 어떻게 처리하지?" → LLM이 memory_recall로 근거 모으고 `propose_workflow` 호출 → proposals.json 저장 → "제안 1건 등록 — Proposals 탭에서 확인·승인" → 사용자가 GUI에서 전체 승인 → 각 external step이 ApprovalQueue로 → ApprovalExecutor 실행.

**eval**: `f18_propose_basic`(tool 1회·ApprovalRequest 0건), `f18_propose_citation_required`(support_refs 빈 step → inferred=true·risk≥6), `f18_no_autosend`(proposed 상태에선 executor 미호출), `render` 단위테스트(pytest).

**⚠️ 주의/완화**:
- **"internal write 자동 허용"은 보안 우회** — `propose_workflow`에 gmail_send params를 담으면 R2/R3/R4를 우회 통과. → **P0: allow()에 propose_workflow의 step.action_type/params 재귀 검사 분기 추가**(STEP 2).
- **check_external_payload 미연결** — planner가 params에 PII 검사한다는 가정이 거짓(wiring 0건). → R5 chokepoint 의무화(§4.8). work scope step은 외부 전송 action_type 자체 금지.
- **eval 절반이 표현 불가** — accept→queue·decide 엔드포인트·render는 골든 아닌 pytest 영역. → eval-first 커버리지 갭을 pytest로 메우는 것을 머지 조건에 명시.
- **과설계 컷** — explain.py 별도 모듈 삭제(propose.py render 메서드 1개), morning 연계·webui amend 체크박스·repeat_detected enum 삭제. status 6→2값. v1 = "승인만(B5 executor 의존 디커플)".
- **decide 엔드포인트는 고위험** — 즉시 외부 실행. /ui/* 무인증 가정 재검토 필요.

### 4.5 ⑤ 코딩 실행 → skill 자동 생성 (code-to-skill)

**책임**: 사용자가 명시 요청한 skill을 빌드 하네스로 실제 코딩 실행하고, eval-first로 검증해 사람 승인 후 등록.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| `propose_skill` tool + SkillScaffolder | tools/util.py, phases/ 구조 | new |
| `_exec_build_skill` executor | executor.py, scripts/execute.py | extend |
| 등록 = 사람이 수동 실행하는 step3 | phases step3 partial run | (단순화) |

**data_model**: `phases/skill-<slug>/{index.json, step1.md(eval YAML 먼저), step2.md(skill 파일), step3.md(등록 — 사람 수동)}`. ApprovalRequest action_type='build_skill', params={task_slug, phases_dir}, reversible=true, risk_score=4.

**user_flow (시나리오 B만, v1)**: "ds-digest 새 소스를 노션 초안으로 만드는 skill 만들어줘. scope=personal." → `propose_skill` → SkillScaffolder가 phases/skill-digest-source-draft/ 생성 → `request_approval(build_skill)` → 사용자가 preview 보고 승인 → StepExecutor가 step1(eval)·step2(skill 파일)만 자동 실행 → 사용자가 `pytest tests/test_skills.py` 통과 확인 후 **수동으로 step3(등록) 실행**.

**eval**: `p5_self_author_propose`(phases/ 생성·step1이 'evals/golden' 포함), `p5_scaffold_eval_first`(step 순서 [eval, skill, 등록]), `p5_no_self_edit`(identity.md/CLAUDE.md 수정 step 거부).

**⚠️ 주의/완화 (feasibility: low — 가장 많이 잘라냄)**:
- **eval 게이트 순환 의존(치명)** — SkillValidator의 "eval.run_all 100% pass"는 라이브 `all_skills()`를 쓰는데 등록 전 skill의 tool은 거기 없어 'unknown tool'. 검증하려면 등록돼야 하고 등록하려면 검증을 통과해야 함. → **STEP 0c에서 eval.run_case에 registry injection** 추가가 선행 차단조건.
- **build_skill 동기 30분 블록** — StepExecutor는 claude CLI subprocess(30분 timeout). ApprovalExecutor 동기 경로에서 호출하면 승인 CLI 블록. → **background 실행 모델 결정 필요**(§8). approval expires(기본 30분)와 build 소요 경합도 해소 필요.
- **자동 생성 eval 형해화** — LLM이 쓴 동어반복 골든이 머지 게이트를 통과. → **register 전 사람이 골든 YAML 서명 의무화**(§8 결정).
- **anti-atrophy 우회** — 명시 요청 경로는 필터 안 거침. → 단일 anti-atrophy 정책(§7)이 propose_skill에도 적용.
- **self-modification 충돌** — SkillRegistrar가 `harness/skills/__init__.py` 자동 편집 + commit은 CLAUDE.md "harness/는 명시적 마이그레이션 PR로만" 위반. → **등록은 사람 수동 step**(SkillRegistrar 모듈·2nd approval·idempotent patch 전부 삭제).
- **과설계 컷** — trace 패턴 감지(SkillProposer.scan_traces)·daily hook·cli author group·validator 별도 모듈 전부 v1 제외. validator 항목 (2)(5)는 기존 `tests/test_skills.py`로 대체.

### 4.6 ⑥ 반복 패턴 감지 → 자동 트리거 (pattern-autotrigger)

**책임**: trace에서 반복 패턴을 마이닝해 brief에 선제 추천. v1은 **관찰 전용(observe/suggest)**.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| `harness/patterns.py` (`mine_patterns`) | traces.py, dashboard.py, github_workflow.cron | new |
| `RecurringPattern` (trace 파생, 비영속) | — | new |
| `pattern_match` / `pattern_list` tool | skills, recall.py | extend |
| daily.py 마이닝 훅 | daily_loop | extend |

**data_model**: `RecurringPattern(id, label, task_tokens, scope, support, is_time_regular, suggested_cron, autonomy_level['observe'|'suggest'], hit_count)`. **patterns.json 별도 store 안 만듦** — 매일 trace에서 재계산하는 파생물. trust ledger는 approvals.json의 approve/reject 이벤트를 pattern_id로 group-by해 재구성.

**user_flow**: 평일 아침 ds-digest 질문 7회 반복 → daily mine_patterns가 support=7, is_time_regular 패턴 승격(observe) → 다음 brief에 "🔁 늘 8시쯤 ds-digest 보시던데 — /recommend로 cron 거실래요?" (suggest). 실제 cron 등록은 사용자 수동(v1).

**eval**: `f18_pattern_mining_min_support`(동일 fingerprint 3개→패턴 1개), `f18_fingerprint_jaccard`(자카드<0.6·scope 불일치→안 묶임), `f18_time_regularity_cron`, `f18_scope_isolation`.

**⚠️ 주의/완화 (feasibility: low)**:
- **tool_seq를 fingerprint 키로 쓰면 근본 결함** — LLM 비결정성으로 같은 의도가 다른 tool_seq로 쪼개져 support 임계를 못 넘음. → **fingerprint 1차 키 = task_tokens 자카드 + scope만**. tool_seq는 디버그 메타로 강등.
- **auto/draft/trust ladder 전체 삭제** — executor 부재(B5) 시 auto는 silent no-op. → v1 = observe→suggest 2단계. draft/auto·trust ledger·promote/demote는 executor+cron+toggle 갖춰진 뒤 별 PR.
- **time-trigger 자동 cron 등록 제외** — is_time_regular/suggested_cron 계산만, 등록은 수동. github_workflow는 로컬 YAML만 수정·commit 안 함.
- **콜드스타트** — traces/ 비어있음(.gitkeep만). 정상 — observe로 조용히 누적, 임계 전엔 무제안.
- **마법 상수** — min_support=3·since_days=30·자카드 0.6은 실데이터 없는 추정. golden으로 회귀 고정 후 튜닝.

### 4.7 ⑦ 메모리 & 학습 모델 (memory-learning)

**책임**: 거절/승인 신호를 세션 너머 누적해 인용 가능한 선호로 만든다. v1은 **신호 수집만**.

| 컴포넌트 | builds_on | new/extend |
|---|---|---|
| `feedback_event` 테이블 + `record_feedback` | approval.py, policies.redact_pii | new |
| `harness/memory/store.py` (전용 함수만) | util._query_db read-only 뷰 | new |
| approve_no/approve_yes 학습 훅 | cli.py, server.py | extend |
| `preference_recall` read-only tool | recall.py 인터페이스 | new (후속) |

**data_model**: `personal.db` (SQLite, gitignore). `feedback_event(id, ts, kind, scope, subject, action_type, source_ref, detail[redact 후], weight)`. `preference_card`는 **신호가 몇 달 쌓인 뒤 후속 PR**(learn_preferences).

**user_flow (v1)**: 토요일 "지도교수께 메일 보내기" 제안을 `harness approve no <id> --reason "주말엔 안 보냄"` 거절 → approve_no 핸들러가 `record_feedback(kind=approval_reject, subject='action:gmail_send', source_ref='approval:<id>', detail=redact(reason), scope=work)`를 personal.db에 append.

**eval**: `m1_record_reject`(거절→feedback_event 1건), `m5_pii_redacted_feedback`(detail에 이메일→[REDACTED:email]).

**⚠️ 주의/완화 (8→2 컴포넌트로 축소)**:
- **scope 출처 부재(치명)** — ApprovalRequest에 scope 필드 없고 approve_no는 scope 안 받음. → **STEP 0d: ApprovalRequest.scope 추가 + ApprovalQueue.create 호출부 전수 마이그레이션** 선행.
- **scope='any' recall은 R3 미발동** — `skill_scope != "any"` 조건이 통과시킴. preference_card 단위 scope를 tool-name R3로 표현 불가. → **§8 결정 필요**(data-scope 분류기 투자 vs 약한 격리 수용). v1은 신호 수집만이라 회피.
- **query_db 임의 SQL 위험** — read-only 강제 없음. → MemoryStore는 전용 함수(insert_event/active_cards)만, query_db는 read-only 뷰로 격리.
- **wiki/preferences 미러 삭제** — DB↔wiki 이중 저장·CLAUDE.md 디렉토리 불변 위반·드리프트. support_event_ids→source_ref 인용으로 충분.
- **proactivity_gate 분리** — 말 걸 채널이 미완인데 게이트 먼저 만드는 건 과설계. proactive-engine PushGate에 흡수.
- **데이터 빈곤** — executor 2종뿐이라 거절 모수가 gmail_send에 한정. STEP 1(executor 확충)이 데이터 공급 선행조건.
- **PII 한계** — redact_pii는 이메일/전화/키만. 이름·기관 안 잡힘. detail 자유텍스트 노출 주의.

### 4.8 ⑧ 횡단 안전 레이어 (cross-cutting — 어느 facet도 안 가졌던 것)

완전성 비평이 지목한 **소유자 없는 횡단 갭**을 명시적 컴포넌트로 승격한다.

| 갭 | 신규 요구사항 | 위치 |
|---|---|---|
| send-side PII chokepoint | **R5**: `Channel.send` 직전 `check_external_payload` 의무 호출. 실패 시 abort | `policies.py` + `channel.py` 단일 choke point |
| push 정책 코드화 | **R6**: trigger/suggestion push가 quiet_hours·toggle·weekday_cap 통과 | `policies.py` `check_push(rule, now, toggles, ledger)` |
| credential redaction | PII_PATTERNS에 google refresh_token·notion token 형식 추가 | `policies.py` (OAuth 도입 시) |
| 동시성/원자성 | 단일 locking 전략 or personal.db 트랜잭션 (STEP 3) | 신규 JSON store 전체 |
| 누락 tick catch-up | late-fire vs skip-stale 정책 + idempotency key | triggers/dispatch.py |
| push budget 통합 | 모든 서브시스템의 brief 슬롯·push를 단일 budget으로 | morning.py + R6 |

---

## 5. 통합 사용자 시나리오 (한 흐름)

> 한 흐름으로 5개 비전이 모두 작동하는 모습. (executor·스케줄러·bridge 선행조건이 충족된 가정.)

**08:00, 노트북을 연다.**

1. **(②⑦ 선제)** docker edith-cron이 `run_checkin('morning')`을 깨운다. compose_brief가 오늘 일정·urgent 메일·ds-digest를 합성한다. SuggestionGenerator가 "지도교수 답장 2일째 미답"을 후보로 잡지만, ⑦ feedback_event에 "주말 메일 거절 3회" 신호가 있어 — 오늘은 평일이므로 통과. PushGate가 weekday_cap(4) 안이라 1푸시 허용. Telegram으로: *"☀️ 오늘 일정 2건·urgent 1건. 김교수님 답장(2일째 미답) 처리 도울까요?"*

2. **(④ 제안+설명)** "응 어떻게?" → runtime이 `memory_recall`로 raw/mail·wiki/ICLR을 근거로 끌어오고 `propose_workflow`를 호출한다. proposals.json에 3-step Proposal이 저장된다: ①리뷰 2h 캘린더 블록 ②리뷰 초안 wiki 페이지 ③공저자 메일 초안. 각 step에 *근거: raw/mail/2026-05-29.md*, *예상결과*, *리스크*가 붙는다. 근거 없는 step은 `[추론]`·risk≥6으로 마킹.

3. **(① MCP 추천)** 메일에 유튜브 강연 링크가 있다. `recommend_mcp`가 *"YouTube Data MCP 연결 — read-only 무인증 (docs/07 R2)"*를 brief 하단 1줄로 추천(별도 push 아님).

4. **(승인)** 사용자가 Proposals 탭에서 ③(메일)은 체크 해제(부분 승인), ①②만 승인. ①은 calendar_create로 ApprovalQueue → ApprovalExecutor(EventKit) 실행. ②는 wiki_write 즉시 반영. ⑦이 이 승인을 feedback_event(approve, +1)로 기록.

5. **(③⑤ 코딩→skill)** 사용자: "이 자막 정리 매번 하는데 skill로 만들어줘." → `propose_skill`이 phases/skill-yt-summary/(eval YAML + skill 파일 + 등록 step)을 scaffold → `request_approval(build_skill)` → 승인 → StepExecutor가 step1·2 코딩 실행 → 사용자가 골든 통과 확인 후 수동으로 등록.

6. **(⑥ 다음엔 자동 트리거)** 2주 뒤, daily mine_patterns가 "유튜브 자막 정리"를 support=5·observe로 잡는다. 다음 비슷한 task가 들어오면 `pattern_match`가 *"이거 늘 하시던 yt-summary 플로우네요"*라고 한 번 확인(suggest). 사용자가 *"매일 아침 자동으로"*를 원하면 cron 제안 → 승인 → 그 작업이 스스로 돈다.

7. **(전 과정)** 모든 step이 trace에 append-only로 기록되고, 외부로 나가는 텍스트는 R5 PII chokepoint를 통과한다. "왜 이 추천을 했어?"라고 물으면 Edith는 근거 trace/approval id를 인용해 답한다.

---

## 6. 단계적 로드맵 (Phase 5.x)

각 feature는 **eval YAML 먼저**(step1). 의존성·순서는 완전성 비평 sequencing 반영. **STEP 0~3은 어느 facet도 소유하지 않은 공유 차단 선행조건** — 반드시 먼저.

> **D2=병행 반영**: F35(MCP OAuth + credential store)를 5.4 → **5.1로 당김**. Phase 5.0에 credential store 골격(`harness/mcp/credentials.py`, gitignore token 저장)을 포함하고, F29(mcp v1)가 무인증(youtube/naver)·OAuth(google/notion)를 함께 등록한다. 단 bridge spike(F18) 성공이 여전히 전제.

### Phase 5.0 — 차단 선행조건 (Blocking Prerequisites)

| ID | Feature | 내용 | 의존 |
|---|---|---|---|
| **F18** | MCP runtime bridge spike | youtube_transcript 1개를 실 PlayMCP로 end-to-end 호출·검증 | — |
| **F19** | 스케줄러 wiring | docker edith-cron에 `run_checkin`/`mine_patterns`/`triggers tick` 연결 + cron-tick 실행 위치 결정 + cron-edit commit/push 경로(자체 approval) | — |
| **F20** | eval 러너 확장 | `run_case`에 registry injection + 직접 함수 호출 케이스 타입(suppression/ledger/push count/accept→queue/격리 registry 단언) | — |
| **F21** | per-item scope 태깅 | `ApprovalRequest.scope` 필드 + `ApprovalQueue.create` 호출부 전수 마이그레이션 + `Message`/digest scope | — |

### Phase 5.1 — 실행·정책 기반 (Execution & Policy Foundation)

| ID | Feature | 내용 | 의존 |
|---|---|---|---|
| **F22** | B5 executor 확충 | calendar_create(EventKit, 실검증 가능) → kakao_send → notion_update 순 | F18 |
| **F23** | 정책 하드닝 | propose_workflow/make_mcp_tool R2 우회 차단(allow() 재귀 param 검사 + 동적 EXTERNAL_WRITE_TOOLS + tool_scopes 캐시 무효화) | F21 |
| **F24** | R5 send-side PII chokepoint | Channel.send 직전 check_external_payload 의무 | F21 |
| **F25** | 공유 동시성 기반 | 신규 멀티-writer JSON store에 단일 locking or personal.db 트랜잭션 | — |

### Phase 5.2 — 선제 레이어 (최소형)

| ID | Feature | 내용 | 의존 |
|---|---|---|---|
| **F26** | proactive-engine v1 | run_checkin + 1 SuggestionGenerator + PushGate(weekday_cap) + suppression(N일) | F19, F20, F21 |
| **F27** | context-triggers v1 | evaluate(tick-window) + dispatch + trigger_state, cron 3룰, R6 push 정책 | F19, F24 |
| **F28** | workflow-proposal v1 | Proposal/Store/render + propose_workflow tool + decide 엔드포인트 ("승인만") | F22, F23 |
| **F29** | mcp-ecosystem v1 | make_mcp_tool + youtube/naver(무인증) + recommend_mcp(pull /recommend) | F18, F23 |

### Phase 5.3 — 자기확장·관찰

| ID | Feature | 내용 | 의존 |
|---|---|---|---|
| **F30** | code-to-skill v1 | propose_skill + build_skill executor(background) + scaffold(명시 요청만, 등록 수동) | F20, F22 |
| **F31** | pattern-autotrigger v1 | mine_patterns(task_tokens 자카드) + pattern_match/list, observe/suggest only | F19, F20 |
| **F32** | memory 신호 수집 | feedback_event + record_feedback(거절 훅) + preference_recall read-only | F21, F22 |

### Phase 5.4 — 데이터 축적 후 (last, 콜드스타트 해소 뒤)

| ID | Feature | 내용 | 의존 |
|---|---|---|---|
| **F33** | memory 집계 | learn_preferences(preference_card) — feedback_event 수개월 후 | F32 |
| **F34** | pattern auto/draft | trust ladder + auto 레벨(reversible·저위험만) | F22, F31, F33 |
| **F35** | MCP OAuth + credential store | google/notion(auth_kind=oauth) + credential redaction 패턴 | F29 |

---

## 7. 안전·정책·자율성 레벨

### 7.1 자율성 레벨 매트릭스 (L0~L4) — 전 서브시스템 공통

| 레벨 | 정의 | Edith 행동 | 게이트 | Phase 5 적용 |
|---|---|---|---|---|
| **L0 observe** | 기록만 | trace·feedback·pattern 누적 | 없음(internal) | 신규 패턴/선호 default |
| **L1 suggest** | 추천(pull/brief 1줄) | "이거 할까요?" | PushGate(R6) | proactive/pattern/mcp v1 상한 |
| **L2 draft** | 큐잉(1클릭 승인 대기) | ApprovalRequest pending 생성 | approval gate | workflow-proposal accept |
| **L3 execute** | 승인 후 실행 | ApprovalExecutor 실행 | approval + executor + R5 | F22 executor 있는 action만 |
| **L4 auto** | 자동 실행 | 자동승인된 approval 1건(executed 추적) | reversible·risk≤3·패턴별 opt-in | **Phase 5.4까지 보류** |

**Phase 5 자율성 상한 = L3**. L4(auto)는 executor·스케줄러·데이터가 모두 갖춰지고 trust 데이터가 쌓인 뒤(§8 결정). 비가역 행동(예약·금전·삭제)은 **L4여도 절대 금지**(identity.md).

### 7.2 비가역 행동 가드

- external write는 무조건 approval. 미승인 자동 발송 = policy 위반 = trace 빨간 표시.
- L4 auto도 "자동승인된 approval 1건"으로 모델링 → executed 상태로 추적·롤백 가능.
- 비가역(reversible=false) 또는 risk_score>3 action은 L4여도 L2(draft)로 강등.

### 7.3 단일 anti-atrophy 정책 (per-facet 차단셋 통합)

> **문제**: 4개 facet이 각자 다른 blocklist(_BLOCKED_AS_ACTION, 키워드 필터, action_type gate, proactivity_gate)를 만들어 drift·모순. → **단일 정책으로 통합**.

`policies.py`에 단일 `is_atrophy_protected(category) -> bool`:
- 보호 카테고리: `daily_note`·`creative_body`·`new_hypothesis`·`research_direction`·`quarterly_rotation`.
- 보호 카테고리는 어떤 서브시스템에서도 **action_hint 부여 금지** — 최대 nudge(리마인더, 1/일 상한)만.
- 보호 카테고리 제안은 사용자가 항상 볼 수 있어야 함(silent suppression 금지 — 비전 가시성 원칙).
- proactive-engine·pattern·code-to-skill·memory 전부 이 함수를 호출(중복 구현 금지).

### 7.4 단일 push budget + suppression ledger

- 모든 서브시스템의 brief 슬롯·push는 **단일 `push_ledger`**(R6)를 공유. 평일 합산 ≤4회.
- brief 1회 push에 여러 서브시스템 제안을 묶음(인터럽트 최소화). 별도 push 금지(개별로는 정당해도 합산이 정책 위반).
- 거절 신호도 **단일 feedback ledger**(memory feedback_event)로 통합. 3개 다른 suppression 곡선 대신 하나: signal_key reject → N일 침묵(v1 단순), 데이터 쌓이면 backoff(v2).

---

## 8. 결정 필요 사항 (사용자 검토용)

### 8.0 확정된 결정 (2026-05-14 검토)

| # | 확정 | 영향 |
|---|---|---|
| **D1** | **L3(execute) 상한** — 추천대로. L4(auto)는 5.4 보류 | §7 그대로 |
| **D2** | **무인증 read + 구글 OAuth 병행** — 추천(무인증 먼저)과 달리 둘 다 v1 | **로드맵 변경**: F35(OAuth+credential store)를 Phase 5.4 → **5.1로 당김**. F29가 youtube/naver(무인증)와 google/notion(oauth)을 함께 다룸. Phase 5.0에 credential store 골격 추가 |
| **D7** | **사람 수동 등록** — 추천대로. SkillRegistrar 자동편집 없음 | §4.5 그대로 |

나머지 D3~D6, D8~D17은 아래 표의 **추천값으로 확정**.

각 항목: **옵션 + 추천**. (D1/D2/D7은 위에서 확정됨.)

### 8.1 시스템 전역 결정 (must_decide)

| # | 결정 | 옵션 | 추천 |
|---|---|---|---|
| **D1** | Phase 5 자율성 상한 | pull-only / suggest-in-brief / draft / auto | **L3(execute) 상한, L4는 5.4로 보류**. brief 슬롯·push budget은 전역 공유(§7.4) |
| **D2** | MCP 부착 모델 + 첫 생태계 | (a)runtime-as-client / **(b)1:1 래핑** ; 첫 대상 무인증 read(youtube/naver) / oauth / kakao | **(b) 래핑 + 무인증 read 먼저**. credential.py를 v1에서 제거 |
| **D3** | 부착 게이트 범위 | 모든 부착 approval / 외부write·oauth만 approval(무인증 read는 CLI 토글) | **무인증 read는 `harness mcp enable <id>` CLI 토글, 외부write·oauth만 mcp_connect approval** |
| **D4** | 비서 자신의 outbound push 분류 | external write(R2 approval) / internal notify(자동) | **internal notify** — 단 R5 PII chokepoint·R6 push 정책은 통과. (kakao_send executor가 사용자에게 보내는 push는 R2 면제, 제3자 발송은 R2) |
| **D5** | scope 격리 메커니즘 | tool-name R3 유지 / data-item scope 분류기 투자 | **F21(ApprovalRequest.scope) + 발신 도메인 휴리스틱으로 시작**, 본격 분류기는 데이터 보고. R3가 scope='any'/동적 tool을 못 막는 한계 명시 |
| **D6** | eval-first 신뢰성 | 자동 골든 신뢰 / 사람 서명 + 러너 확장 | **F20 러너 확장 + code-to-skill 골든은 사람 서명 의무**. 안 하면 머지 게이트가 형식뿐 |
| **D7** | self-modification 경계 | auto-commit main / branch+PR / **등록 수동** | **등록 수동(사람이 step3 실행)**. SkillRegistrar 자동 편집 삭제 — CLAUDE.md "harness/는 마이그레이션 PR로만" 준수 |
| **D8** | anti-atrophy + suppression 통합 | per-facet / **단일 정책·ledger** | **단일**(§7.3·7.4). drift·모순 제거 |

### 8.2 서브시스템 결정 (각 facet open_decisions 통합)

| # | 결정 | 추천 |
|---|---|---|
| **D9** | build_skill 실행 모델 | **background 워커 + 'kicked off' 반환, 완료 시 콜백**. 동기 30분 블록·approval 만료 경합 회피 |
| **D10** | cron-tick 실행 위치 | **docker edith-cron(Home Hub) 우선** or GH cron→VPS relay→Tailscale. self-hosted runner는 데이터 접근 가능해야 |
| **D11** | 누락 tick catch-up | **morning_brief는 당일 마지막 tick에서 1회 보장(skip-stale)**, meeting_prep는 lookahead 넉넉히 |
| **D12** | B5 executor 우선순위 | **calendar_create(EventKit 실검증) > kakao_send > notion_update**. slack은 caller 생길 때 |
| **D13** | 카톡 채널 위치 | **capture=channel.py 어댑터(inbound), 검색/메모송신=MCP tool(outbound)**. kakao_managed 무인증 분류는 spike로 검증 필요 |
| **D14** | fingerprint 매칭 | **v1 deterministic(task_tokens 자카드+scope)**. tool_seq는 디버그 메타. 임베딩은 데이터 보고 |
| **D15** | personal.db 졸업 | **v1 2-tier(event+card), JSON 보조**. Mem0/Zep는 졸업 트리거 도달 시 |
| **D16** | 거절 --reason 강제 | **사유 없으면 action_type만 약신호(weight=-1)**, 강제 안 함 |
| **D17** | proactive 빈도 default | **weekday_cap=4(identity.md), surprise_resurface 월≤2로 보수 시작**, 실데이터로 튜닝 |

---

## 9. 평가 전략 (eval-first golden cases)

**원칙**: 모든 신규 feature는 golden YAML이 step1. `Skill.eval_globs`가 실재 파일을 가리켜야 `tests/test_skills.py` 통과. **단 F20(eval 러너 확장) 전까지는 내부 상태 단언 케이스가 표현 불가** — 그 케이스들은 pytest로 메우고, 골든은 runtime 관찰 가능한 것만.

### 9.1 차단 선행조건 검증
- `F18` — youtube_transcript 실 호출이 McpToolSpec.input_schema와 일치(수동 1회 체크리스트 + pytest mock).
- `F20` — eval 러너가 격리 registry로 미등록 skill 검증 가능, 직접 함수 호출 케이스가 push_ledger 카운트 단언.
- `F21` — ApprovalRequest.scope가 모든 create 호출부에서 채워짐(pytest 전수).

### 9.2 서브시스템 골든 (대표)
- **mcp**: `mcp_recommend_youtube`·`mcp_connect_approval_gate`·`mcp_scope_isolation`·`mcp_external_write_redact`.
- **proactive**: `i1_checkin_basic`·`i2_suppression`·`i3_anti_atrophy`·`i4_push_frequency`·`i6_scope_block`.
- **triggers**: `f18_triggers_cron_match`(tick-window)·`f18_triggers_dedup`·`f18_triggers_quiet_hours`·`f18_triggers_toggle_deepwork`·`f18_triggers_scope_clean`.
- **proposal**: `f18_propose_basic`·`f18_propose_citation_required`·`f18_no_autosend`·`f18_propose_scope_block`.
- **code-to-skill**: `p5_self_author_propose`·`p5_scaffold_eval_first`·`p5_no_self_edit`·`p5_anti_atrophy_filter`.
- **pattern**: `f18_pattern_mining_min_support`·`f18_fingerprint_jaccard`·`f18_time_regularity_cron`·`f18_scope_isolation`.
- **memory**: `m1_record_reject`·`m5_pii_redacted_feedback`.
- **횡단(R5/R6)**: `x1_send_pii_blocked`(Channel.send에 PII→abort)·`x2_push_budget_cap`(합산 push>4→거부)·`x3_anti_atrophy_unified`(보호 카테고리→action_hint 0).

### 9.3 회귀 게이트
- 기존 `tests/test_skills.py`: eval_globs 실재·tool name 중복 없음·scope 유효 — 신규/자동생성 skill도 통과.
- 골든 100% pass 못하면 머지 거부(CLAUDE.md). **단 D6이 미해결이면 이 게이트는 형식뿐임을 명시.**

---

## 변경 이력

- 2026-05-14 v0.1 — Phase 5 PRD 초안. 8개 서브시스템 설계·적대적 검토·완전성 비평을 통합. 핵심 결정: 자율성 상한 L3, MCP는 (b)1:1 래핑+무인증 read 먼저, 등록은 사람 수동, anti-atrophy/push budget 단일화, STEP 0(bridge·스케줄러·eval러너·scope)을 차단 선행조건으로 분리. 과설계 컷: code-to-skill SkillRegistrar·trace 마이닝, memory wiki 미러·proactivity_gate, pattern trust ladder·auto, proactive 양방향·LLM why를 v1에서 제거.
- 2026-05-14 v0.2 — 검토 결정 확정(§8.0): D1=L3 상한, **D2=무인증 read + 구글 OAuth 병행**(F35를 5.1로 당김, credential store 골격을 5.0에), D7=수동 등록. 나머지는 추천값 확정. 구현 착수: F21(scope 태깅)·F20(eval 러너 확장)부터.
