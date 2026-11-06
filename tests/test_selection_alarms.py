"""Target material, dopant and state are purple (undefined) only until chosen.

Elena Long (2026-11-06, Ells: "once they're selected they should no longer be
purple"): pythonSoftIOC keeps an Out record's start-up INVALID/UDF alarm and
re-applies it on every later write, so the Panopticon showed the material
and dopant purple even after they were picked on the Cryo Safety screen, and
after every restart.  The IOCs now clear that alarm when a value is chosen
on a screen, restored from the saved state, or followed from the cryo
selection.
"""

import asyncio
import os
import socket
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

from cooldown_sim.testing import softioc_stub

ROOT = Path(__file__).resolve().parents[1]
UNDEFINED = (3, 17)                     # INVALID, UDF
CLEAR = (0, 0)


class FakePV:
    def __init__(self, value=0):
        self.value, self.alarm = value, UNDEFINED

    def get(self):
        return self.value

    def set(self, value, **_kw):
        self.value = value

    def set_alarm(self, severity, status):
        self.alarm = (severity, status)


def _target_status():
    with softioc_stub.installed():
        from logic_devices.target_status import Device
    return Device


def _fake_status(tmp_path):
    Device = _target_status()
    dev = types.SimpleNamespace(
        last_file=str(tmp_path / "last.yaml"),
        status_names=["Warm", "Cooldown", "Cold"],
        material_names=["Empty", "ND3", "d-butanol", "d-propanediol", "NH3"],
        dopant_names=["None", "Irradiated", "TEMPO", "Trityl"],
        pvs={k: FakePV() for k in ("status", "material", "dopant", "state_applied")},
        state_table_validated=False, apply_enabled=False)
    for name in ("_chosen", "_dopant_update", "_remember", "_selected", "connect", "stat_update"):
        setattr(dev, name, types.MethodType(getattr(Device, name), dev))
    return dev


def test_restored_selections_are_not_purple_but_missing_ones_stay(tmp_path):
    (tmp_path / "last.yaml").write_text("material_name: NH3\ndopant_name: TEMPO\n")
    dev = _fake_status(tmp_path)
    dev.connect()
    assert dev.pvs["material"].value == 4 and dev.pvs["material"].alarm == CLEAR
    assert dev.pvs["dopant"].value == 2 and dev.pvs["dopant"].alarm == CLEAR
    assert dev.pvs["status"].alarm == UNDEFINED          # nothing saved: not chosen yet


def test_a_fresh_start_leaves_everything_purple(tmp_path):
    dev = _fake_status(tmp_path)
    dev.connect()
    assert all(dev.pvs[k].alarm == UNDEFINED for k in ("status", "material", "dopant"))


def test_choosing_on_the_screen_clears_only_that_selection(tmp_path):
    dev = _fake_status(tmp_path)
    dev.pvs["material"].value = 1
    asyncio.run(dev.stat_update(1, "UNH:GEN:CRYO:STATE:material"))
    assert dev.pvs["material"].alarm == CLEAR
    assert dev.pvs["status"].alarm == UNDEFINED and dev.pvs["dopant"].alarm == UNDEFINED
    dev.pvs["dopant"].value = 1
    dev._dopant_update(1)
    assert dev.pvs["dopant"].alarm == CLEAR
    assert "Irradiated" in (tmp_path / "last.yaml").read_text()


class _Reading(str):
    severity = 0


def _supervisor(monkeypatch, cryo_value, cryo_severity):
    with softioc_stub.installed():
        from logic_devices.microwave_supervisor import device as mod
    reading = _Reading(cryo_value)
    reading.severity = cryo_severity

    async def caget(*_a, **_kw):
        return reading
    monkeypatch.setattr(mod.aioca, "caget", caget)
    dev = types.SimpleNamespace(
        follow_dopant_pv="UNH:GEN:CRYO:STATE:dopant", _next_dopant_check=0.0,
        _followed_dopant=None, pvs={"Dopant": FakePV()},
        dopants=[{"name": n} for n in ("None", "Irradiated", "TEMPO", "Trityl")])
    dev._dopant_chosen = types.MethodType(mod.Device._dopant_chosen, dev)
    asyncio.run(mod.Device._follow_dopant(dev))
    return dev


