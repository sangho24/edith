#!/usr/bin/env bash
# macOS launchd installer for `harness daily` (Phase 2 W3).
# 매일 22시 자동 실행. 로그는 $EDITH_HOME/harness/daily.log.
#
# 사용:
#   bash scripts/install_daily.sh          # 설치
#   bash scripts/install_daily.sh test     # 즉시 한 번 실행 (테스트)
#   bash scripts/install_daily.sh uninstall # 제거

set -euo pipefail

EDITH_HOME="${EDITH_HOME:-$HOME/edith}"
UV_BIN="$(command -v uv || echo /opt/homebrew/bin/uv)"
PLIST_NAME="com.edith.daily"
PLIST_TEMPLATE="$EDITH_HOME/scripts/${PLIST_NAME}.plist.template"
PLIST_TARGET="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

if [[ ! -f "$PLIST_TEMPLATE" ]]; then
    echo "error: template not found at $PLIST_TEMPLATE" >&2
    exit 1
fi
if [[ ! -x "$UV_BIN" ]]; then
    echo "error: uv not found in PATH (brew install uv)" >&2
    exit 1
fi

cmd="${1:-install}"

case "$cmd" in
install)
    mkdir -p "$HOME/Library/LaunchAgents"
    sed -e "s|\${EDITH_HOME}|$EDITH_HOME|g" \
        -e "s|\${UV_BIN}|$UV_BIN|g" \
        "$PLIST_TEMPLATE" > "$PLIST_TARGET"

    launchctl unload "$PLIST_TARGET" 2>/dev/null || true
    launchctl load "$PLIST_TARGET"
    echo "✓ installed at $PLIST_TARGET"
    echo "  매일 22:00 자동 실행. 로그: $EDITH_HOME/harness/daily.log"
    echo "  즉시 테스트: bash scripts/install_daily.sh test"
    ;;
test)
    echo "→ launchctl start ${PLIST_NAME}"
    launchctl start "${PLIST_NAME}"
    sleep 2
    echo "─── tail $EDITH_HOME/harness/daily.log ───"
    tail -30 "$EDITH_HOME/harness/daily.log" 2>/dev/null || echo "(log empty)"
    ;;
uninstall)
    launchctl unload "$PLIST_TARGET" 2>/dev/null || true
    rm -f "$PLIST_TARGET"
    echo "✓ uninstalled"
    ;;
*)
    echo "usage: $0 [install|test|uninstall]"
    exit 1
    ;;
esac
