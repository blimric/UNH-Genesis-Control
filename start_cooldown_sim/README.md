# start_cooldown_sim: a simulated cool-down from one command

This folder does what [`start_cooldown/`](../start_cooldown/README.md) does,
but for the simulation. It runs the real Genesis software with its real lab
screens, and every instrument is simulated, so nothing touches any hardware.
Use it to practise a cool-down, to train people, and to try changes before
they meet the equipment. The steps are in
[`Cooldown-Quick-Start-Guide.md`](../Cooldown-Quick-Start-Guide.md) at the
top of the repository.

| File | What it does |
|---|---|
| `start.sh` | Starts the simulation in the background; its screens open in about a minute |
| `stop.sh` | Ends the simulation (same as **End session**), writes its report and closes its Phoebus |
| `update.sh` | Brings this copy up to the newest `elong` (the same update as `start_cooldown/update.sh`) |
| `setup.sh` | One-time setup (this is `tools/sim_setup.sh`). A laptop set up for the live system doesn't need it |
| `genesis_sim_start.bat`, `genesis_sim_stop.bat` | Windows double-click versions of `start.sh` and `stop.sh` |

These scripts work from any copy of the repository. The `.bat` files assume
the laptop's copy, `~/genesis-live`.

## Live and simulated, side by side

| | `start_cooldown/` (live) | `start_cooldown_sim/` (simulated) |
|---|---|---|
| Instruments | The lab's equipment | Simulated: fridge, magnet, microwaves, NMR, vacuum |
| Starts from | The lab as it is | Warm and off, or a past cool-down's record |
| Screens | Panopticon | Sim Control, Panopticon, Magnet, Cryo, Microwave, NMR fitter |
| Time | Real time | Time warp: pause, 1x, up to 600x |
| Data | `~/genesis-live-local_data/`, copied to Windows at stop | The run folder, `logs/cooldown_sim/<run>/`, with `report.md` |
| Runs in | `screen` sessions `genesis-*`, `ioc-manager` | `screen` session `genesis-sim` |

The two can't run at the same time on one computer. They use the same PV
names, so `start.sh` refuses while the live system is running.

## Usage

```bash
~/genesis-live/start_cooldown_sim/start.sh                 # the live cool-down, from warm
~/genesis-live/start_cooldown_sim/start.sh history --cooldown 2026-06 --start "2026-06-17 11:00"
~/genesis-live/start_cooldown_sim/stop.sh
```

- **History.** `history` replays a past cool-down's record, and needs
  `GENESIS_REPLAY_DATA`. You can set it in `~/.genesis-live.env`. The
  records are not in git; ask the UNH polarized-target group.
- **Other options.** Any option of `python -m cooldown_sim live` or
  `history` passes through, for example `start.sh live --speed 60`.
- **Log.** The session log is `logs/start_cooldown_sim.log`. Follow it with
  `tail -f`.
- **Python.** The scripts use `~/.venvs/genesis-sim` if `setup.sh` made one.
  Otherwise they use the live system's `~/.venvs/genesis-p1`. Set
  `GENESIS_SIM_VENV` to choose a different one.

## What to press

The full walk-through is in
[`docs/SIMULATION_QUICK_START.md`](../docs/SIMULATION_QUICK_START.md). In
short:

1. **Start Cool-down Sim** on Sim Control.
2. **Roots: On**.
3. Ramp the magnet on the Magnet tab.
4. Choose the material and dopant.
5. Turn the microwaves on at Magic + or Magic −.

## If something goes wrong

- **"REFUSED".** Another simulation, or Genesis, is already running here.
  End it with `stop.sh`.
- **Closing Phoebus doesn't end the simulation.** Use `stop.sh` or
  **End session**.
- **The screens didn't open, or you closed them.** Run
  `~/.venvs/genesis-p1/bin/python -m cooldown_sim phoebus --screens panopticon,magnet,cryo,mw,fitter`
  from the repository folder.
