# 09 · Gmail + Google Calendar 실연동 (OAuth) 세팅

> Edith가 **실제 내 Gmail·구글 캘린더**를 읽고(브리프·선제 제안), 승인 후 실제 메일을
> 발송하게 하는 1회 세팅. 토큰은 `secrets/`(gitignore)에만 저장되고 커밋되지 않는다.

단일 OAuth 토큰 하나로 Gmail(읽기+발송)과 Calendar(읽기)를 모두 커버한다.
scope: `gmail.readonly` · `gmail.send` · `calendar.readonly` (최소 권한).

## 0. 라이브러리 설치

```bash
cd ~/edith
uv pip install -e ".[google]"     # google-auth(-oauthlib), google-api-python-client
```

## 1. Google Cloud — OAuth 클라이언트 만들기 (사용자 수동, ~10분)

1. https://console.cloud.google.com → 새 프로젝트 (예: `edith`)
2. **API 사용 설정**: "API 및 서비스 → 라이브러리"에서
   - **Gmail API** 사용 설정
   - **Google Calendar API** 사용 설정
3. **OAuth 동의 화면**:
   - User Type: **External**
   - 앱 이름/이메일만 채우고 저장
   - **테스트 사용자**에 **본인 Gmail 주소 추가** (게시 안 해도 본인은 사용 가능)
   - Scopes는 여기서 추가 안 해도 됨 (코드가 요청)
4. **사용자 인증 정보 → OAuth 클라이언트 ID 만들기**:
   - 애플리케이션 유형: **데스크톱 앱**
   - 만든 뒤 **JSON 다운로드**
5. 받은 JSON을 여기로:

```bash
mkdir -p ~/edith/secrets
mv ~/Downloads/client_secret_*.json ~/edith/secrets/google_oauth.json
```

> 경로를 바꾸려면 `GOOGLE_OAUTH_CLIENT_SECRETS_FILE` 환경변수로 override 가능.

## 2. 동의 flow 실행 (토큰 저장)

```bash
uv run harness oauth google
```

- 브라우저가 열림 → 본인 Google 계정 동의 → "앱이 확인되지 않음"이 뜨면
  *고급 → 안전하지 않은 페이지로 이동*(본인 테스트 앱이라 정상)
- 완료되면 `secrets/google_token.json` 저장. 이후 자동 갱신.

확인:
```bash
uv run harness oauth google --status
```

## 3. 실연동 켜기

읽기 소스를 Google로 전환 (환경변수):

```bash
export EDITH_MAIL_BACKEND=gmail
export EDITH_CALENDAR_BACKEND=google
uv run harness brief          # 실제 내 메일 triage + 실제 오늘 일정
```

`.env`에 넣어두면 영구 적용:
```
EDITH_MAIL_BACKEND=gmail
EDITH_CALENDAR_BACKEND=google
```

GUI도 동일 — 그 환경변수가 떠 있는 셸에서 `make serve` 하면 Brief 탭이 실데이터.

> macOS에서 Apple 캘린더(EventKit)를 그대로 쓰려면 `EDITH_CALENDAR_BACKEND`를
> 비워두면 된다(기본값이 EventKit). Google로 보려면 `=google`.

## 4. 실제 메일 발송 (승인 필수)

발송은 **읽기와 분리**된 외부 write다. 직접 호출 불가 —
정책 R2 → 승인 큐 → executor 경로만 탄다:

1. (LLM/제안이) `gmail_send` step을 제안 → Proposals/Approvals 탭에 pending
2. 사람이 **승인(yes)** → `ApprovalExecutor`가 `GmailSource.send_message` 실행
3. 미승인 자동 발송은 정책 위반 (trace 빨간 표시)

토큰에 `gmail.send` scope가 있으므로 승인만 하면 실제 발송된다.

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `Google API 클라이언트 필요` | `uv pip install -e ".[google]"` 안 함 |
| `OAuth client secret 없음` | `secrets/google_oauth.json` 위치 확인 |
| `유효한 Google 토큰 없음` | `harness oauth google` 먼저 실행 |
| 동의 화면 "확인되지 않은 앱" | 본인 테스트 앱 정상 — 고급→계속 |
| 브리프에 일정 0건 | `EDITH_CALENDAR_BACKEND=google` 떴는지, 토큰 scope에 calendar 있는지 확인 |
| 토큰 만료/scope 변경 | `secrets/google_token.json` 지우고 `harness oauth google` 재실행 |

## 보안 메모

- `secrets/`는 `.gitignore` 대상 — client secret·token 절대 커밋 안 됨.
- 토큰 파일은 **0o600(소유자 전용)** 으로 저장 — 같은 머신 타 사용자도 못 읽음.
- 토큰 값은 로그·trace·CLI 출력에 노출되지 않음 (`--status`는 scope/계정만 표시).
- scope는 읽기 + 발송 최소만. 메일 삭제·수정(modify), 캘린더 쓰기 권한은 요청 안 함.
- 읽기·발송 경로는 브라우저 동의 flow를 트리거하지 않음 — 토큰 발급은 `harness oauth google`로만.
