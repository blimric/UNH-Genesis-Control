# Cool-down Quick Start Guide

This guide starts the whole Genesis system for a cool-down with one command:

- the cryo stack and its Pi bridges
- the magnet supply
- the NMR: PyNMR plus the Genesis online fitter
- the trend history and the master archiver
- Phoebus with the Panopticon
- the microwaves

It also covers how to practise first on the simulation.

This guide assumes the following:

- the laptop has been set up once (see [Setting up a new laptop](#setting-up-a-new-laptop));
- WSL (Ubuntu) is running;
- Genesis lives in `~/genesis-live`.

Run the commands in a **WSL terminal**. From a Windows terminal, wrap each
one as `wsl -e bash -lc "<command>"`, or double-click the matching `.bat`
file.

| Folder | What it starts |
|---|---|
| [`start_cooldown/`](start_cooldown/README.md) | The live system, connected to the lab's equipment |
| [`start_cooldown_sim/`](start_cooldown_sim/README.md) | The same software and screens, with every instrument simulated |

## 1. Before you start

- **Only this laptop may own the instruments.** Stop Genesis and LabVIEW on
  any other computer first. Most serial-gateway ports allow one connection.
- **Network.** The laptop is on the lab Wi-Fi as 192.168.1.x. For the NMR it
  also needs its second address on 192.168.0.x, with a /24 mask (see
  [`start_cooldown/README.md`](start_cooldown/README.md)).
- **Vaunix.** Plug the Vaunix USB in before the microwaves start.

## 2. Bring the code up to date

Do this only while Genesis is stopped.

```bash
~/genesis-live/start_cooldown/update.sh
```

`start.sh` reminds you when the copy is behind.

## 3. Start everything: one command

```bash
~/genesis-live/start_cooldown/start.sh
```

Or double-click `start_cooldown\genesis_live_start.bat`, or run it from
Windows:

```powershell
wsl -e bash -lc "~/genesis-live/start_cooldown/start.sh"
```

The script checks that each instrument answers on the network. It then
starts everything in order and skips anything already running. It stops to
ask you two things:

1. **Magnet control from Phoebus?** Type `YES` to allow ramps from the
   Magnet screen. Press Enter to keep the magnet read-only.
2. **Start the microwaves now?** Press Enter, or type `skip`. Utsav's
   microwave start sets the UCA, then asks **you** to type `READY`. The
   script never answers a safety prompt for you.

It ends with a list of what is running. If something failed, fix it and run
`start.sh` again; it only starts what is missing.

To leave a part out, use `--no-pynmr`, `--no-phoebus` or `--no-microwaves`.

## 4. Once it's up

- **Panopticon.** It opens about 20 s after the last step. A red box is an
  alarm; a purple box is a value not yet defined.
- **Target material and dopant.** Choose them on the **Cryo Safety**
  screen. They stay purple until you do. The magnet's NMR target frequency
  follows the material.
- **Fitter material.** The online fitter starts as `FITTER_MATERIAL`, set
  in `~/.genesis-live.env`. You can change it on the fitter screen.
- **PyNMR.** Its "JLab Polarization Display" window opens on Windows. Run
  the NMR from it as usual. It feeds the Genesis fitter on port 8777.

## 5. Stop everything

```bash
~/genesis-live/start_cooldown/stop.sh
```

Or double-click `start_cooldown\genesis_live_stop.bat`.

- **Order.** It stops the microwaves first, through Utsav's stop, which
  turns the RF off and puts the UCA at its safe baseline. Then it stops the
  rest.
- **Data.** It copies the data to `C:\Users\<you>\Genesis_live_<date>`.
  This is a copy; WSL keeps the originals.
- **PyNMR.** Close its window yourself.
- **Cryo stop refused.** If the cryo stop refuses because the cold-board
  output is ON, run `stop.sh --cryo-readonly-kill`.

## Practise first: the simulation

The same software and screens, with nothing connected to hardware:

```bash
~/genesis-live/start_cooldown_sim/start.sh        # a cool-down from warm
~/genesis-live/start_cooldown_sim/stop.sh         # end it (writes its report)
```

Or double-click `start_cooldown_sim\genesis_sim_start.bat` and
`start_cooldown_sim\genesis_sim_stop.bat`.

The Sim Control, Panopticon and operator screens open in about a minute.
On Sim Control:

1. Press **Start Cool-down Sim**.
2. Press **Roots: On**.
3. Ramp the magnet.
4. Choose the material.
5. Turn the microwaves on at Magic + or Magic −.

To replay a past cool-down instead, run
`start_cooldown_sim/start.sh history --cooldown 2026-06 --start "2026-06-17 11:00"`.
This needs the cool-down records in `GENESIS_REPLAY_DATA`.

The simulation and the live system can't run at the same time on one
laptop; each refuses while the other runs. The full walk-through is in
[`docs/SIMULATION_QUICK_START.md`](docs/SIMULATION_QUICK_START.md).

## If something goes wrong

| Symptom | What to do |
|---|---|
| `[WARN] ... not answering` at the start | That instrument is off, unplugged, or on another network. Check it, then run `start.sh` again |
| Magnet IOC stays disconnected | Something else holds the supply's serial port; stop Genesis or LabVIEW elsewhere |
| Blank plots after an IOC restart | Close Phoebus and run `start.sh` again (it reopens Phoebus) |
| The microwave stop keeps its IOCs | It couldn't confirm a safe state. Check the UCA and RF by hand before stopping them |
| `update.sh` says "other local changes" | Something besides the two laptop-only settings was edited in `~/genesis-live`. Look at `git -C ~/genesis-live status` |

- **Everything, step by step.** [`STARTUP_INSTRUCTIONS.md`](STARTUP_INSTRUCTIONS.md)
  covers the same start by hand.
- **Details.** Ports, `screen` sessions and quirks are in
  [`start_cooldown/README.md`](start_cooldown/README.md).

## Setting up a new laptop

Once, in a WSL terminal:

```bash
git -c core.autocrlf=false clone -b elong https://github.com/ellie-long/UNH-Genesis-Control.git ~/genesis-live \
  && ~/genesis-live/start_cooldown/setup.sh
```

The Windows-side steps are in
[`start_cooldown/README.md`](start_cooldown/README.md): the NMR network
address and PyNMR's conda environment.
