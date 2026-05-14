# 06 · 설계 백로그 — 알려진 문제·미완·기술부채

> 2026-05-14 v0.1 · 살아있는 문서 (해소 시 줄 긋고 날짜 기록, 신규 발견 시 append)
> 목적: 독립적으로 해결 가능한 task들을 한 곳에 모아 "한 번에" 처리하기 위한 백로그.

각 항목은 **독립 task**로 잡을 수 있게 작성. `심각도` · `발견 맥락` · `왜 문제인가` · `해결 방향` · `의존`.
심각도: 🔴 기능/안전에 영향 · 🟡 일관성/유지보수 · 🟢 정리·문서.

---

## A. 정책·안전 (policy & safety)

### A1. ✅ ~~R3 scope cross-ref enforce 미구현~~ (2026-05-14 해소 — skill scope 게이트)

- **발견 맥락**: F15 health skill (scope=personal) 머지 시. `harness/policies.py`가 R3를 "Phase 2 frontmatter 도입 후"로 미뤄둠.
- **해소**: `harness/skills/tool_scopes()` 역인덱스 + `policies.allow()`의 R3 — concrete scope skill의 tool은 같은 scope 또는 mixed task에서만 허용. `f15_health_scope_block.yaml` golden으로 검증. (PR 28)
- **남은 부분**: wiki/raw frontmatter scope 게이트는 별도 → **A2**.

### A2. ✅ ~~wiki 페이지 frontmatter scope 미검증~~ (2026-05-14 해소)

- **발견 맥락**: CLAUDE.md는 모든 wiki 페이지에 `scope` frontmatter를 요구하지만 `wiki_read`/`wiki_search`가 검증하지 않음.
- **해소**: `wiki_read`가 page frontmatter scope를 task scope와 대조, conflict면 content 대신 `blocked` 결과 반환. `wiki_search`는 cross-scope 페이지를 hit에서 제외(snippet leak 방지). frontmatter 없는 특수 페이지(log.md 등)는 무관. `a2_wiki_scope_block.yaml` golden으로 검증. (PR 29)
- **남은 부분**: raw 파일 scope 게이트는 별도 — raw에 frontmatter가 없어 path heuristic 필요. 빈도 낮아 보류.

### A3. ✅ ~~`Skill.policy_keys` 필드가 선언만 되고 미사용~~ (2026-05-14 해소 — 필드 삭제)

- **발견 맥락**: H8 skill registry. `health` skill이 `policy_keys=["scope:personal"]`을 선언하지만 읽는 코드가 없음.
- **해소**: A1의 R3는 `policy_keys`가 아니라 `Skill.scope`를 직접 입력으로 쓴다. 죽은 `policy_keys` 필드 삭제. (PR 28)

---

## B. 미완 기능 (Phase 4 follow-through)

### B1. 🟡 `channel.py`에 EmailChannel·KakaoChannel 어댑터 없음

- **발견 맥락**: F13. `Channel` Protocol만 추출, 구현체는 Telegram·Mock뿐.
- **왜 문제인가**: 멀티"채널"인데 채널이 하나. 단, 이건 *의도된 보류* — caller 없는 채널은 부채라 안 만듦.
- **해결 방향**: ds-digest digest 발송(email) 또는 카톡 capture 흐름이 Edith 본체로 들어올 때 어댑터 추가. **그 전엔 건드리지 말 것.**

### B2. 🟡 ds-digest "기여"(write) 경로 없음 — read-only만

- **발견 맥락**: F14. `GitHubPagesDigestSource`는 read. roadmap F14 설명의 "digest 기여는 request_approval 게이트"는 미구현.
- **왜 문제인가**: Edith가 digest에 소스 추가/제외를 제안할 수 없음.
- **해결 방향**: F17 `ApprovalExecutor` registry에 `ds_digest_pr` executor 추가 — `request_approval`로 큐잉 후 승인되면 ds-digest repo에 PR/issue. `harness/integrations/github_pr.py` 재사용.
- **의존**: F17 (완료) — 이제 executor 한 줄 추가 + integration만.

### B5. 🟡 F17 executor가 2종류만 — 나머지 action_type 미구현

