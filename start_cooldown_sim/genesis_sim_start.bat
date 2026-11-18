@echo off
rem Start a SIMULATED cool-down in WSL (see Cooldown-Quick-Start-Guide.md).
rem Nothing touches any hardware.  Double-click, or run from a Windows terminal.
wsl.exe -e bash -lc "~/genesis-live/start_cooldown_sim/start.sh %*; echo; read -r -p 'Press Enter to close this window'"