def test_supervisor_follows_a_chosen_cryo_dopant_and_stops_being_purple(monkeypatch):
    dev = _supervisor(monkeypatch, "TEMPO", 0)
    assert dev.pvs["Dopant"].value == 2 and dev.pvs["Dopant"].alarm == CLEAR


def test_supervisor_follows_a_chosen_first_entry_too(monkeypatch):
    dev = _supervisor(monkeypatch, "None", 0)            # index 0, same as the start value
    assert dev.pvs["Dopant"].value == 0 and dev.pvs["Dopant"].alarm == CLEAR


def test_supervisor_ignores_an_unchosen_cryo_dopant(monkeypatch):
    dev = _supervisor(monkeypatch, "None", 3)            # cryo record still undefined
    assert dev.pvs["Dopant"].alarm == UNDEFINED and dev._followed_dopant is None


# ------------------------------------------------- through real EPICS
IOC_SCRIPT = textwrap.dedent("""
    import asyncio, os, sys
    from softioc import asyncio_dispatcher, builder, softioc
    from aioca import FORMAT_TIME, caget, caput
    from logic_devices.target_status import Device

    last = sys.argv[1]
    disp = asyncio_dispatcher.AsyncioDispatcher()
    builder.SetDeviceName("TST:STATE")
    dev = Device("TST:STATE", {"states_file": "logic_devices/states_unh.yaml", "last_file": last,
                               "state_table_validated": False, "apply_enabled": False})
    builder.LoadDatabase()
    softioc.iocInit(disp)
    dev.connect()

    async def main():
        async def sev(key):
            return (await caget("TST:STATE:" + key, format=FORMAT_TIME, timeout=5)).severity
        print("start", await sev("material"), await sev("dopant"), flush=True)
        if sys.argv[2] == "choose":
            await caput("TST:STATE:material", "ND3", wait=True, timeout=5)
            await caput("TST:STATE:dopant", "TEMPO", wait=True, timeout=5)
            await asyncio.sleep(0.5)
            print("chosen", await sev("material"), await sev("dopant"), flush=True)
    asyncio.run_coroutine_threadsafe(main(), disp.loop).result(30)
    os._exit(0)
""")


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_ioc(tmp_path, last, action):
    port = str(_free_port())
    env = dict(os.environ, EPICS_CA_SERVER_PORT=port, EPICS_CA_ADDR_LIST=f"127.0.0.1:{port}",
               EPICS_CA_AUTO_ADDR_LIST="NO", PYTHONPATH=str(ROOT))
    script = tmp_path / "ioc.py"
    script.write_text(IOC_SCRIPT, encoding="utf-8")
    out = subprocess.run([sys.executable, "-u", str(script), str(last), action], cwd=ROOT, env=env,
                         input="", capture_output=True, text=True, timeout=60)
    lines = {ln.split()[0]: [int(x) for x in ln.split()[1:]]
             for ln in out.stdout.splitlines() if ln.startswith(("start ", "chosen "))}
    assert "start" in lines, out.stdout + out.stderr
    return lines


def test_through_epics_purple_until_chosen_and_after_a_restart(tmp_path):
    pytest.importorskip("softioc")
    pytest.importorskip("aioca")
    last = tmp_path / "last.yaml"
    first = _run_ioc(tmp_path, last, "choose")
    assert first["start"] == [3, 3]                      # never chosen: purple
    assert first["chosen"] == [0, 0]                     # picked on the screen: not purple
    again = _run_ioc(tmp_path, last, "look")
    assert again["start"] == [0, 0]                      # restored at start: not purple
