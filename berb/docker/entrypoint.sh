#!/bin/bash
# Berb experiment entrypoint — unified three-phase execution.
#
# Phase 0: pip install from requirements.txt (if present)
# Phase 1: Run setup.py for dataset downloads / preparation (if present)
# Phase 2: Run the main experiment script
#
# Environment variables:
#   RC_SETUP_ONLY_NETWORK=1  — disable network after Phase 1 (iptables/route)
#   RC_ENTRY_POINT           — override entry point (default: first CLI arg or main.py)
set -e

WORKSPACE="/workspace"
ENTRY_POINT="${1:-main.py}"

# ----------------------------------------------------------------
# Phase 0: Install additional pip packages
# ----------------------------------------------------------------
if [ -f "$WORKSPACE/requirements.txt" ]; then
    echo "[RC] Phase 0: Installing packages from requirements.txt..."
    pip install --no-cache-dir --break-system-packages \
        -r "$WORKSPACE/requirements.txt" 2>&1 | tail -20
    echo "[RC] Phase 0: Package installation complete."
fi

# ----------------------------------------------------------------
# Phase 1: Run setup script (dataset download / preparation)
# ----------------------------------------------------------------
if [ -f "$WORKSPACE/setup.py" ]; then
    echo "[RC] Phase 1: Running setup.py (dataset download/preparation)..."
    python3 -u "$WORKSPACE/setup.py"
    echo "[RC] Phase 1: Setup complete."
fi

# ----------------------------------------------------------------
# Network cutoff (if setup_only policy)
# ----------------------------------------------------------------
if [ "${RC_SETUP_ONLY_NETWORK:-0}" = "1" ]; then
    echo "[RC] Disabling network for experiment phase..."
    # Try iptables first (requires NET_ADMIN capability)
    if iptables -A OUTPUT -j DROP 2>/dev/null; then
        echo "[RC] Network disabled via iptables."
    elif ip route del default 2>/dev/null; then
        echo "[RC] Network disabled via route removal."
    else
        # SECURITY: fail closed. The container was asked for setup_only
        # isolation and neither mechanism worked (missing NET_ADMIN) — run
        # with network still up is a silent isolation downgrade, not a
        # convenience. Run with --cap-add=NET_ADMIN, or use network_policy:
        # none/full if you accept experiment-phase network access.
        echo "[RC] FATAL: Could not disable network (no NET_ADMIN cap or ip route)." >&2
        exit 1
    fi
fi

# ----------------------------------------------------------------
# Phase 2: Run experiment
# ----------------------------------------------------------------
echo "[RC] Phase 2: Running experiment ($ENTRY_POINT)..."
exec python3 -u "$WORKSPACE/$ENTRY_POINT"
