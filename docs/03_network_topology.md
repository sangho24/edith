# 03 · Edith Network Topology — 동작 원리

> 2026-04-29 · Phase 3 F12 배포 직후 학습 노트
> 대상: 처음 self-host + Tailscale + relay 패턴 만지는 사람

이 문서는 **왜 이런 구조** 인지, **각 부분이 어떤 일을 하는지**, **실패하면 어디서 막히는지** 설명합니다. 단순 셋업 가이드가 아니라 mental model 만들기 위한 글.

---

## 1. 우리가 풀고 싶은 문제

> "MacBook 에서 돌아가는 Edith 가 외부 이벤트 (Telegram 메시지, OAuth 콜백, 카톡 push 트리거 등) 를 받게 하고, 외부 어디서든 (회사·핸드폰) Edith 한테 질문할 수 있어야 한다."

이게 단순해 보이지만 두 가지 근본 제약이 있어요:

### 제약 1 — MacBook 은 공인 IP 가 없다

집 라우터 NAT 뒤에 있어서 외부 서비스 (Telegram 서버, Google OAuth) 가 직접 못 부름. 포트포워딩 가능하지만 IP 가 동적이라 깨지기 쉽고, 보안 노출 큼.

### 제약 2 — MacBook 은 항상 켜져 있지 않다

가방에 넣고 다님 → sleep. 근데 외부 webhook 은 시도 시점에 닿아야 함. "MacBook 깨어났을 때 처리" 가 안 됨.

---

## 2. 해결책 — 3계층 토폴로지

```
┌─────────────────────────────────────────────────┐
│                  외부 세계                       │
│  Telegram · Google · Kakao · GitHub · 사용자    │
└──────────────────┬──────────────────────────────┘
                   │ HTTPS (공인 인터넷)
                   ▼
┌─────────────────────────────────────────────────┐
│  ☁️  Oracle VPS (edith-relay)                    │
│     공인 IP: 168.110.120.197                     │
│     역할: 우편함 (24/7 켜져있음, stateless)       │
│     - webhook 수신                                │
│     - HMAC 검증                                   │
│     - 큐잉 (MacBook 잠들어있을 때)                │
└──────────────────┬──────────────────────────────┘
                   │ Tailscale (사설 mesh, 암호화)
                   ▼
┌─────────────────────────────────────────────────┐
│  🍎 MacBook (Edith 본체)                         │
│     Tailscale IP: 100.79.238.53                  │
│     역할: 두뇌 (raw·wiki·LLM call)                │
└─────────────────────────────────────────────────┘
                   ▲
                   │ Tailscale
                   │
┌──────────────────┴──────────────────────────────┐
│  📱 iPhone                                       │
│     Tailscale IP: 100.78.97.10                   │
│     역할: 입력·조회 단말                          │
└─────────────────────────────────────────────────┘
```

각 계층의 의도:

| 계층 | 책임 | 안 가지는 책임 |
|---|---|---|
| 외부 | 이벤트 발생 | Edith 내부 정보 |
| VPS | 공인 진입점 + 신원 검증 | 데이터 저장, LLM 호출 |
| MacBook | 모든 실제 처리 | 외부 직접 노출 |
| iPhone | 사용자 인터페이스 | 데이터 (조회만) |

---

## 3. Tailscale 은 도대체 뭐 하는 거야?

### 한 줄 요약

> "내 모든 기기를 사설 LAN 안에 있는 것처럼 만들어주는 VPN mesh."

전통적인 VPN (회사 OpenVPN 같은 거) 은 **hub-and-spoke** — 모든 트래픽이 중앙 서버 거침. 느리고 단일 장애점.

Tailscale 은 **mesh** — 기기 A 와 기기 B 가 직접 연결. 중앙 서버는 키 교환 + 라우팅 정보만 관리.

### 어떻게 NAT 뒤에 있는 기기들이 직접 연결되지?

이게 Tailscale 의 핵심 마법인데 **WireGuard + STUN/ICE/DERP** 조합:

