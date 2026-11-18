#!/usr/bin/env bash
# One-time setup for the simulated cool-down (macOS, Linux, or Windows through
# WSL): a Python environment (~/.venvs/genesis-sim) and Phoebus.  Safe to
# re-run.  This is tools/sim_setup.sh; a laptop already set up for the live
# system (../start_cooldown/setup.sh) can skip it.  Elena Long (2026-11-18).
#
#   setup.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT/tools/sim_setup.sh" "$@"
