"""SimEngine: the clock, the value provider and the emulator host for one run.

The engine is deliberately free of EPICS so it can be hosted either by the
``run`` command directly (unattended regression) or by the Sim Control IOC
(interactive rehearsal).  It records every operator-visible sim event --
start, pause, seek, speed, faults, notes -- in ``events.csv`` with both wall
and sim time, and saves the clock checkpoints so validators can map archive
timestamps back to sim time.
"""

from __future__ import annotations

import collections
import csv
import math
import json
import threading
import time
from dataclasses import asdict
from pathlib import Path

from .channel_map import ChannelMap
from .clock import SimClock
from .data.records import format_epoch
from .data.timeline import Timeline
from .emulators.host import EmulatorHost
from .profile import GeneratedStack
from .providers import ReplayProvider, ServedLog
from .run_dir import RunDir


class EventLog:
    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self._fh = open(path, "a", newline="", encoding="utf-8")
        self._w = csv.writer(self._fh)
        if path.stat().st_size == 0:
            self._w.writerow(["wall", "sim", "sim_local", "kind", "detail"])

    def write(self, sim: float, kind: str, detail: str = "") -> None:
        with self._lock:
            self._w.writerow([f"{time.time():.3f}", f"{sim:.3f}", format_epoch(sim), kind, detail])
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            self._fh.close()