- **발견 맥락**: F17. `default_registry()`에 `github_workflow_update_cron`·`gmail_send`만. `calendar_create`·`notion_update`·`slack_send`·`kakao_send`는 승인돼도 "executor 없음" 에러.
- **왜 문제인가**: 그 action들은 LLM이 request_approval로 큐잉은 되지만 실행 불가.
- **해결 방향**: 각 integration에 write 메서드 + executor 등록. calendar_create는 EventKit(macOS)로 실 검증 가능. 우선순위는 실사용 빈도순.
- **의존**: 일부는 E1(실 OAuth).

### B3. ✅ ~~F14/F15 소스가 morning brief에 미편입~~ (2026-05-14 해소)

- **발견 맥락**: `apple_health.format_for_brief()`가 caller 없는 dead helper. (digest는 이미 brief에 있었음 — 백로그 초안의 digest 언급은 부정확했음.)
- **해소**: `compose_brief`에 헬스 섹션 추가 — `get_health_source` → 오늘치 `daily_summary`. `render_text`에 🩺 줄. digest는 `get_digest_source`로 교체(EDITH_DS_DIGEST_URL → GitHub Pages 지원). (PR 30)

### B4. 🟢 papers·repo·jd skill의 `eval_globs`가 비어있음

- **발견 맥락**: H8. F7(repo)·F8(papers)·F9(jd)에 golden YAML이 원래 없음.
- **왜 문제인가**: CLAUDE.md "새 feature는 eval 먼저" 룰이 이 셋엔 적용 안 됨. `test_skills.py`는 빈 리스트를 통과시킴.
- **해결 방향**: F7/F8/F9 각각 golden 케이스 1개씩 작성 후 `eval_globs`에 연결. (기존 `tests/test_pr_review.py` 등이 로직은 커버하므로 🟢.)

---

## C. 빌드 하네스 (docs/05)

### C1. ✅ ~~빌드 하네스가 설계만 — 구현 0~~ (2026-05-14 해소, step 4는 사용자 실행 대기)

- **발견 맥락**: `docs/05_cc_harness.md` 작성. `scripts/execute.py`·`phases/`·`.claude/commands/build.md` 미구현.
- **해소**: `scripts/execute.py` StepExecutor (runner·commit_fn inject, --dry-run) + `tests/test_execute.py` 10 tests + `phases/b4-golden-evals/` 첫 실전 task + `.claude/commands/build.md`. (PR 31)
- **남은 부분**: step 4(`b4-golden-evals` 실행)는 실 `claude` subprocess라 사용자가 `python scripts/execute.py b4-golden-evals`로 1회 실검증해야 함. `feat-<task>` 브랜치 자동 생성은 v1 미포함.

---

## D. 일관성·중복 (consistency)

### D1. 🟡 CalendarEvent / EventKitCalendarSource가 두 군데 중복 정의

- **발견 맥락**: `harness/calendar.py`와 `harness/integrations/apple_calendar.py` 둘 다 `CalendarEvent`·`EventKitCalendarSource`를 정의. 후자를 전자가 어댑터로 감쌈.
- **왜 문제인가**: 같은 개념 두 타입. F2 `CalendarEvent`(id·attendees 있음) vs integration `CalendarEvent`(calendar_name·all_day 있음) — 필드가 달라 헷갈림.
- **해결 방향**: integration을 raw layer로 두고 `harness/calendar.py`만 public type으로 — 또는 둘을 합침. 헬스(`apple_health.py`)는 처음부터 단일 타입이라 이 패턴을 안 따라감 — calendar도 거기 맞추는 게 일관적.

### D2. ✅ ~~server.py가 `TelegramClient`를 직접 써서 `channel.py`를 안 거침~~ (2026-05-14 해소)

- **발견 맥락**: F13 직후. `channel.py`의 `TelegramChannel`이 만들어졌지만 `harness/server.py`는 여전히 `telegram_client.parse_update`/`send_message`를 직접 호출.
- **해소**: `make_app`이 `telegram_client`를 `TelegramChannel`로 감싸고, webhook 핸들러는 `Channel` 인터페이스(`parse_incoming`/`send`)만 본다. 새 채널 추가 시 server.py 안 바뀜. (PR 25)

