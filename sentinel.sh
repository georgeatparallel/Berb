#!/bin/bash
# Sentinel Watchdog Script for Berb
# Monitors pipeline heartbeat and detects stalled runs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEARTBEAT_FILE="${SCRIPT_DIR}/heartbeat.json"
TIMEOUT_SEC=${1:-300}

usage() {
    echo "Usage: $0 [timeout_seconds]"
    echo "  timeout_seconds: Seconds to wait before considering run stalled (default: 300)"
    exit 1
}

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

check_heartbeat() {
    if [ ! -f "$HEARTBEAT_FILE" ]; then
        echo "ERROR: No heartbeat file found at $HEARTBEAT_FILE"
        return 1
    fi

    local last_update
    local current_time
    local elapsed

    last_update=$(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || stat -f %m "$HEARTBEAT_FILE" 2>/dev/null)
    current_time=$(date +%s)
    elapsed=$((current_time - last_update))

    if [ $elapsed -gt $TIMEOUT_SEC ]; then
        echo "WARNING: Heartbeat stale (${elapsed}s > ${TIMEOUT_SEC}s timeout)"
        return 1
    fi

    echo "OK: Heartbeat fresh (${elapsed}s <= ${TIMEOUT_SEC}s timeout)"
    return 0
}

main() {
    echo "Sentinel watchdog monitoring (timeout: ${TIMEOUT_SEC}s)"
    check_heartbeat
}

main "$@"
