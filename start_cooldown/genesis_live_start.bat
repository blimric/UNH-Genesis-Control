@echo off
rem Start the Genesis live system in WSL (see Cooldown-Quick-Start-Guide.md).
rem Double-click, or run from a Windows terminal.  The window stays open for
rem the prompts (magnet writes, microwave READY) and the final summary.
wsl.exe -e bash -lc "~/genesis-live/start_cooldown/start.sh %*; echo; read -r -p 'Press Enter to close this window'"
