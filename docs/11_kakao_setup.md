# 11 · KakaoTalk 나에게 보내기 push 세팅

> Edith의 아침 brief 요약을 카카오톡 **나에게 보내기**로 받기 위한 1회 세팅.
> 이 채널은 본인 메모 엔드포인트만 사용한다. 친구/채팅방 등 제3자 발송 scope와 API는 쓰지 않는다.

토큰은 `secrets/kakao_token.json`에 저장하고 커밋하지 않는다. 저장 파일 권한은 코드에서
`0o600`으로 맞춘다.

## 1. Kakao Developers 앱 만들기

1. https://developers.kakao.com 에 로그인
2. **내 애플리케이션 → 애플리케이션 추가하기**
3. 앱의 **REST API 키**를 복사해 `.env`에 저장:

```bash
KAKAO_REST_API_KEY=...
```

## 2. 카카오 로그인과 동의항목

1. 앱 설정에서 **카카오 로그인 활성화**
2. Redirect URI를 로컬 테스트용으로 등록
   - 예: `http://127.0.0.1:8765/oauth/kakao/callback`
3. **동의항목**에서 `talk_message` 권한을 설정
   - 목적: 카카오톡 메시지 **나에게 보내기**
   - friends, talk message to others 등 제3자 발송 권한은 요청하지 않는다.

## 3. 토큰 발급

자동 브라우저 flow는 아직 CLI에 붙지 않았다. Kakao Developers REST API 문서의
카카오 로그인 절차로 authorization code를 받은 뒤 token API를 호출해
`access_token`과 `refresh_token`을 발급한다.

발급한 토큰을 아래 파일에 저장:

```bash
mkdir -p ~/edith/secrets
chmod 700 ~/edith/secrets
$EDITOR ~/edith/secrets/kakao_token.json
chmod 600 ~/edith/secrets/kakao_token.json
```

형식:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1790000000
}
```

`expires_at`은 없어도 된다. API가 401을 반환하면 Edith가 refresh token으로 access token을
갱신하고 다시 한 번 전송한다.

## 4. 상태 확인과 brief push

```bash
uv run harness oauth kakao --status
uv run harness brief --push kakao
```

카카오 text template은 본문 길이 제한이 짧기 때문에 전체 brief를 보내지 않는다.
Edith는 날짜, Top 3, 일정/안읽음 카운트만 200자 이내로 요약해서 보내고,
전체 brief는 GUI 링크(`EDITH_GUI_URL`, 기본 `http://127.0.0.1:8765`)로 보게 한다.

## 보안 메모

- `.env`와 `secrets/`는 `.gitignore` 대상이다.
- 토큰 값은 CLI 상태 출력에 노출하지 않는다.
- 모든 카카오 전송 직전 `policies.guard_outbound` PII 게이트를 통과한다.
- 이 구현은 `POST /v2/api/talk/memo/default/send`만 호출한다.
