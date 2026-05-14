# 06 · 설계 백로그 — 알려진 문제·미완·기술부채

> 2026-05-14 v0.1 · 살아있는 문서 (해소 시 줄 긋고 날짜 기록, 신규 발견 시 append)
> 목적: 독립적으로 해결 가능한 task들을 한 곳에 모아 "한 번에" 처리하기 위한 백로그.

각 항목은 **독립 task**로 잡을 수 있게 작성. `심각도` · `발견 맥락` · `왜 문제인가` · `해결 방향` · `의존`.
심각도: 🔴 기능/안전에 영향 · 🟡 일관성/유지보수 · 🟢 정리·문서.

---

## A. 정책·안전 (policy & safety)

### A1. 🔴 R3 scope cross-ref enforce 미구현

- **발견 맥락**: F15 health skill (scope=personal) 머지 시. `harness/policies.py`가 R3를 "Phase 2 frontmatter 도입 후"로 미뤄둠 (`allow()` 주석).
- **왜 문제인가**: health·work skill이 scope를 *선언*만 하고 런타임이 강제하지 않는다. work/school task에서 `health_summary`가 호출돼도 안 막힌다. CLAUDE.md 답변 규칙 3번(scope 분리)이 코드로 강제되지 않음.
- **해결 방향**: `policy.allow(tool, args, scope)`에 R3 추가 — tool이 속한 skill의 `scope`와 task `scope`가 충돌하면(`personal` skill을 `work` task에서) block. skill→tool 역인덱스가 필요 (`harness/skills/`에서 빌드).
- **의존**: `harness/skills/` (있음). frontmatter 기반 wiki scope 체크는 별도(A2).

### A2. 🟡 wiki 페이지 frontmatter scope 미검증

- **발견 맥락**: CLAUDE.md는 모든 wiki 페이지에 `scope` frontmatter를 요구하지만 `wiki_read`/`wiki_write`가 검증하지 않음.
- **왜 문제인가**: scope=work 페이지를 personal task가 읽어도 통과. R3의 절반(tool 단)만 막아선 leak 못 막음.
- **해결 방향**: `wiki_read` 결과의 frontmatter `scope`를 task scope와 대조, 불일치 시 redact 또는 block.
- **의존**: A1과 같은 PR로 묶는 게 자연스러움.

### A3. 🟡 `Skill.policy_keys` 필드가 선언만 되고 미사용

- **발견 맥락**: H8 skill registry. `health` skill이 `policy_keys=["scope:personal"]`을 선언하지만 읽는 코드가 없음.
- **왜 문제인가**: 죽은 필드 = 거짓 신호. 보는 사람이 "정책이 걸려있다"고 오해.
- **해결 방향**: A1 구현 시 `policy_keys`를 실제 enforce 입력으로 쓰거나, 안 쓸 거면 필드 삭제.

---

## B. 미완 기능 (Phase 4 follow-through)

### B1. 🟡 `channel.py`에 EmailChannel·KakaoChannel 어댑터 없음

- **발견 맥락**: F13. `Channel` Protocol만 추출, 구현체는 Telegram·Mock뿐.
- **왜 문제인가**: 멀티"채널"인데 채널이 하나. 단, 이건 *의도된 보류* — caller 없는 채널은 부채라 안 만듦.
- **해결 방향**: ds-digest digest 발송(email) 또는 카톡 capture 흐름이 Edith 본체로 들어올 때 어댑터 추가. **그 전엔 건드리지 말 것.**

### B2. 🟡 ds-digest "기여"(write) 경로 없음 — read-only만

- **발견 맥락**: F14. `GitHubPagesDigestSource`는 read. roadmap F14 설명의 "digest 기여는 request_approval 게이트"는 미구현.
- **왜 문제인가**: Edith가 digest에 소스 추가/제외를 제안할 수 없음.
- **해결 방향**: ds-digest repo에 PR/issue를 여는 tool — `EXTERNAL_WRITE_TOOLS`에 등록 + `request_approval` 필수.
- **의존**: `harness/integrations/github_pr.py` 재사용 가능.

### B3. 🟡 F14/F15 소스가 morning brief에 미편입

- **발견 맥락**: `apple_health.format_for_brief()`, ds-digest `digest_latest`가 있지만 `harness/morning.py`가 호출하지 않음.
- **왜 문제인가**: 만든 helper에 caller가 없음. morning brief가 일정·메일만 보고 digest·헬스를 빼먹음.
- **해결 방향**: `harness/morning.py`에 digest 최신 1줄 + 헬스 요약 1줄 추가. golden `f4_morning_brief.yaml` 갱신.

### B4. 🟢 papers·repo·jd skill의 `eval_globs`가 비어있음

- **발견 맥락**: H8. F7(repo)·F8(papers)·F9(jd)에 golden YAML이 원래 없음.
- **왜 문제인가**: CLAUDE.md "새 feature는 eval 먼저" 룰이 이 셋엔 적용 안 됨. `test_skills.py`는 빈 리스트를 통과시킴.
- **해결 방향**: F7/F8/F9 각각 golden 케이스 1개씩 작성 후 `eval_globs`에 연결. (기존 `tests/test_pr_review.py` 등이 로직은 커버하므로 🟢.)

---

## C. 빌드 하네스 (docs/05)

### C1. 🔴 빌드 하네스가 설계만 — 구현 0

- **발견 맥락**: `docs/05_cc_harness.md` 작성. `scripts/execute.py`·`phases/`·`.claude/commands/build.md` 미구현.
- **왜 문제인가**: roadmap §4.4.3이 "Phase 4부터 빌드 하네스로 짓는다"고 했지만 도구가 없음. Phase 4 자체는 사람이 수동으로 지음.
- **해결 방향**: `docs/05` §4 도입 순서대로 — (1) `phases/` 스키마 (2) `StepExecutor` (3) `.claude/commands/build.md` (4) 첫 실전 task. 독립 PR 3-4개로 분해 가능.
- **의존**: 없음. 단 step 2(StepExecutor)는 Claude Code subprocess 호출이라 테스트가 까다로움 — `forward_fn` inject 패턴처럼 executor도 runner inject 가능하게 설계할 것.

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

---

## 처리 우선순위 (제안)

```
1순위 (🔴)         A1+A2 scope enforce  ·  C1 빌드 하네스 step 1-2
2순위 (🟡 caller)  D2 server↔channel  ·  B3 morning brief 편입
3순위 (🟡)         D1 calendar 중복 정리  ·  B2 ds-digest write
4순위 (🟢)         B4 golden 보강  ·  D3 CLAUDE.md (사용자)  ·  E2
상시               E1 실 OAuth — 사용자 수동
```

---

## 변경 이력

- 2026-05-14 v0.1 — Phase 4(H8·F13·F14·F15) 머지 직후 백로그 초안.
