#!/usr/bin/env bash
# PR #18 — Edith server.py LaunchAgent 설치/제거 helper.
#
# 사용법:
#   bash scripts/launchd/install.sh install      # ~/Library/LaunchAgents 에 복사 + load
#   bash scripts/launchd/install.sh uninstall    # 중지 + 제거
#   bash scripts/launchd/install.sh status       # 현재 상태
#   bash scripts/launchd/install.sh restart      # bounce
#   bash scripts/launchd/install.sh logs         # tail -f server.log

set -euo pipefail

PLIST_NAME="com.edith.server.plist"
SRC_PLIST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${PLIST_NAME}"
DST_DIR="${HOME}/Library/LaunchAgents"
DST_PLIST="${DST_DIR}/${PLIST_NAME}"
LABEL="com.edith.server"
EDITH_HOME="${EDITH_HOME:-${HOME}/edith}"

cmd="${1:-status}"

case "$cmd" in
    install)
        mkdir -p "$DST_DIR"
        cp "$SRC_PLIST" "$DST_PLIST"
        # 이미 load 되어 있으면 unload 후 다시
        launchctl unload "$DST_PLIST" 2>/dev/null || true
        launchctl load "$DST_PLIST"
        echo "✓ 설치 완료: $DST_PLIST"
        echo ""
        echo "확인:"
        echo "  launchctl list | grep edith"
        echo "  curl http://localhost:8765/health"
        echo "  tail -f ${EDITH_HOME}/harness/server.log"
        ;;

    uninstall)
        if [ -f "$DST_PLIST" ]; then
            launchctl unload "$DST_PLIST" 2>/dev/null || true
            rm "$DST_PLIST"
            echo "✓ 제거 완료"
        else
            echo "이미 제거됨: $DST_PLIST 없음"
        fi
        ;;

    restart)
        if [ -f "$DST_PLIST" ]; then
            launchctl unload "$DST_PLIST" 2>/dev/null || true
            launchctl load "$DST_PLIST"
            echo "✓ 재시작 완료"
        else
            echo "Error: 미설치 상태. 'install' 먼저."
            exit 1
        fi
        ;;

    status)
        echo "── plist 위치 ──"
        if [ -f "$DST_PLIST" ]; then
            echo "  ✓ $DST_PLIST"
        else
            echo "  ✗ 미설치 ($DST_PLIST 없음)"
        fi
        echo ""
        echo "── launchctl list ──"
        launchctl list | grep -i edith || echo "  (실행 중 아님)"
        echo ""
        echo "── /health 응답 ──"
        if curl -s -m 3 http://localhost:8765/health 2>/dev/null; then
            echo ""
        else
            echo "  (도달 불가)"
        fi
        ;;

    logs)
        log_path="${EDITH_HOME}/harness/server.log"
        err_path="${EDITH_HOME}/harness/server.err.log"
        echo "─── stdout: $log_path ───"
        echo "─── stderr: $err_path ───"
        echo ""
        tail -f "$log_path" "$err_path"
        ;;

    *)
        echo "사용법: $0 {install|uninstall|restart|status|logs}"
        exit 1
        ;;
esac
