#!/usr/bin/env bash
# Start a Genesis cool-down simulation with its screens open.
#
#   bash tools/sim.sh                 the live cool-down from warm (every button works)
#   bash tools/sim.sh history --cooldown 2026-06 --start "2026-06-17 11:00"
#                                     a past cool-down's record (needs GENESIS_REPLAY_DATA)
#
# One-time setup first: bash tools/sim_setup.sh.  End with "End session" on
# Sim Control (or Ctrl+C here).
set -euo pipefail
cd "$(dirname "$0")/.."
VENV="${GENESIS_SIM_VENV:-$HOME/.venvs/genesis-sim}"
if [ ! -x "$VENV/bin/python" ]; then
    echo "Run the one-time setup first:  bash tools/sim_setup.sh"
    exit 1
fi
# the Java the setup downloaded, if the computer had none
[ -x "$HOME/phoebus/jre/bin/java" ] && ! command -v java >/dev/null && export PATH="$HOME/phoebus/jre/bin:$PATH"
mode="${1:-live}"
[ $# -gt 0 ] && shift
exec "$VENV/bin/python" -u -m cooldown_sim "$mode" "$@"
