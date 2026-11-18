# Simulation Quick Start Guide

Run a simulated cool-down of the UNH polarized target on your own computer.
You get the real Genesis control software with its real lab screens, but
every instrument is simulated, so nothing you press touches any hardware.

You need macOS, Linux, or Windows 11, and about 2 GB of disk space.

## 1. Set up (once)

**Windows:**
1. Open PowerShell and run `wsl --install -d Ubuntu`.
2. Restart the computer, then open **Ubuntu** from the Start menu.
3. Type the commands below into the Ubuntu window. Clone into your Ubuntu home, not into `C:\`.

**Mac or Linux:** open a Terminal.

```bash
git clone -b elong https://github.com/ellie-long/UNH-Genesis-Control.git
cd UNH-Genesis-Control
bash tools/sim_setup.sh
```

If the setup says something is missing (Python, Java, git or curl), it prints
the one command that installs it. Run that command, then run
`bash tools/sim_setup.sh` again. The first setup takes about 5–10 minutes.

## 2. Start it

```bash
bash tools/sim.sh
```

(This runs in the terminal; Ctrl+C ends it. To run it in the background
instead, use `start_cooldown_sim/start.sh` and end it with
`start_cooldown_sim/stop.sh`; see the
[Cool-down Quick Start Guide](../Cooldown-Quick-Start-Guide.md).)

After about a minute these windows open. They are Phoebus, the display
program Genesis uses in the lab.

* **Sim Control** (red banner): controls the *simulated world*.
* **Panopticon**: the one-page overview of the whole system.
* **Magnet**, **Cryo**, **Microwave** and **NMR fitter** tabs: the operator screens, as in the lab.

Everything starts warm, off and paused.

## 3. Run a cool-down

| Step | Where | What to press |
|---|---|---|
| 1 | Sim Control, **Live cool-down** | **Start Cool-down Sim**. The magnet, then the fridge, cool to ~1.9 K in about 4 minutes, with time speeded up automatically. The line next to the stage name always says what to do next. |
| 2 | Sim Control, **Live cool-down** | **Roots: On**. The fridge goes to ~1.1 K. |
| 3 | Magnet tab | **Heater ON (driven)**, wait for the 20 s bar. Then type **48.666** in Target current and press **RAMP to target** (5 T). Slide the speed up to ~60x so the ramp takes seconds. |
| 4 | Microwave tab | **Set target material**: choose the material (e.g. d-butanol) and the dopant (e.g. Irradiated). The **Magic +** and **Magic −** frequencies then appear in the supervisor section. |
| 5 | Microwave tab | Set **Output frequency** to the Magic + value, turn **RF request** ON, and lower the UCA voltage on the UCA card (0 V is full power). The polarization builds on the Panopticon's NMR card. |
| 6 | Sim Control | Try anything else: **Target Stick Insert**, **Magnet LHe Fill**, the vacuum **Leak** buttons, **QUENCH**, **Warm up**. |
| 7 | Sim Control | **End session** when you are done. |

## Time warp

The **Time warp** slider on Sim Control sets how fast simulated time runs. It
clicks at **pause** and **1x**, and slides smoothly up to 600x. Simulated
time matches a real cool-down. The automatic stages speed themselves up and
then give your speed back. The speed drops to 1x on alarms, interlock trips
and quenches; you can switch that off.

## A past cool-down instead

To rehearse on a past cool-down, you need the lab's cool-down records. They
are not in git: ask the UNH polarized-target group. Then:

```bash
export GENESIS_REPLAY_DATA=/path/to/the/cooldown/records
bash tools/sim.sh history --cooldown 2026-06 --start "2026-06-17 11:00"
```

The record plays back, and the autopilot repeats what the operators did. Set
any part to **Human** on Sim Control to take it over.

## If something goes wrong

* **"REFUSED"** at start: another simulation (or Genesis) is already running
  on this computer. End it first.
* **Closing Phoebus does not stop the simulation.** Use **End session**, or
  press Ctrl+C in the terminal.
* **The screens did not open**, or you closed them: run
  `~/.venvs/genesis-sim/bin/python -m cooldown_sim phoebus --screens panopticon,magnet,cryo,mw,fitter`.
* **A screen looks out of date**: right-click it, then choose **Re-load display**.

Tested on Windows 11 (WSL Ubuntu) and Linux; it should run the same on a Mac.
The full guide is in [COOLDOWN_SIM.md](COOLDOWN_SIM.md).
