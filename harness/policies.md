# Harness Policies (H5)

> `harness/policies.py`의 `allow()` 함수가 강제하는 룰을 사람이 읽을 수 있게 정리.
> 마크다운이 spec, Python이 구현. 둘이 어긋나면 마크다운이 진실.

## R1. `raw/` is immutable

raw 디렉토리 안 파일을 수정·삭제하는 tool은 거부.

- 거부: `raw_write`, `raw_delete`, `raw_modify`, `raw_truncate`
- 허용: 새 파일 생성은 `capture_text`로만 (`raw/captures/<timestamp>_<source>.md` 형식)

## R2. External write 는 승인 큐 거침

비가역 외부 발송 도구는 `request_approval`을 먼저 거쳐야 함.

- 거부 대상: `gmail_send`, `calendar_create`, `calendar_update`, `notion_update`,
  `github_commit`, `github_push`, `slack_send`, `kakao_send`
- 승인 큐 통과 시 별도 executor가 실행 (Phase 3 F5에서)

## R3. Scope cross-reference 금지

- task `scope=personal` 또는 `scope=school`일 때 `raw/` 안에서 work 표식 파일 retrieve 금지.
- task `scope=work`일 때 외부 (anthropic) LLM 호출 금지 → 사내 endpoint만.
- `scope=mixed` task는 분리 후 각각 처리, 또는 사용자 명시 동의 필요.

> Phase 1엔 raw 파일 자체에 scope 메타가 없어서 path heuristic으로만 판단. 정식 enforce는 Phase 2에서 frontmatter scope 읽고 강제.

## R4. PII redaction (외부 LLM payload)

외부 LLM 호출 직전 payload에 다음 패턴 매치되면 redact 또는 abort:

| 종류 | 정규식 |
|---|---|
| 이메일 주소 | `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` |
| 한국 휴대폰 | `01[016789]-?\d{3,4}-?\d{4}` |
| 주민등록번호 | `\d{6}-?[1-4]\d{6}` |
| Anthropic API key | `sk-ant-[A-Za-z0-9_\-]{20,}` |
| AWS access key | `AKIA[A-Z0-9]{16}` |
| OpenAI key | `sk-[A-Za-z0-9]{32,}` |

- 동작: `redact_pii(text)` → 매치 부분을 `[REDACTED]`로 치환.
- 외부 호출 전 `check_external_payload(text)` → 매치 발견 시 차단 + 사용자 알림.

## R5. Budget 강제

- `Budget(max_tokens, max_steps, max_seconds)` 어느 하나 초과 시 즉시 종료.
- runtime이 enforce. 정책 엔진 영역 아님 (참조용).

## 변경 이력

- 2026-04-28 v0.1 — H5 풀 정책 (R1-R5).