class SimEngine:
    def __init__(self, run: RunDir, stack: GeneratedStack, timeline: Timeline, cmap: ChannelMap,
                 clock: SimClock, *, noise_rel: float = 2e-5, seed: int = 0,
                 supply_initial: dict | None = None, provider=None):
        self.run = run
        self.stack = stack
        self.timeline = timeline
        self.cmap = cmap
        self.clock = clock
        self.served = ServedLog(run.path / "served.csv")
        self.provider = provider or ReplayProvider(timeline, cmap, clock, noise_rel=noise_rel,
                                                   seed=seed, served=self.served)
        if provider is not None:
            provider.served = self.served
        self.host = EmulatorHost(stack, self.provider, cmap, timeline, supply_initial)
        if hasattr(self.provider, "host"):
            self.provider.host = self.host
        self.events = EventLog(run.path / "events.csv")
        #: session facts shown on Sim Control (mode, source, window, scenario)
        self.info: dict = {}
        self.last_event = ""
        self.autopilot = {"mw": False, "ssrf": False, "fit": False}
        #: operator microwave requests for the MW leg (thread-safe deque): ("frequency", GHz)
        self.mw_requests: collections.deque = collections.deque()
        self.stop_requested = threading.Event()
        #: the interactive warm start's live cryostat (synth/live.py), or None
        self.background = getattr(self.provider, "background", None)
        #: time warp (Elena Long, 2026-11-04): an automatic stage of the live
        #: cryostat warps the clock and gives the operator's speed back after;
        #: (speed to restore, stage) while it warps
        self._warp: tuple | None = None
        self._warp_cancelled = None          # the stage the operator took the speed back in
        #: drop the warp to 1x on alarms, interlock trips and quenches
        self.auto_drop = True

    # ----------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.host.start()
        for name, h in self.host.hosted.items():
            for note in h.notes:
                self.events.write(self.clock.now(), "instrument", f"{name}: {note}")
        self.events.write(self.clock.now(), "engine", "emulators up")

    def stop(self) -> None:
        self.host.stop()
        self.served.close()
        self.save_clock()
        self.events.write(self.clock.now(), "engine", "stopped")
        self.events.close()

    def save_clock(self) -> Path:
        path = self.run.sub("state") / "clock.json"
        path.write_text(json.dumps([asdict(c) for c in self.clock.checkpoints()], indent=2),
                        encoding="utf-8")
        return path

    # ------------------------------------------------------------- control
    def play(self):
        self.events.write(self.clock.play(), "clock", "play")

    def pause(self):
        self.events.write(self.clock.pause(), "clock", "pause")

    def set_speed(self, speed: float, *, operator: bool = True):
        if operator and self._warp is not None:
            # the operator takes the speed back: no warp for the rest of this stage
            self._warp_cancelled = self._warp[1]
            self._warp = None
            self.events.write(self.clock.now(), "warp", "time warp cancelled by the operator")
        self.events.write(self.clock.set_speed(speed), "clock", f"speed {speed:g}")

    # ------------------------------------------------------------ time warp
    def warp_tick(self) -> None:
        """Once a second: warp the clock through the live cryostat's automatic
        stages (each takes about a minute of wall time), then restore."""
        bg = self.background
        if bg is None:
            return
        stage, want = bg.phase_id(), bg.auto_speed()
        if want is not None and stage != self._warp_cancelled:
            if self._warp is None:
                self._warp = (self.clock.speed, stage)
                self.events.write(self.clock.now(), "warp", f"time warp {want:g}x: {stage[0]}")
            self._warp = (self._warp[0], stage)
            if abs(self.clock.speed - want) > 1e-6:
                self.clock.set_speed(want)
                self.last_event = f"time warp {want:g}x ({bg.status()['phase_text']})"
        elif self._warp is not None:
            saved = self._warp[0]
            self._warp = None
            self.set_speed(saved, operator=False)
            self.last_event = f"time warp off: back to {saved:g}x"
        for msg in bg.pop_events():
            self.events.write(self.clock.now(), "world", msg)
            self.last_event = msg

    def alert(self, reason: str) -> None:
        """An alarm, interlock trip or quench: drop the warp to 1x (if enabled
        and not inside an automatic stage, whose alarms are expected)."""
        self.events.write(self.clock.now(), "alert", reason)
        if self.auto_drop and self._warp is None and self.clock.speed > 1.0:
            self.set_speed(1.0, operator=False)
            self.last_event = f"dropped to 1x: {reason}"

    def seek(self, sim_time: float):
        if self.background is not None:
            raise ValueError("the live cool-down cannot seek: change the speed instead")
        self.events.write(self.clock.seek(sim_time), "clock", f"seek {format_epoch(sim_time)}")
        if hasattr(self.provider, "reset"):           # target model re-initialised from the record
            self.provider.reset(sim_time)

    def set_fault(self, instrument: str, mode: str) -> None:
        self.host.set_fault(instrument, mode)
        self.events.write(self.clock.now(), "fault", f"{instrument} {mode}")
        self.last_event = f"fault {instrument} {mode}"

    def note(self, text: str) -> None:
        self.events.write(self.clock.now(), "note", text)
        self.last_event = f"note: {text[:60]}"

    # -------------------------------------------------------- control channel
    def status(self) -> dict:
        now = self.clock.now()
        truth = {}
        if hasattr(self.provider, "truth"):
            try:
                truth = self.provider.truth(now)
            except Exception:      # noqa: BLE001 - status must always answer
                truth = {}
        return {
            "sim_time": now, "sim_local": format_epoch(now), "running": self.clock.running,
            "speed": self.clock.speed, **self.info,
            "record_start": ("live (no record)" if self.background is not None
                             else format_epoch(self.timeline.start)),
            "record_end": "" if self.background is not None else format_epoch(self.timeline.end),
            "world": self.background.status() if self.background is not None else {},
            "warp": self._warp is not None, "auto_drop": self.auto_drop,
            "faults": {n: h.emulator.fault.get() for n, h in self.host.hosted.items()},
            "autopilot": dict(self.autopilot), "truth": truth, "last_event": self.last_event,
            "stop_requested": self.stop_requested.is_set(),
        }

    def handle(self, request: dict) -> dict:
        """Dispatch one control-channel request (see cooldown_sim/control.py)."""
        cmd = request.get("cmd")
        if cmd == "status":
            pass
        elif cmd == "play":
            self.play()
            self.last_event = "play"
        elif cmd == "pause":
            self.pause()
            self.last_event = "pause"
        elif cmd == "speed":
            self.set_speed(float(request["value"]))
            self.last_event = f"speed {float(request['value']):g}x"
        elif cmd == "world":
            if self.background is None:
                raise ValueError("world actions need the live cool-down (--source warm)")
            self.background.advance(self.clock.now())
            action = str(request["action"])
            detail = self.background.act(action, request.get("value"))
            self.events.write(self.clock.now(), "world", detail)
            self.last_event = detail
            if action in ("start_cooldown", "insert", "warm_up") and not self.clock.running:
                self.play()                      # an automatic stage starts at once
        elif cmd == "auto_drop":
            self.auto_drop = bool(request["on"])
            self.events.write(self.clock.now(), "warp", f"auto drop to 1x {'on' if self.auto_drop else 'off'}")
            self.last_event = f"auto drop to 1x {'on' if self.auto_drop else 'off'}"
        elif cmd == "seek":
            self.seek(float(request["value"]))
            self.last_event = f"seek {format_epoch(float(request['value']))}"
        elif cmd == "jump":
            target = self.clock.now() + 60.0 * float(request["minutes"])
            self.seek(target)
            self.last_event = f"jump {float(request['minutes']):+g} min"
        elif cmd == "fault":
            self.set_fault(request["instrument"], request["mode"])
        elif cmd == "autopilot":
            leg, on = request["leg"], bool(request["on"])
            if leg not in self.autopilot:
                raise ValueError(f"unknown autopilot leg {leg!r}")
            self.autopilot[leg] = on
            self.events.write(self.clock.now(), "autopilot", f"{leg} {'on' if on else 'off'}")
            self.last_event = f"autopilot {leg} {'on' if on else 'off'}"
        elif cmd == "note":
            self.note(str(request.get("text", "")))
        elif cmd == "mark":
            self.events.write(self.clock.now(), "mark", str(request.get("text", "")))
            self.last_event = "mark"
        elif cmd == "model":
            if not hasattr(self.provider, "set_input"):
                raise ValueError("this session has no target model")
            self.provider.set_input(request["key"], request["value"])
            self.events.write(self.clock.now(), "model", f"{request['key']} = {request['value']}")
            self.last_event = f"model {request['key']} = {request['value']}"
        elif cmd == "override":
            key = (request["instrument"], request["channel"])
            value = request.get("value")
            if value is None:
                self.provider.overrides.pop(key, None)
                detail = f"{key[0]}.{key[1]} back to the record"
            else:
                v = float(value)
                self.provider.overrides[key] = lambda t, v=v: v
                detail = f"{key[0]}.{key[1]} forced to {v:g} (recorded units)"
            self.events.write(self.clock.now(), "override", detail)
            self.last_event = f"override {detail}"
        elif cmd == "magic":
            # the DAQ's quick tune: set the microwave frequency to the best P-up
            # ("+") or P-down ("-") frequency at the present field, as an operator
            model = getattr(self.provider, "model", None)
            if model is None:
                raise ValueError("this session has no target model")
            sign = "+" if str(request.get("sign", "+")).startswith(("+", "p")) else "-"
            f = model.magic_GHz(sign, self.clock.now())
            if not (math.isfinite(f) and 138.0 <= f <= 142.0):
                raise ValueError(f"magic {sign}: {f:.3f} GHz is outside 138-142 GHz (field off?)")
            if self.autopilot.get("mw"):
                self.autopilot["mw"] = False
                self.events.write(self.clock.now(), "autopilot", "mw off (operator took the microwaves)")
            self.mw_requests.append(("frequency", round(f, 4)))
            self.events.write(self.clock.now(), "microwave", f"magic {sign}: {f:.4f} GHz")
            self.last_event = f"magic {sign}: {f:.3f} GHz"
        elif cmd == "stop":
            self.stop_requested.set()
            self.events.write(self.clock.now(), "session", "end requested")
            self.last_event = "session end requested"
        else:
            raise ValueError(f"unknown command {cmd!r}")
        return {"ok": True, "status": self.status()}