1. **WireGuard** — 커널 레벨 암호화 터널 프로토콜 (빠르고 가벼움)
2. **STUN/ICE** — NAT 뚫기 (UDP hole punching). 양쪽이 동시에 같은 포트로 패킷 보내면 NAT 가 "응 이건 응답이네" 하고 통과시킴.
3. **DERP** — STUN 안 되면 Tailscale 의 중계 서버로 fallback (최후 수단). 좀 느려짐.

우리 ping 결과를 다시 보면:
```
pong from edith-relay (100.84.196.71) via DERP(tok) in 112ms     ← 처음엔 도쿄 DERP 경유
pong from edith-relay (100.84.196.71) via 168.110.120.197:41641 in 31ms  ← 직접 UDP 연결됨
```

처음엔 양쪽 NAT 정보를 모르니까 DERP (도쿄 중계 서버) 거쳐서 통신 → 112ms. 그 사이에 STUN 으로 양쪽 IP/Port 교환 → 직접 UDP 연결 성립 → 31ms 로 단축.

### 왜 이게 우리 프로젝트에 결정적인가

**전통적 방식이면**: VPS 가 MacBook 으로 forward 하려면 MacBook 이 공인 IP 가 있어야 하거나 reverse SSH tunnel 필요. 둘 다 깨지기 쉽고 셋업 복잡.

**Tailscale 사용**: VPS 도 mesh 의 일원 → MacBook Tailscale IP (`100.79.238.53`) 로 그냥 HTTP 호출. NAT 무관. 양쪽 다 어디 있든 통함.

---

## 4. VPS Relay 패턴

### 왜 stateless 인가

`vps/relay.py` 는 데이터 저장 X — 받자마자 forward. 이유:

- **재배포 자유**: 컨테이너 죽이고 다시 띄워도 데이터 손실 X
- **공격 표면 최소**: 털려도 wiki·raw 데이터 안 새어나감
- **싸게 운영**: VPS 1GB RAM 으로도 충분

### HMAC 검증

```python
# vps/relay.py 의 _verify_signature
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
return hmac.compare_digest(expected, given)
```

외부 webhook 이 진짜 우리가 등록한 source 인지 확인. 같은 `RELAY_SECRET` 을 양쪽 (sender + relay) 이 알고 있어서, sender 가 body 의 HMAC 서명을 헤더에 박아 보냄. 누군가 가짜로 webhook 흉내내려 해도 secret 모르면 서명 못 만듦.

**왜 token 인증이 아니라 HMAC?**

Token 은 길어도 한 번 노출되면 끝. HMAC 은 **메시지 자체에 서명** 해서 body 변조도 잡힘. webhook 같이 "공개 URL 로 누구나 POST 할 수 있는" 환경에 적합.

### Forward 함수 추상화

```python
def make_app(forward_fn: Callable[[str, dict], Any] | None = None) -> FastAPI:
```

`forward_fn` 이 None 이면 그냥 OK 응답만 (smoke test). 실제 운영에선 HTTP POST to MacBook Tailscale IP. 테스트에선 mock 함수.

이렇게 한 이유: **테스트할 때 실제 네트워크 안 부르도록.** `tests/test_relay.py` 가 FastAPI TestClient 만 쓰고 fake_forward 로 검증하는 게 가능.

---

## 5. Public IP vs Tailscale IP — 언제 뭘 쓰나

### Public IP (`168.110.120.197`)

**용도**: 외부 서비스 → VPS 진입

- Telegram webhook URL
- Kakao OAuth callback
- GitHub Actions push
- 본인이 카페에서 SSH 로 VPS 디버깅

**보안**: 0.0.0.0/0 노출 → HMAC 으로 보호. SSH 는 key 인증만. Security List 로 포트 제한 (22, 8765 만 열림).

### Tailscale IP (VPS: `100.84.196.71`, MacBook: `100.79.238.53`, iPhone: `100.78.97.10`)

**용도**: mesh 내부 통신

