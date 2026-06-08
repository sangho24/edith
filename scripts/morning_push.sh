#!/usr/bin/env bash
# Run the daily Edith morning brief push from launchd.

set -u

EDITH_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${EDITH_HOME}/logs"
LOG_FILE="${LOG_DIR}/morning_push.log"
UV_BIN="${UV_BIN:-$(command -v uv 2>/dev/null || true)}"

if [[ -z "${UV_BIN}" ]]; then
    UV_BIN="/opt/homebrew/bin/uv"
fi

mkdir -p "${LOG_DIR}"

{
    echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] morning push start"
    cd "${EDITH_HOME}" || exit 1
    "${UV_BIN}" run harness brief --push email,osnotify
    status=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] morning push exit=${status}"
    exit "${status}"
} >> "${LOG_FILE}" 2>&1
