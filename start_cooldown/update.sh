#!/usr/bin/env bash
# Bring this laptop's Genesis copy (~/genesis-live) up to the newest elong.
# Elena Long (2026-11-18).
#
#   update.sh
#
# The copy pulls from its origin: GitHub, or (on Ells's laptop) the Windows
# checkout C:\...\GitHub\UNH-Genesis-Control, so commits made there arrive
# without a push.
#
# start.sh edits two settings files in this copy every session (the LS455
# tesla_scale, and magnet writes if you say YES).  Git will not update files
# with local changes, so those two are saved to a patch in your home folder
# and put back first; start.sh re-applies them (and asks about magnet writes
# again).  Any other local change stops the update, untouched.
#
# Refuses while Genesis is running here: stop it first (stop.sh).
set -uo pipefail

ROOT="${GENESIS_ROOT:-$HOME/genesis-live}"
VENV="${GENESIS_VENV:-$HOME/.venvs/genesis-p1}"
BRANCH="${GENESIS_BRANCH:-elong}"
LOCAL_EDITS=(configs/target_physical/ls455/settings.yaml configs/magnet_physical/ips120/settings.yaml)

cd "$ROOT" || { echo "[FAIL] no Genesis repository at $ROOT (run setup.sh)"; exit 1; }

if screen -ls 2>/dev/null | grep -qE "[0-9]+\.(genesis-|ioc-manager|cooldown-sim)"; then
    echo "[FAIL] Genesis (live or simulated) is running on this laptop; stop it first:"
    echo "       $ROOT/start_cooldown/stop.sh   or   $ROOT/start_cooldown_sim/stop.sh"
    exit 1
fi

if ! git diff --quiet -- "${LOCAL_EDITS[@]}"; then
    patch="$HOME/genesis-live-local-edits-$(date +%Y%m%dT%H%M%S).patch"
    git diff -- "${LOCAL_EDITS[@]}" > "$patch"
    git checkout -- "${LOCAL_EDITS[@]}"
    echo "[OK]   laptop-only settings saved to $patch and put back (start.sh re-applies them)"
fi

other="$(git status --porcelain --untracked-files=no)"
if [[ -n "$other" ]]; then
    echo "[FAIL] other local changes in $ROOT; not updating:"
    echo "$other"
    exit 1
fi

old_req="$(git rev-parse -q HEAD:requirements.txt)"
if ! git fetch -q origin; then
    echo "[FAIL] cannot reach origin ($(git remote get-url origin))"
    exit 1
fi
if ! { git checkout -q "$BRANCH" && git merge -q --ff-only "origin/$BRANCH"; }; then
    echo "[FAIL] could not fast-forward $BRANCH to origin/$BRANCH; nothing else changed"
    exit 1
fi
echo "[OK]   now at $(git log --oneline -1)"

if [[ "$(git rev-parse -q HEAD:requirements.txt)" != "$old_req" ]]; then
    "$VENV/bin/python" -m pip install -q -r requirements.txt && echo "[OK]   Python requirements updated"
fi