- VPS → MacBook (relay forward)
- iPhone → MacBook (직접 query)
- iPhone → VPS (queue 조회)
- MacBook → VPS (배포·로그 확인)

**보안**: WireGuard 암호화 + 본인 계정 기기만 접근. 공개 인터넷에서 절대 안 보임.

### 룰 오브 thumb

> **외부에서 들어와야 = Public IP. 내 기기끼리 = Tailscale IP.**

OAuth callback URL, webhook URL → Public.
edith.MacBook 에 raw 파일 sync, VPS log tail → Tailscale.

---

## 6. OAuth Callback 흐름 (Google 예시)

```
사용자 브라우저
   │
   │ 1. "Sign in with Google" 클릭
   ▼
Google OAuth 서버
   │
   │ 2. consent 화면 후 redirect_uri 로 code 보냄
   ▼
http://localhost:8765/oauth/google/callback     ← 첫 OAuth 시 MacBook 의 로컬
또는 https://relay.your-domain/oauth/google/callback ← 운영 (VPS 통해)
```

### 첫 OAuth 가 localhost 인 이유

데스크톱 앱 OAuth flow 는 **사용자가 직접 브라우저 띄워서 로그인** → redirect 가 localhost 로 와야 토큰 잡을 수 있음. CLI 앱도 마찬가지 — `google-auth-oauthlib` 가 임시 로컬 서버 띄워서 한 번 잡고 끝.

이걸로 받은 **refresh_token** 만 저장하면 그 다음부터는 OAuth UI 없이 access_token 갱신 가능 → 자동화 OK.

### 운영 시 VPS 가 받는 OAuth callback

이미 refresh_token 받은 후의 일상 갱신은 callback URL 안 거침. 다만 만료되거나 새 scope 추가 시 다시 OAuth flow 필요한데, 이때 **MacBook 깨어있어야** localhost callback 받을 수 있음.

→ 이걸 회피하려면 redirect_uri 를 `https://relay.../oauth/google/callback` 으로 등록하고 VPS 가 받아서 MacBook 으로 forward (Tailscale 통해).

이 패턴은 **카카오 OAuth 처럼 Public URL 강제** 하는 곳에 필수. Google 은 둘 다 지원.

---

## 7. Telegram Bot 흐름 (계획)

```
iPhone Telegram 앱
   │
   │ "오늘 일정 알려줘"
   ▼
Telegram 서버
   │
   │ webhook (POST)
   ▼
https://relay.your-domain/webhook/telegram     ← VPS Public IP
   │
   │ HMAC 검증 → forward
   ▼ (Tailscale)
http://100.79.238.53:8765/ask                  ← MacBook 의 harness server
   │
   │ harness runtime → tool calls → Grok LLM
   ▼
응답 텍스트
   │
   │ POST sendMessage
   ▼
Telegram 서버
   │
   ▼
iPhone Telegram 앱 (답변 수신)
```

**왜 webhook 이고 long polling 아닌가**: Telegram 도 둘 다 지원하는데 webhook 이 즉시성 좋고 자원 효율적. Long polling 은 클라이언트가 계속 요청 보내야 해서 MacBook 바쁨.

**왜 VPS 거치고 직접 MacBook 으로 안 보내나**: Telegram 서버는 **HTTPS public URL** 강제. MacBook 은 자체 인증서·공인 IP 어렵. VPS 가 nginx + Let's Encrypt 로 HTTPS 받아서 가운데 끼는 게 표준.

---

## 8. iOS Shortcut — 가장 단순한 핸드폰 진입점

### Tier 1 (가장 단순, MacBook 깨어있을 때)

```
iPhone Shortcut "Ask Edith"
   │
   │ 텍스트 입력 → URL 호출
   ▼ (Tailscale 직접)
http://100.79.238.53:8765/ask?q=...            ← MacBook 의 harness server
   │
   ▼
응답 표시
```

