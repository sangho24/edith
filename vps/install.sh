#!/usr/bin/env bash
# VPS bootstrap — Ubuntu 22.04 / Debian 12 호환.
# 사용:
#   curl -sSL https://raw.githubusercontent.com/sangho24/edith/main/vps/install.sh | bash
#
# 필수 env:
#   RELAY_SECRET  : 임의의 강한 secret (HMAC 서명 검증용)
#   HOME_HUB_URL  : Home Hub의 Tailscale 주소 (예: http://100.x.y.z:8000)

set -euo pipefail

if [[ -z "${RELAY_SECRET:-}" ]]; then
    echo "error: RELAY_SECRET env required (e.g., export RELAY_SECRET=$(openssl rand -hex 32))" >&2
    exit 1
fi

# Docker 설치 (없으면)
if ! command -v docker &>/dev/null; then
    echo "→ installing docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "  (재로그인 후 다시 실행하세요)"
    exit 0
fi

EDITH_REPO="${EDITH_REPO:-$HOME/edith}"
if [[ ! -d "$EDITH_REPO" ]]; then
    echo "→ cloning edith repo..."
    git clone https://github.com/sangho24/edith.git "$EDITH_REPO"
fi

cd "$EDITH_REPO/vps"

cat > .env <<EOF
RELAY_SECRET=${RELAY_SECRET}
HOME_HUB_URL=${HOME_HUB_URL:-}
EOF
chmod 600 .env

echo "→ building & starting relay..."
docker compose up -d --build

echo
echo "✓ Relay deployed. Health check:"
sleep 3
curl -s http://localhost:8765/health
echo
echo
echo "다음 단계:"
echo "  1. KakaoTalk Memo: home hub에서 push payload 보내기"
echo "  2. OAuth callback URL: http://YOUR_VPS_IP:8765/oauth/{provider}/callback"
echo "  3. logs: docker compose logs -f"
