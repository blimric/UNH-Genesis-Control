#!/usr/bin/env bash
# End the simulated cool-down started by start.sh: the same as End session on
# Sim Control (it writes the run's report), then close that run's Phoebus
# windows, which outlive the session.  Elena Long (2026-11-18).
#
#   stop.sh
#
# Touches only the simulation: never the live system's IOCs or Phoebus.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${GENESIS_SIM_VENV:-}" ]]; then
    if [[ -x "$HOME/.venvs/genesis-sim/bin/python" ]]; then GENESIS_SIM_VENV="$HOME/.venvs/genesis-sim"
    else GENESIS_SIM_VENV="${GENESIS_VENV:-$HOME/.venvs/genesis-p1}"; fi
fi
PY="$GENESIS_SIM_VENV/bin/python"
cd "$ROOT" || exit 1
session_up() { screen -ls 2>/dev/null | grep -qE "[0-9]+\.cooldown-sim[[:space:]]"; }

run="$("$PY" -c "from cooldown_sim import run_dir; r = run_dir.latest(); print(r or '')" 2>/dev/null)"

if session_up; then
    echo "Ending the session ($run) ..."
    "$PY" -m cooldown_sim ctl stop 2>&1 | tail -n 3
    for _ in $(seq 1 120); do session_up || break; sleep 1; done
    if session_up; then
        echo "[WARN] the session did not end in 2 minutes; stopping its processes"
        "$PY" -m cooldown_sim stop "$run" 2>&1 | tail -n 2
        for s in $(screen -ls | grep -oE "[0-9]+\.cooldown-sim\b"); do screen -S "$s" -X quit; done
    fi
    echo "[STOPPED] simulation"
else
    echo "[--] no simulation running"
fi

# the run's Phoebus: started with that run's own settings file
if [[ -n "$run" ]] && pgrep -f -- "-settings $run/" >/dev/null; then
    pkill -f -- "-settings $run/" && echo "[STOPPED] its Phoebus windows"
fi
if [[ -n "$run" ]]; then
    echo "Run folder:   $run"
    [[ -f "$run/report.md" ]] && echo "Report:       $run/report.md"
    [[ -f "$run/after_action.html" ]] && echo "After-action: $run/after_action.html (open in a browser)"
fi