VPS 안 거치고 mesh 내부 직통. Tailscale 앱이 깔린 iPhone 에서만 작동. 외출 중에도 MacBook 켜져있으면 OK.

### Tier 2 (MacBook 잠들어있어도)

```
iPhone Shortcut
   │
   ▼ HTTPS (공인 인터넷)
https://relay.your-domain/ask
   │
   │ 큐에 적재
   ▼
relay 의 메모리 (또는 Redis 같은 거)
   │
   │ MacBook 깨어나면 polling
   ▼
MacBook → 처리 → 답변 push back to iPhone
```

이건 PR #15 이후 단계.

---

## 9. 우리 셋업의 강점·약점 정직하게

### 강점

- **자체호스팅 = 데이터 100% 본인 소유**. raw 데이터 클라우드 안 올라감.
- **비용 거의 0** (Oracle Free + Tailscale 무료 tier).
- **Tailscale 덕분에 NAT 무관**, 어디서든 작동.
- **Stateless relay** 라 VPS 털려도 데이터 손실 X.

### 약점

- **MacBook sleep 시 cron 못 돌아감** — GitHub Actions cron 으로 우회 (F8).
- **iPhone 에 Tailscale 깔아야** Tier 1 가능. 외부 사람한텐 못 줌 (사용자 개인 도구라 OK).
- **HTTPS 인증서 관리 필요** (Let's Encrypt + nginx 또는 Cloudflare Tunnel).
- **Oracle Free Tier 가 영구 보장 X** — 정책 바뀌면 마이그레이션 필요.

---

## 10. 디버깅 체크리스트 (실패 시 어디부터 보나)

### "외부에서 VPS 안 닿음"

1. `curl http://168.110.120.197:8765/health` (다른 네트워크에서)
2. Oracle Security List 에 8765 ingress 있나
3. VPS 안에서 `sudo ss -tlnp | grep 8765` — relay 떠있나
4. `sudo ufw status` — VPS 자체 방화벽

### "VPS → MacBook forward 안 됨"

1. `tailscale status` — 양쪽 다 online
2. `tailscale ping macbookair` (VPS 에서)
3. MacBook 의 server 떠있나 (`lsof -i :8765`)
4. MacBook firewall (System Settings → Network → Firewall)

### "MacBook 응답 늦음"

1. `tailscale ping macbookair` 로 latency 체크 (DERP fallback 시 100ms+, direct 시 30ms)
2. Grok API rate limit?
3. `harness traces` 로 tool call 횟수 확인

---

## 11. 더 공부할 거리

- **WireGuard 프로토콜 자체**: https://www.wireguard.com/papers/wireguard.pdf (15페이지, 의외로 짧고 깔끔)
- **Tailscale 설계 글**: https://tailscale.com/blog/how-tailscale-works
- **NAT traversal 원리**: STUN (RFC 5389), ICE (RFC 8445) — 첫 5장만 읽어도 충분
- **HMAC**: Bruce Schneier 의 *Applied Cryptography* 9장 정도
- **OAuth 2.0**: RFC 6749. 데스크톱 앱은 *PKCE* (RFC 7636) 까지 같이.
- **FastAPI**: 공식 튜토리얼이 좋음. async + Pydantic + dependency injection 핵심.

---

## 12. 우리 코드의 어디에 매핑되나

| 개념 | 코드 |
|---|---|
| HMAC 검증 | `vps/relay.py::_verify_signature` |
| Webhook receiver | `vps/relay.py::webhook` |
| Forward 추상화 | `vps/relay.py::make_app(forward_fn=...)` |
| Test (no network) | `tests/test_relay.py` |
| OAuth callback | `vps/relay.py::oauth_callback` |
| 미래 — MacBook 진입점 | `harness/server.py` (PR #15) |
| Telegram 통합 | `harness/integrations/telegram.py` (PR #15) |
| Apple Calendar | `harness/integrations/apple_calendar.py` (PR #14) |

---

## 변경 이력

- 2026-04-29 v0.1 — Phase 3 F12 배포 직후 학습 노트로 작성
