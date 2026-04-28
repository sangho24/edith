# Phase 3 F11 — Home Hub Deploy

자택 always-on 머신 (Mac mini / NUC / 안 쓰는 데스크탑)에 Edith 컨테이너 배포.

## 사전 요구

- Docker Desktop (macOS) 또는 docker + docker-compose-plugin (Linux)
- ANTHROPIC_API_KEY (사용자 발급)

## 설치

```bash
cd ~/edith

# .env 작성 (한 번)
cat > docker/.env <<EOF
ANTHROPIC_API_KEY=sk-ant-...
EDITH_HOST_PATH=$(pwd)
EDITH_DS_DIGEST_LATEST=$HOME/projects/ds-digest/docs/latest.json  # optional
EDITH_DS_DIGEST_WORKFLOW=$HOME/projects/ds-digest/.github/workflows/daily.yml  # optional
EOF

# 빌드 + 실행
make hub-up
```

## 운영

```bash
make hub-logs       # 실시간 로그
make hub-shell      # 컨테이너 안 셸 (ad-hoc)
make hub-down       # 중지
make hub-restart    # 재시작
```

## 자동화 schedule (컨테이너 안 cron)

| 시간 (KST) | command | 역할 |
|---|---|---|
| 매일 08:00 | `harness brief` | morning briefing |
| 매일 22:00 | `harness daily` | compile + eval + dashboard |
| 일요 21:00 | `harness weekly` | weekly synthesis |

## 데이터 위치

- `EDITH_HOST_PATH` (host) ↔ `/data/edith` (container)
- raw/, wiki/, harness/traces, harness/approvals.json 모두 host에 그대로 남음
- 컨테이너 재기동해도 데이터 유실 없음

## 백업

cron 이외 별도 백업 권장:

```bash
# 매일 03:00 외장 SSD로 rsync
0 3 * * * rsync -av --delete ~/edith /Volumes/Backup/edith-snap-$(date +\%F)
```

## 알려진 한계

- macOS Docker Desktop은 ARM Mac에서 좀 느림. 진짜 Linux 홈서버 추천.
- KakaoTalk push는 외부 callable 필요 → VPS Relay (F12) 별도 필요.
- Google OAuth callback도 외부 callable 필요 → 마찬가지.

## VPS Relay 와의 관계

| 컴포넌트 | 어디에 | 역할 |
|---|---|---|
| **Home Hub** (F11) | 자택 | 데이터 정본, schedule, LLM 호출 |
| **VPS Relay** (F12) | 클라우드 | 외부 webhook 수신, KakaoTalk push, OAuth callback |
| 통신 | Tailscale 또는 SSH tunnel | hub ←→ relay |

`vps/README.md` 참조.
