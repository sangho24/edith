# Phase 3 F12 — VPS Relay

작은 VPS에 띄우는 stateless relay. Home Hub의 외부 callable layer.

## 왜 별도 VPS인가

- **KakaoTalk Memo API**: external callable IP 필요 (집 IP는 변동)
- **OAuth callback URL**: Google/GitHub OAuth는 안정된 redirect_uri 요구
- **외부 webhook 수신**: GitHub Actions, Slack 등이 push할 곳 필요
- **Home Hub 보호**: 자택 IP 노출 X. relay만 인터넷에 노출.

## 추천 호스팅

| | 가격 | 메모 |
|---|---|---|
| **Oracle Free Tier** | 무료 | ARM 4 vCPU 24GB RAM 까지. **추천** |
| AWS Lightsail | $5/월 | x86, 1GB RAM. 안정적 |
| DigitalOcean | $4/월 | 비슷함 |

## 설치 (5분)

```bash
# VPS SSH 후
export RELAY_SECRET=$(openssl rand -hex 32)
export HOME_HUB_URL=http://100.x.y.z:8000  # Tailscale 주소
curl -sSL https://raw.githubusercontent.com/sangho24/edith/main/vps/install.sh | bash
```

## 엔드포인트

| path | 용도 | 인증 |
|---|---|---|
| `GET /health` | 헬스 체크 | 없음 |
| `POST /webhook/{source}` | 외부 webhook 수신 (e.g., github, calendar) | HMAC `X-Relay-Signature` |
| `POST /push/kakao` | home hub → 카톡 메모 push | HMAC |
| `GET /oauth/{provider}/callback` | OAuth redirect 받기 | (provider state 검증) |

## HMAC 검증

home hub가 relay로 보낼 때:

```python
import hmac, hashlib, json, requests
body = json.dumps(payload).encode()
sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
requests.post(f"{RELAY_URL}/push/kakao", data=body, headers={"X-Relay-Signature": sig})
```

## Tailscale 셋업 (선택)

home hub와 relay를 같은 tailnet에 두면 `HOME_HUB_URL`을 100.x 주소로 쓸 수 있고 인터넷 노출 X.

```bash
# VPS 와 home hub 모두에서
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4  # 100.x.y.z 주소 확인
```

## 모니터링

```bash
docker compose logs -f --tail 100
docker compose ps
curl http://localhost:8765/health
```

## 보안 체크리스트

- [ ] `.env`의 `RELAY_SECRET` 강함 (32+ bytes)
- [ ] VPS 방화벽: 8765 + SSH(22) 만 열기 (`ufw allow 22 && ufw allow 8765 && ufw enable`)
- [ ] Tailscale 우선 — VPS의 8765 포트를 인터넷에 노출 안 하면 더 안전
- [ ] HMAC 검증 위반 시 401 반환 (로그에 IP 기록 권장 — 추후 추가)
- [ ] HTTPS: Caddy 또는 nginx + Let's Encrypt 권장 (별도 추가)
