# 10 · 상용화 스프린트 — 빌드 스펙 (Codex 실행용)

> 출처: 5차원 상용화 감사(견고성·보안·온보딩·기능·품질) ~66건 → 우선순위화.
> 원칙: **무료(유료 LLM 불필요)·결정적·테스트 동봉**. 각 항목 구현 후 `make check`+`make eval` 그린, 커밋(`PR NN: …`).
> Tier 1 → 4 순서. 한 Tier 끝낼 때마다 커밋. AGENTS.md의 규약 준수(특히 R1/R2/secrets, 골든 동봉).

---

## Tier 1 — 견고성 + 보안 (상용 dealbreaker, 먼저)

### T1.1 무중단 graceful degradation
- **문제**: Gmail/Calendar/digest/health 중 하나라도 실패하면 `compose_brief`가 예외→ `/ui/brief`·`/ui/summary` 500/무한로딩, GUI "불러오는 중…" 고착.
- **할 일**: `harness/morning.py compose_brief` 각 소스(calendar/mail/digest/health)를 개별 try/except로 감싸 **부분 brief + per-source 에러 표식** 반환. `server.py` `/ui/summary`·`/ui/brief`는 절대 500 안 나게(부분 ok + `errors` 필드). `integrations/gmail._batch_fetch`는 드롭된 수를 로깅/반환. Google API에 타임아웃(예: build 시 `num_retries`/httplib2 timeout, 또는 호출 래핑).
- **GUI**: 홈/브리프가 소스 실패 시 "불러오는 중" 대신 **에러/부분 상태** 표시.
- **검증**: 실패하는 소스 mock 주입 → brief가 예외 없이 부분 반환; `/ui/summary` ok=True + 에러 표기. 단위 테스트 추가.

### T1.2 GUI/API 인증
- **문제**: `/ask`·`/ui/*`가 무인증 — 바인드 호스트 네트워크의 누구나 호출 가능.
- **할 일**: `EDITH_GUI_TOKEN` env 있으면 `/ask`·`/ui/*`에 토큰 검사(헤더 `X-Edith-Token` 또는 쿠키). 없으면 127.0.0.1 바인드 + 起動 시 경고 로그. GUI는 토큰을 localStorage에 저장/전송, 없으면 입력 프롬프트.
- **검증**: 토큰 설정 시 무토큰 401 / 정상토큰 200 테스트. 기존 `/webhook/telegram` HMAC 경로는 유지.

### T1.3 동시성 안전 쓰기
- **문제**: `ApprovalQueue`(approvals.json)·`ProposalStore`(proposals.json)·suggestions ledger·brief 캐시가 read-modify-write TOCTOU. 멀티 워커/동시 요청 시 손상.
- **할 일**: JSON 저장을 **atomic**(임시파일 write + `os.replace`)으로. 가능하면 파일 락(`fcntl`)으로 read-modify-write 보호. brief 캐시는 앱 인스턴스 락.
- **검증**: 저장이 atomic(중간 크래시에도 손상 없음) 단위 테스트. 동시 create 2회 → 둘 다 보존.

### T1.4 입력 검증
- **할 일**: `/ui/approve`·`/ui/proposals/decide`·`/ask` payload 검증(필드/타입) → 잘못되면 400. executor가 params를 실행 전 검증(이미 일부 있음 — gmail to/subject/body, cron path/cron). 누락 시 명확한 에러.
- **검증**: 잘못된 payload 400 테스트.

---

## Tier 2 — 온보딩 / UX

### T2.1 `harness doctor`
- **할 일**: cli에 `doctor` 명령 — 점검: `.env`의 EDITH_LLM + 해당 키, Google OAuth 토큰 존재·scope, `[google]` deps, EDITH_MAIL/CALENDAR_BACKEND, raw/wiki/harness 디렉토리. 각 항목 ✓/✗ + **고치는 법** 한 줄. 종료코드(문제 있으면 1).
- **검증**: tmp home에서 doctor가 구조화 상태 반환(누락 항목 표기) 테스트.

### T2.2 GUI Settings 탭
- **할 일**: GUI에 Settings 뷰 — 모델(EDITH_LLM/model), 메일·캘린더 backend, EDITH_MAX_TOKENS 조회/변경. 서버 `/ui/settings` GET/POST — `.env`를 **안전하게**(기존 키 보존, 백업) 갱신하거나 `harness/settings.json`에 저장 후 런타임 반영. secrets 값은 노출 금지(설정 여부만).
- **검증**: GET/POST /ui/settings 테스트.

### T2.3 GUI 상태 폴리시
- **할 일**: 빈 상태 안내(모두 0일 때 "다음 단계" 가이드), 로딩 스피너, 에러는 명시 표시(무한로딩 금지), **반응형/모바일**(미디어 쿼리), 대화 history **localStorage 영속**(F5에도 유지).
- **검증**: HTML 서빙 + 주요 요소 존재(기존 test_webui 확장).

### T2.4 첫 실행 에러 친절화
- **할 일**: 키/설정 누락 시 난해한 stacktrace 대신 "`harness doctor` 참고" 류 안내. runtime/server 시작 시 필수 env 점검 후 친절 메시지.

---

## Tier 3 — 기능 / 차별화

### T3.1 실 캘린더 일정 생성 executor
- **할 일**: `GOOGLE_SCOPES`에 `calendar.events`(쓰기) 추가(사용자 재인증 필요 — 문서화). `GoogleCalendarSource.create_event(...)`. `executor.py`에 `calendar_create` executor + registry 등록. propose→approve→execute 경로로 실제 일정 생성(R2 준수). 토큰/스코프 없으면 안전 실패.
- **검증**: mock service로 executor 단위 테스트(events.insert 호출·결과). scope 문서 갱신(docs/09).

### T3.2 패턴 마이닝 (반복작업 감지)
- **할 일**: `harness/patterns.py` `mine_patterns(traces)` — task 토큰 자카드로 반복 클러스터 → `RecurringPattern(label, support, is_time_regular, suggested_cron, level['observe'|'suggest'])`. `pattern_match`/`pattern_list` tool. brief/체크인에 "🔁 늘 하시던 X" 1줄(suggest). 자동 실행 X.
- **검증**: golden(동일 fingerprint 3개→패턴 1개·자카드<0.6 분리) + 단위.

### T3.3 선호 학습 (피드백 집계)
- **할 일**: `suggestion_feedback.jsonl` reject 집계 → 카테고리/신호별 억제 강도 학습(결정적 카운트). 이미 있는 suppression을 데이터로 강화.
- **검증**: 단위 테스트.

### T3.4 (선택) 알림·digest 실 전송
- ds-digest 실연동(EDITH_DS_DIGEST_URL=본인 GitHub Pages), 이메일/OS 알림 채널.

---

## Tier 4 — 품질 / 테스트 하드닝

- **e2e**: 제안→승인→실행 풀 서버 경로 통합 테스트.
- **커버리지**: `/ask` history 파라미터 전달, batch 부분실패 콜백, OAuth refresh(allow_flow=False) 경로, `/ui/summary` 에러 케이스, 새 triage 카테고리 golden.
- **정리**: dead code(`_fetch_message` 등) 제거, 에러 패턴 일관화.

---

## 정직한 천장 (이번 스프린트 밖)
멀티테넌시·결제·SOC2/컴플라이언스·확장 인프라는 별도 규모. 본 스프린트 목표는
**"1인 데모 → 견고한 개인 제품(혼자/소수 판매 가능)"** 수준까지.
