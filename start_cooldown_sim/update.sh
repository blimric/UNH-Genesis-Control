#!/usr/bin/env bash
# Bring this copy of Genesis up to the newest elong: the same update as
# ../start_cooldown/update.sh (refuses while anything runs here, keeps the
# live system's two laptop-only settings edits in a patch).  Elena Long (2026-11-18).
#
#   update.sh
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${GENESIS_SIM_VENV:-}" ]]; then
    if [[ -x "$HOME/.venvs/genesis-sim/bin/python" ]]; then GENESIS_SIM_VENV="$HOME/.venvs/genesis-sim"
    else GENESIS_SIM_VENV="${GENESIS_VENV:-$HOME/.venvs/genesis-p1}"; fi
fi
GENESIS_ROOT="$ROOT" GENESIS_VENV="$GENESIS_SIM_VENV" bash "$ROOT/start_cooldown/update.sh"
