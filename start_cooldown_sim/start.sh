#!/usr/bin/env bash
# Start a SIMULATED cool-down: the real Genesis software and lab screens, with
# every instrument simulated, so nothing touches any hardware.  The simulated
# twin of ../start_cooldown/start.sh.  Elena Long (2026-11-18).
#
#   start.sh                       the live cool-down from warm (every button works)
#   start.sh history --cooldown 2026-06 --start "2026-06-17 11:00"
#                                  a past cool-down's record (needs GENESIS_REPLAY_DATA)
#   start.sh live --speed 60       any option of `python -m cooldown_sim live` or `history`
#
# The simulation runs in the background, in screen session cooldown-sim (not
# genesis-*: the simulation's guard reads those as the live system).  Its
# Phoebus windows open in about a minute.  End it with stop.sh, or with
# End session on Sim Control.  Refuses while the live system runs here.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$HOME/.genesis-live.env"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"          # GENESIS_REPLAY_DATA, if set there
if [[ -z "${GENESIS_SIM_VENV:-}" ]]; then
    # tools/sim_setup.sh's environment, or the live system's (it has everything the sim needs)
    if [[ -x "$HOME/.venvs/genesis-sim/bin/python" ]]; then GENESIS_SIM_VENV="$HOME/.venvs/genesis-sim"
    else GENESIS_SIM_VENV="${GENESIS_VENV:-$HOME/.venvs/genesis-p1}"; fi
fi
export GENESIS_SIM_VENV
export DISPLAY="${DISPLAY:-:0}"                     # WSLg

cd "$ROOT" || exit 1
[[ -x "$GENESIS_SIM_VENV/bin/python" ]] || { echo "[FAIL] no Python environment: run $ROOT/start_cooldown_sim/setup.sh"; exit 1; }
step() { printf '\n===== %s =====\n' "$*"; }
session_up() { screen -ls 2>/dev/null | grep -qE "[0-9]+\.cooldown-sim[[:space:]]"; }

step "1. Nothing live running here"
if screen -ls 2>/dev/null | grep -qE "[0-9]+\.(genesis-(cryo|hist|magnet|fitter|phoebus)|ioc-manager)"; then
    echo "[FAIL] the live system is running on this computer; the simulation would share its PV names."
    echo "       Stop it first ($ROOT/start_cooldown/stop.sh), or run the simulation on another computer."
    exit 2
fi
if session_up; then
    echo "[UP] a simulation is already running: end it with $ROOT/start_cooldown_sim/stop.sh"
    exit 0
fi
echo "[OK]"

step "2. The simulation (${*:-live})"
mkdir -p logs
log="$ROOT/logs/start_cooldown_sim.log"
printf '\n---- %s start.sh %s\n' "$(date '+%F %T')" "$*" >> "$log"
mark="$(wc -l < "$log")"
screen -dmS cooldown-sim bash -c "exec bash tools/sim.sh $(printf '%q ' "$@") >> '$log' 2>&1"

# wait for the session to say it is ready (Phoebus opening), or to stop
for _ in $(seq 1 180); do
    sleep 1
    new="$(tail -n +"$((mark + 1))" "$log")"
    if grep -q "Phoebus starting" <<<"$new"; then break; fi
    if ! session_up; then
        echo "[FAIL] the simulation stopped while starting; the end of its log ($log):"
        tail -n 15 <<<"$new"
        exit 1
    fi
done
new="$(tail -n +"$((mark + 1))" "$log")"
grep -E "^\[(ok|warn|fail)\]|REFUSED|run directory|Phoebus" <<<"$new" | tail -n 12
if grep -q "Phoebus starting" <<<"$new"; then
    echo
    echo "[OK] running.  The Sim Control, Panopticon and operator screens open in about a minute."
else
    echo "[WARN] still starting after 3 minutes; follow it with: tail -f $log"
fi
echo "End the simulation (it writes a report) with: $ROOT/start_cooldown_sim/stop.sh"