### D3. 🟢 CLAUDE.md "Tool 사용 규칙"이 skill 도입을 반영 못 함

- **발견 맥락**: H8. `wiki/log.md`에 schema 개선 제안으로 기록해둠.
- **왜 문제인가**: CLAUDE.md가 `harness/tools/`만 언급, `harness/skills/`·`eval_globs` 강제를 모름.
- **해결 방향**: **사용자가 직접** CLAUDE.md 수정 (자기 갱신 정책상 Edith가 못 고침). "Tool 사용 규칙" → "Skill·Tool 사용 규칙".

---

## E. 운영 미완 (from docs/04 세션 로그)

### E1. 🟡 실 OAuth/권한 플로우 미검증

- **발견 맥락**: `docs/04_session_2026-04-29.md` §7 "아직 안 한 것".
- **항목**: Gmail 첫 OAuth flow(refresh_token 저장), EventKit 첫 권한 다이얼로그, `make run`으로 실 LLM 호출, Telegram `set_webhook` 실등록.
- **왜 문제인가**: F2/F3/F15 모두 Mock·fixture로만 검증됨. 실 데이터 경로는 한 번도 안 돌아봄.
- **해결 방향**: 사용자 본인 기기에서 1회씩 수동 검증 — Edith가 자동화 못 하는 영역(사람이 다이얼로그 클릭). 체크리스트로.

### E2. 🟢 Telegram webhook HTTPS 노출

- **발견 맥락**: docs/04 §7. 현재 8765는 HTTP. Telegram은 HTTPS public URL 강제.
- **해결 방향**: Tailscale Funnel 또는 Cloudflare Tunnel (PR #17에서 일부 진행됨 — 현황 확인 필요).

### E3. 🟢 CI 게이트 명령이 `ruff | tail`로 exit code를 가림

- **발견 맥락**: PR 25. `uv run ruff check ... | tail -2 && ...` — 파이프가 ruff의 exit 1을 가려서 lint 에러(PR 23 유입)가 커밋됨. PR 26에서 사후 수정.
- **해결 방향**: CI 게이트는 `make check` 단일 명령으로. 출력 자르려면 `tail`이 아니라 ruff 자체 옵션 또는 `set -o pipefail`.

---

## F. 외부 스킬 부착 (docs/07)

### F1. 🟡 PlayMCP 부착 아키텍처 미결정

- **발견 맥락**: `docs/07_external_skills_catalog.md` §4. PlayMCP(카카오 MCP)를 Edith에 붙이는 방식이 두 갈래.
- **선택지**: (a) Edith runtime이 MCP client가 되어 `mcp__PlayMCP__*` 직접 호출 — 얇지만 trace·policy 누락 위험. (b) MCP 툴을 `harness/tools/`로 1:1 래핑 — trace·policy 일관, 래퍼 코드 증가.
- **해결 방향**: Phase B 토론. R1(KakaoMemoChannel) 부착 PR 전에 결정 필요.
- **의존**: docs/07 R1-R4 부착 PR 전부 이 결정에 막힘.

### F2. 🟢 docs/07 R1-R4 외부 스킬 미부착

- **발견 맥락**: docs/07 ROI 분석. R1 KakaoMemoChannel · R2 youtube skill · R3 naver skill · R4 hwp.
- **해결 방향**: docs/07 §4 부착 순서대로 독립 PR. 각각 golden eval 동봉. F1 결정 후 착수.

---

## 처리 우선순위 (제안)

```
✅ 해소           A1·A2 scope · A3 policy_keys · B3 brief 편입 · C1 빌드 하네스 · D2 server↔channel
대기 (사용자)      C1 step 4 — `python scripts/execute.py b4-golden-evals` 실검증
3순위 (🟡)         D1 calendar 중복 정리  ·  B2 ds-digest write  ·  F1 PlayMCP 부착 결정
4순위 (🟢)         B4 golden 보강  ·  D3 CLAUDE.md (사용자)  ·  E2  ·  E3
상시               E1 실 OAuth — 사용자 수동
```

---

## 변경 이력

- 2026-05-14 v0.1 — Phase 4(H8·F13·F14·F15) 머지 직후 백로그 초안.
