@echo off
rem End the simulated cool-down in WSL (writes its report, closes its Phoebus).
wsl.exe -e bash -lc "~/genesis-live/start_cooldown_sim/stop.sh %*; echo; read -r -p 'Press Enter to close this window'"
