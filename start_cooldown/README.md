# start_cooldown: the whole live system from one command

These scripts run Genesis on a Windows laptop (with WSL) as the lab machine.
They start the cryo stack, the magnet supply, the NMR (PyNMR plus the Genesis
online fitter), the trend history, the master archiver, Phoebus with the
Panopticon, and the microwaves. The steps for a cool-down are in
[`Cooldown-Quick-Start-Guide.md`](../Cooldown-Quick-Start-Guide.md) at the
top of the repository. This file covers the details.

The folder was `scripts/live_laptop` until 2026-11-18.

| File | What it does |
|---|---|
| `start.sh` | Starts everything; parts already running are skipped |
| `stop.sh` | Stops everything and copies the data to Windows |
| `update.sh` | Brings the laptop's copy up to the newest `elong` |
| `setup.sh` | One-time setup of a new laptop; safe to re-run |
| `genesis_live_start.bat`, `genesis_live_stop.bat` | Windows double-click versions of `start.sh` and `stop.sh` |

These scripts are for the laptop's own copy, `~/genesis-live`. They edit two
settings files in it (see below) and stop processes by name. Don't run them
in a checkout that is shared or controlled in some other way, such as the
`main` worktree that Utsav's operator runbook covers.

## Once per computer

In a WSL (Ubuntu) terminal:

```bash
git -c core.autocrlf=false clone -b elong https://github.com/ellie-long/UNH-Genesis-Control.git ~/genesis-live \
  && ~/genesis-live/start_cooldown/setup.sh
```

The clone has to be Linux-native, with LF line endings. Utsav's `.sh` scripts
fail from a Windows checkout. On Ells's laptop, `~/genesis-live` is cloned
from the Windows checkout `C:\Users\longe\OneDrive\Documents\GitHub\UNH-Genesis-Control`
instead of GitHub, so commits made there reach it without a push.

`setup.sh` does the following:

- installs the Ubuntu packages, the Python environment
  (`~/.venvs/genesis-p1`) and Phoebus 5.0.5;
- creates SSH keys for the two Raspberry Pis and installs them (you type
  each Pi's password);
- writes `~/.genesis-live.env`, which holds the PyNMR paths and the online
  fitter's starting material. Check the paths in it.

On the Windows side, by hand:

- **NMR network.** The JLab NMR FPGA (192.168.0.72) and its SMA100A
  (192.168.0.50) are on 192.168.0.x, on the same Wi-Fi. Give the Wi-Fi
  adapter a second address with a **/24** mask, no gateway, and
  SkipAsSource. A /22 mask overlaps 192.168.1.x and breaks WSL's connections
  to the instruments. In an admin PowerShell:
  ```powershell
  New-NetIPAddress -InterfaceAlias "Wi-Fi" -IPAddress 192.168.0.232 -PrefixLength 24 -SkipAsSource $true
  ```
  The adapter must allow a static address alongside DHCP. To undo it:
  `Remove-NetIPAddress -IPAddress 192.168.0.232 -Confirm:$false`.
- **PyNMR.** This needs a conda env `pynmr` with jlab_pynmr on its `unh`
  branch. Its `unh/data_streamer.yaml` must have `enable: True` (the default
  since 2026-11-04) and `port: 8777`, which feed the Genesis fitter.
- **Other computers.** Stop Genesis and LabVIEW on any other computer that
  owns the instruments. Most serial-gateway ports allow only one connection.

## Every session

```bash
~/genesis-live/start_cooldown/update.sh   # only when Genesis is stopped
~/genesis-live/start_cooldown/start.sh    # or double-click genesis_live_start.bat
~/genesis-live/start_cooldown/stop.sh     # or genesis_live_stop.bat
```

`start.sh` checks the network and says if the copy is behind its origin. It
then asks you two things:

1. Whether to enable magnet control from Phoebus. Type `YES` to enable it;
   press Enter to keep the magnet read-only.
2. When to start the microwaves. Plug the Vaunix USB in first. Utsav's start
   then sets the UCA and asks **you** to type READY.

Options: `--no-pynmr`, `--no-phoebus`, `--no-microwaves`. Run `start.sh`
again at any time to start whatever is missing.

`stop.sh` stops everything, microwaves first, through Utsav's stop. It then
copies the data and logs to `C:\Users\<you>\Genesis_live_<date>`; this is a
copy, and WSL keeps the originals. PyNMR is left for you to close. If the
cryo stop refuses because the cold-board output is ON, use
`stop.sh --cryo-readonly-kill`. It stops only the read-only cryo IOCs;
Genesis never writes the cold board.

`update.sh` refuses while any part of Genesis is running. It first saves
`start.sh`'s two settings edits to `~/genesis-live-local-edits-<time>.patch`
and puts the two files back. `start.sh` re-applies them, and asks about
magnet writes again. Any other local change stops the update without
touching anything.

## The two settings `start.sh` changes in this copy

These changes are not committed:

- **LS455 `tesla_scale` is set to 1.0.** The LS455 reports in tesla
  (`UNIT? = T`). The scale stays at 1.0 until the driver reads the unit
  itself.
- **Magnet `write_enabled` is set to true**, but only if you type `YES`.

## The online fitter's material

The fitter starts with `FITTER_MATERIAL` from `~/.genesis-live.env`
(default `d-butanol`). You can change it on the fitter screen while it runs.

The target material and dopant are chosen on the Cryo Safety screen. They
stay purple (undefined) until chosen. The magnet's NMR target frequency
follows the material chosen there.

## Ports

| Service | CA port |
|---|---|
| Cryo IOCs | 5111-5129 (target state, material and dopant: 5120) |
| Trend history | 5130 |
| Magnet IOC | 5131 |
| Online fitter | 5100 (PVA 5101; sweeps from PyNMR or LabVIEW on 8777) |
| Microwave | 5094 (manager), 5066, 5069, 5085, 5087, 5095 |

## Screen sessions

Everything runs in detached `screen` sessions, so it outlives the terminal.
`screen -ls` lists them. The sessions are:

- `genesis-cryo-*`
- `genesis-hist`
- `genesis-magnet`
- `genesis-fitter`
- `genesis-phoebus`
- `ioc-manager`, plus the microwave IOCs

`screen -r <name>` attaches to one; detach again with Ctrl-a d.

## Known quirks

- **Restarting an IOC that Phoebus is watching** can leave Phoebus with dead
  connections and blank plots. Reopen Phoebus.
- **Magnet IOC stays disconnected.** Something else holds the supply's
  serial port, 5001 on 192.168.1.250. Usually that is another computer.
- **UCA supply.** On 2026-10-23 its socket port (5025) refused connections
  for hours while VXI-11 worked, then recovered (question 98).
- **Right-Roots flowmeter** (cryo Pi port 5010). No `/dev/ttyACM` device
  shows up on the Pi, so check its USB adapter.
