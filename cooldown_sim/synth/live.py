"""Live background for the interactive "cool-down from warm" simulation.

Ells (2026-11-04): a second interactive simulation in which the operator can
"push all the buttons" as if a cool-down were in progress.  Everything starts
warm and off.  Sim Control's world buttons then drive the cryostat:

* **Start Cool-down Sim**: the magnet's LN2 precool and LHe fill, then the
  fridge cool-down with convergence (F3-F11 and the cup hang warm while the
  liquid collects, then reach ~4.2 K together; F1/F2 at the top never get
  cold), then the backing pump takes the bath to ~1.9 K;
* **Backing pump / Roots** on and off (the Roots needs the backing pump):
  ~4.2 K with no pumping, ~1.9 K on the backing pump (cell ~20 Torr), ~1.1 K
  with the Roots (the flow spikes, then settles);
* **Magnet LHe fill** (to ~31 in, the sensor top), with boil-off growing with
  the field; **shells and cell leaks**; **Warm up** and **Reset to warm**;
* **Target stick insert**: pumps off, T1/T3 and the NMR go down, the cell
  goes slightly above atmospheric and the bath stops being superfluid
  (~4.2 K); then T1/T3 come back, then the NMR (no signal yet).  The operator
  turns the backing pump and the Roots back on.

Simulated time follows real cool-downs (2025-11, 2026-06 records from warm:
fridge 300 -> 4 K in 3.75-5 h, backing pump to ~1.9 K in 15-45 min, Roots to
~1.1 K); the automatic stages ask the engine for a time warp
(:meth:`auto_speed`) so each takes about a minute of wall time.

The background answers the simulator exactly like a past record does (the
:class:`~cooldown_sim.data.timeline.Timeline` read API: ``value_at``,
``samples``, ``has`` ...), under the same channel names, so the channel map,
the emulators and the closed-loop target model (microwaves, P and Q, the NMR
line) run unchanged on top of it.  It is state-driven: it integrates forward
in sim time on demand and cannot seek.
"""

from __future__ import annotations

import collections
import math
import threading
from dataclasses import dataclass, field

import numpy as np

from ..model import physics as ph

NAN = float("nan")
ROOM_K = 295.0
#: longest integration step (sim s)
STEP_S = 10.0
#: history kept for samples() (sim s) and its sampling period
HISTORY_S = 6 * 3600.0
HISTORY_DT = 20.0

FRIDGE = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11")
CUP = ("T1", "T3")
MAGNET = ("M1", "M2", "M3", "M4", "M5")
#: the "bath region": converges together (none below ~4.2 K until all are there)
BATH_REGION = ("F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "T1", "T3")

#: every record channel this background serves
CHANNELS = (FRIDGE + CUP + MAGNET + (
    "manometer_hi", "manometer_lo", "vp_temp", "roots_pressure", "ionivac", "fringe_g",
    "roots_flow_r", "roots_flow_l", "separator_flow", "fridge_he_level", "magnet_lhe_level"))

# ------------------------------------------------------------------ stage data
#: magnet LN2 precool (sim s) and targets (K) / time constants (s)
MAGNET_LN2_S = 3600.0
MAGNET_LN2 = {"M1": (150.0, 2400.0), "M2": (95.0, 3600.0), "M3": (78.0, 720.0),
              "M4": (74.0, 480.0), "M5": (73.0, 300.0)}
#: magnet LHe transfer: duration, level fill (start, duration) and time constants
MAGNET_LHE_S = 3600.0
LEVEL_FILL_START_S, LEVEL_FILL_S = 600.0, 2700.0
MAGNET_LHE_TAU = {"M1": 900.0, "M2": 900.0, "M3": 480.0, "M4": 300.0, "M5": 240.0}
#: operating magnet temperatures in LHe (data: M3-M5 4.0-4.4 K, M2 4-6 K)
MAGNET_COLD = {"M2": 4.6, "M3": 4.40, "M4": 4.16, "M5": 4.02}
LEVEL_FULL_IN = 30.9          # the sensor's top: the reading never goes higher
LEVEL_PERMIT_IN = 20.0
#: boil-off (in/h): ~0.45 at 0 T, ~2.2 at 5 T (2025-11, 2026-06)
BOILOFF_0T, BOILOFF_PER_T = 0.45, 0.35
FILL_RATE_IN_PER_H = 40.0

#: fridge cool-down: total, convergence start and its time constant (sim s)
FRIDGE_COOL_S = 3.0 * 3600.0
CONVERGE_TAU_S = 600.0
#: per sensor: (delay s, K/h after the delay, hang K before the liquid collects)
FRIDGE_SCHEDULE = {
    "F3": (1800.0, 260.0, 55.0), "F4": (0.0, 800.0, 25.0), "F5": (600.0, 400.0, 30.0),
    "F6": (1200.0, 300.0, 40.0), "F7": (3000.0, 110.0, 48.0), "F8": (2400.0, 115.0, 46.0),
    "F9": (4800.0, 140.0, 50.0), "F10": (3600.0, 120.0, 47.0), "F11": (4200.0, 130.0, 45.0),
    "T1": (4200.0, 125.0, 46.0), "T3": (4200.0, 120.0, 47.0)}
#: F1/F2 (top, by the pump-out line) never get cold: (cool-down, backing, Roots) K
TOP = {"F1": (225.0, 215.0, 260.0), "F2": (135.0, 120.0, 180.0)}
TOP_TAU_S = 2400.0

#: bath temperature (K) and cell pressure (Torr) for each pumping state
BATH_4K, BATH_BACKING, BATH_ROOTS = 4.20, 1.93, 1.10
CELL_ATM_TORR = 785.0         # slightly above atmospheric: no pumping, the cell vented
#: bath time constants (s): pump-down on the backing pump, Roots, warming with no pumping
TAU_BACKING, TAU_ROOTS, TAU_NO_PUMP = 600.0, 75.0, 900.0
#: how far above the bath each sensor reads, at 4.2 K / 1.93 K / 1.1 K (data)
EXCESS = {"F3": (0.8, 7.0, 24.0), "F4": (0.5, 4.0, 14.0), "F5": (0.3, 2.0, 7.0),
          "F6": (0.2, 0.6, 3.5), "F7": (0.05, 0.25, 0.4), "F8": (0.08, 0.45, 0.9),
          "F9": (-0.1, -0.08, -0.1), "F10": (0.03, 0.1, 0.15), "F11": (0.0, 0.02, 0.05),
          "T1": (0.05, 0.03, 0.15), "T3": (0.08, 0.05, 0.25)}
#: Elena Long (2026-11-04): a thermometer under the liquid reads the liquid's
#: temperature -- its plot follows the vapour pressure -- apart from a small
#: calibration offset; only the uncovered ones read warmer (EXCESS) and lag.
#: Fridge LHe level reading (in) at which each is covered (top -> bottom: F3/F4,
#: F5, F6, F8, F7, F9, F10, F11, then the cup below F11)
SENSOR_HEIGHT_IN = {"F3": 10.5, "F4": 9.0, "F5": 7.0, "F6": 5.0, "F8": 2.5, "F7": 0.0,
                    "F9": -3.0, "F10": -6.0, "F11": -8.5, "T1": -12.0, "T3": -12.0}
#: calibration offsets of covered thermometers (K); F9 reads systematically low
CAL_OFFSET_K = {"F9": -0.08, "F7": 0.01, "F8": 0.02, "F10": 0.01, "T3": 0.02}
#: fridge level after the cool-down's fill, with no pumping (the separator
#: keeps it there), and where pumping leaves it (liquid above T1, at or just
#: below F11; the 2025-11 / 2026-06 records fall ~1.45 in/h while pumped)
LEVEL_FILLED_IN, LEVEL_PUMPED_IN, LEVEL_FALL_IN_PER_H = 4.0, -9.0, 1.45
#: sensor time constants while cold (s): the cup responds within a couple of minutes
SENSOR_TAU = {"T1": 60.0, "T3": 90.0, "F11": 1500.0, "F9": 1200.0, "F10": 1000.0}
DEFAULT_SENSOR_TAU = 600.0

#: Roots line flow (slm): backing only, Roots steady, the switch-on spike
FLOW_BACKING, FLOW_ROOTS, FLOW_SPIKE, SPIKE_TAU = 20.0, 6.0, 50.0, 90.0
FLOW_ZERO = -0.3              # the flowmeters' zero offset
SEPARATOR_FLOW = 45.0

#: target-stick insert: sensors back after, NMR back after (sim s)
INSERT_SENSORS_S, INSERT_NMR_S = 600.0, 900.0
WARMUP_S = 6 * 3600.0

#: shells (insulating) vacuum (Torr): warm, cold, with a leak
SHELLS_WARM, SHELLS_COLD, SHELLS_LEAK = 1.5e-5, 4.0e-7, 5.0e-3

#: wall seconds each automatic stage should take (the time warp)
WALL_TARGET_S = {"magnet_ln2": 30.0, "magnet_lhe": 30.0, "fridge_cool": 60.0,
                 "pumpdown": 20.0, "inserting": 20.0, "warming": 60.0}
STAGE_SIM_S = {"magnet_ln2": MAGNET_LN2_S, "magnet_lhe": MAGNET_LHE_S,
               "fridge_cool": FRIDGE_COOL_S + 5 * CONVERGE_TAU_S, "pumpdown": 2400.0,
               "inserting": INSERT_NMR_S, "warming": WARMUP_S}

PHASE_TEXT = {
    "warm": "Warm and off",
    "magnet_ln2": "Magnet LN2 precool",
    "magnet_lhe": "Magnet LHe fill",
    "fridge_cool": "Fridge cooling (convergence)",
    "pumpdown": "Backing pump: bath to ~1.9 K",
    "cold": "Cold",
    "inserting": "Target stick insert",
    "warming": "Warming up",
}


def relax(x: float, target: float, tau: float, dt: float) -> float:
    if not math.isfinite(x):
        return target
    return target + (x - target) * math.exp(-dt / max(tau, 1e-6))


def interp_excess(sensor: str, bath_K: float) -> float:
    """Excess of ``sensor`` over the bath, interpolated between the pumping states."""
    a, b, c = EXCESS[sensor]
    if bath_K >= BATH_4K:
        return a
    if bath_K >= BATH_BACKING:
        f = (bath_K - BATH_BACKING) / (BATH_4K - BATH_BACKING)
        return b + f * (a - b)
    f = max(bath_K - BATH_ROOTS, 0.0) / (BATH_BACKING - BATH_ROOTS)
    return c + f * (b - c)


@dataclass
class World:
    t: float
    phase: str = "warm"
    phase_t0: float = 0.0
    temps: dict = field(default_factory=dict)
    magnet_level: float = 0.0
    fridge_level: float = -16.0
    cell: float = 760.0
    bath: float = NAN            # bath temperature once there is liquid
    liquid: bool = False
    converge: float = NAN        # the liquid's temperature during convergence
    backing: bool = False
    roots: bool = False
    roots_on_at: float = NAN
    flow: float = FLOW_ZERO
    shells: float = SHELLS_WARM
    shells_leak: bool = False
    cell_leak: bool = False
    filling: bool = False
    sensors_up: bool = True       # T1/T3 (the target stick's thermometers)
    nmr_up: bool = True
    quench_until: float = -math.inf


class LiveBackground:
    """The warm-start cryostat, behind the Timeline read API."""

    def __init__(self, t0: float, field_fn=None):
        self._lock = threading.RLock()
        self.t0 = float(t0)
        #: () -> field at the target (T); set by the provider (the IPS120 emulator)
        self.field_fn = field_fn or (lambda: 0.0)
        #: (message) -> None for important events (the engine's warp drop)
        self.events: collections.deque = collections.deque(maxlen=50)
        #: the important ones (quench, magnet LHe low): the engine drops the warp to 1x
        self.alerts: collections.deque = collections.deque(maxlen=20)
        self.max_hold_s = 300.0
        self.table = None
        self._hist: dict[str, collections.deque] = {c: collections.deque() for c in CHANNELS}
        self._hist_t = -math.inf
        self.w = self._warm(self.t0)
        #: incremented on every insert: the target model resets P and Q (a new target)
        self.inserts = 0

    # ------------------------------------------------------------ Timeline API
    @property
    def start(self) -> float:
        return self.t0

    @property
    def end(self) -> float:
        return self.t0 + 10 * 365 * 86400.0    # open-ended (finite: dates must format)

    def has(self, channel: str) -> bool:
        return channel in CHANNELS

    def coverage(self, channel: str) -> float:
        return 1.0 if channel in CHANNELS else 0.0

    def value_at(self, channel: str, t: float) -> float:
        if channel not in CHANNELS:
            return NAN
        with self._lock:
            if t >= self.w.t:
                self.advance(t)
                return self._value(channel)
            return self._past(channel, t)

    def values_at(self, channel: str, ts) -> np.ndarray:
        return np.array([self.value_at(channel, float(t)) for t in np.asarray(ts, float)])

    def text_at(self, channel: str, t: float) -> str:
        return ""

    def samples(self, channel: str, t0: float = -np.inf, t1: float = np.inf):
        with self._lock:
            rows = [(t, v) for t, v in self._hist.get(channel, ()) if t0 <= t <= t1 and math.isfinite(v)]
        if not rows:
            return np.array([]), np.array([])
        t, v = zip(*rows)
        return np.asarray(t, float), np.asarray(v, float)

    def gaps(self, min_gap_s: float = 120.0) -> list:
        return []

    # ------------------------------------------------------------------ state
    def _warm(self, t: float) -> World:
        w = World(t=t, phase="warm", phase_t0=t)
        warm = {"F9": ROOM_K + 15.0, "F11": ROOM_K - 30.0}      # F9 reads high, F11 low (data)
        w.temps = {s: warm.get(s, ROOM_K) for s in FRIDGE + CUP + MAGNET}
        return w

    def _set_phase(self, phase: str) -> None:
        w = self.w
        if w.phase != phase:
            self.events.append(f"{PHASE_TEXT.get(w.phase, w.phase)} -> {PHASE_TEXT.get(phase, phase)}")
        w.phase, w.phase_t0 = phase, w.t

    def advance(self, t: float) -> None:
        with self._lock:
            while self.w.t < t:
                dt = min(STEP_S, t - self.w.t)
                self._step(dt)
                self.w.t += dt
                if self.w.t - self._hist_t >= HISTORY_DT:
                    self._record()

    def _record(self) -> None:
        self._hist_t = self.w.t
        cutoff = self.w.t - HISTORY_S
        for c, rows in self._hist.items():
            rows.append((self.w.t, self._value(c)))
            while rows and rows[0][0] < cutoff:
                rows.popleft()

    def _past(self, channel: str, t: float) -> float:
        rows = self._hist.get(channel)
        if not rows:
            return NAN
        times = [r[0] for r in rows]
        i = int(np.searchsorted(times, t, side="right")) - 1
        return rows[i][1] if i >= 0 else NAN

    # ------------------------------------------------------------------- step
    def _step(self, dt: float) -> None:
        w = self.w
        age = w.t - w.phase_t0
        B = abs(self._field())
        if w.phase == "magnet_ln2":
            for s, (target, tau) in MAGNET_LN2.items():
                w.temps[s] = relax(w.temps[s], target, tau, dt)
            if age >= MAGNET_LN2_S:
                self._set_phase("magnet_lhe")
        elif w.phase == "magnet_lhe":
            for s in MAGNET:
                w.temps[s] = relax(w.temps[s], self._magnet_cold_target(s), MAGNET_LHE_TAU[s], dt)
            if age >= LEVEL_FILL_START_S:
                w.magnet_level = min(LEVEL_FULL_IN, LEVEL_FULL_IN * (age - LEVEL_FILL_START_S) / LEVEL_FILL_S)
            if age >= MAGNET_LHE_S:
                self._set_phase("fridge_cool")
        else:
            self._magnet_step(dt, B)
        if w.phase == "fridge_cool":
            self._fridge_cool_step(dt, age)
        elif w.phase == "pumpdown":
            self._cold_step(dt)
            if abs(w.bath - BATH_BACKING) < 0.05:
                self._set_phase("cold")
                self.events.append("cold: bath ~1.9 K on the backing pump -- press Roots On")
        elif w.phase in ("cold",):
            self._cold_step(dt)
        elif w.phase == "inserting":
            self._insert_step(dt, age)
        elif w.phase == "warming":
            self._warming_step(dt, age)
        self._vacuum_step(dt)

    # magnet ------------------------------------------------------------------
    def _magnet_cold_target(self, s: str) -> float:
        level = self.w.magnet_level
        if s == "M1":                        # above the liquid unless the dewar is full
            return 4.2 if level >= LEVEL_FULL_IN - 0.5 else min(75.0, 4.2 + 6.0 * (LEVEL_FULL_IN - level))
        base = MAGNET_COLD[s]
        if level < 8.0:                      # the solenoid starts to come out of the liquid
            base += (8.0 - level) * {"M2": 4.0, "M3": 2.0, "M4": 1.0, "M5": 0.6}[s]
        return base

    def _magnet_step(self, dt: float, B: float) -> None:
        w = self.w
        if w.phase == "warm" or (w.phase == "warming"):
            return
        rate = BOILOFF_0T + BOILOFF_PER_T * B + (3.0 if w.shells_leak else 0.0)
        if w.filling:
            rate -= FILL_RATE_IN_PER_H
            if w.magnet_level >= LEVEL_FULL_IN:
                w.filling = False
                self.events.append(f"magnet LHe fill done ({LEVEL_FULL_IN:.1f} in)")
        before = w.magnet_level
        w.magnet_level = min(LEVEL_FULL_IN, max(0.0, w.magnet_level - rate * dt / 3600.0))
        if before >= LEVEL_PERMIT_IN > w.magnet_level:
            self._alert(f"magnet LHe below {LEVEL_PERMIT_IN:.0f} in: magnet moves blocked -- fill it")
        quench = w.t < w.quench_until
        for s in MAGNET:
            target = 15.0 if quench and s in ("M3", "M4", "M5") else self._magnet_cold_target(s)
            w.temps[s] = relax(w.temps[s], target, 300.0, dt)

    def magnet_quenched(self) -> None:
        """The supply quenched (emulator): the magnet warms and boils LHe off."""
        with self._lock:
            w = self.w
            w.quench_until = w.t + 900.0
            w.magnet_level = max(0.0, w.magnet_level - 8.0)
            self._alert("MAGNET QUENCH")

    def _alert(self, message: str) -> None:
        self.events.append(message)
        self.alerts.append(message)

    # fridge ------------------------------------------------------------------
    def _fridge_cool_step(self, dt: float, age: float) -> None:
        w = self.w
        w.cell = relax(w.cell, 760.0, 600.0, dt)
        w.flow = FLOW_ZERO + 15.0 + 85.0 * min(age / FRIDGE_COOL_S, 1.0)
        w.fridge_level = -16.0 + (LEVEL_FILLED_IN + 16.0) * min(age / (FRIDGE_COOL_S + 2 * CONVERGE_TAU_S), 1.0)
        for s, (target, _b, _r) in TOP.items():
            w.temps[s] = relax(w.temps[s], target, TOP_TAU_S, dt)
        if age < FRIDGE_COOL_S:
            for s, (delay, rate, hang) in FRIDGE_SCHEDULE.items():
                pre = ROOM_K - rate * max(0.0, age - delay) / 3600.0
                w.temps[s] = relax(w.temps[s], max(hang, pre), 120.0, dt)
            return
        # the liquid collects: everything in the bath region converges on it,
        # none going below it, so none passes ~4.2 K until all reach it
        if not math.isfinite(w.converge):
            w.converge = max(w.temps[s] for s in BATH_REGION)
        w.converge = relax(w.converge, BATH_4K, CONVERGE_TAU_S, dt)
        for s in BATH_REGION:
            w.temps[s] = max(min(w.temps[s], w.converge + interp_excess(s, BATH_4K)),
                             BATH_4K + interp_excess(s, BATH_4K))
        if w.converge < BATH_4K + 0.1:
            w.liquid, w.bath, w.converge = True, BATH_4K, NAN
            w.backing = True                 # the sequence pumps on the bath itself
            self.events.append("fridge at ~4.2 K: backing pump on")
            self._set_phase("pumpdown")

    def _bath_target(self) -> tuple[float, float]:
        """(target bath K, time constant s) for the pumps as set."""
        w = self.w
        if w.backing and w.roots:
            return BATH_ROOTS + (0.25 if w.cell_leak else 0.0), TAU_ROOTS
        if w.backing:
            return BATH_BACKING + (0.25 if w.cell_leak else 0.0), TAU_BACKING
        return BATH_4K, TAU_NO_PUMP

    def _cold_step(self, dt: float) -> None:
        w = self.w
        target, tau = self._bath_target()
        w.bath = relax(w.bath, target, tau, dt)
        w.cell = CELL_ATM_TORR if (not w.backing and w.bath >= BATH_4K - 0.02) else ph.he4_p90_torr(w.bath)
        # the level falls while pumped, to just above the cup; the separator
        # tops it back up with no pumping
        if w.backing:
            w.fridge_level = max(LEVEL_PUMPED_IN, w.fridge_level - LEVEL_FALL_IN_PER_H * dt / 3600.0)
        else:
            w.fridge_level = relax(w.fridge_level, LEVEL_FILLED_IN, 7200.0, dt)
        self._bath_sensors(dt)
        col = 2 if (w.backing and w.roots) else 1 if w.backing else 0
        for s, values in TOP.items():
            w.temps[s] = relax(w.temps[s], values[col] if col else values[0], TOP_TAU_S, dt)
        # Roots line flow
        if w.backing and w.roots:
            spike = FLOW_SPIKE * math.exp(-(w.t - w.roots_on_at) / SPIKE_TAU) if math.isfinite(w.roots_on_at) else 0.0
            steady = FLOW_ROOTS + 10.0 * math.exp(-(w.t - w.roots_on_at) / 1200.0) if math.isfinite(w.roots_on_at) else FLOW_ROOTS
            w.flow = steady + spike + (5.0 if w.cell_leak else 0.0)
        elif w.backing:
            w.flow = relax(w.flow, FLOW_BACKING + (5.0 if w.cell_leak else 0.0), 300.0, dt)
        else:
            w.flow = relax(w.flow, FLOW_ZERO, 60.0, dt)

    def covered(self, sensor: str) -> bool:
        """True while ``sensor`` is under the liquid (it reads the liquid's temperature)."""
        w = self.w
        h = SENSOR_HEIGHT_IN.get(sensor)
        return bool(w.liquid and h is not None and w.fridge_level >= h)

    def _bath_sensors(self, dt: float, tau_cap: float = math.inf) -> None:
        """Covered sensors read the bath (plus calibration offset), at once; the
        others relax toward the bath plus their excess."""
        w = self.w
        for s in BATH_REGION:
            if s in CUP and not w.sensors_up:
                continue
            if self.covered(s):
                w.temps[s] = w.bath + CAL_OFFSET_K.get(s, 0.0)
            else:
                w.temps[s] = relax(w.temps[s], w.bath + interp_excess(s, w.bath),
                                   min(SENSOR_TAU.get(s, DEFAULT_SENSOR_TAU), tau_cap), dt)

    def _insert_step(self, dt: float, age: float) -> None:
        w = self.w
        w.bath = relax(w.bath, BATH_4K + 0.05, 180.0, dt)   # no longer superfluid: up to ~4.2 K
        w.cell = relax(w.cell, CELL_ATM_TORR, 120.0, dt)
        w.flow = relax(w.flow, FLOW_ZERO, 60.0, dt)
        w.fridge_level = relax(w.fridge_level, LEVEL_FILLED_IN, 7200.0, dt)
        if not w.sensors_up and age >= INSERT_SENSORS_S:
            w.sensors_up = True
            self.events.append("target stick in: T1/T3 reading")
        self._bath_sensors(dt, tau_cap=300.0)
        if age >= INSERT_NMR_S:
            w.nmr_up = True
            self.events.append("NMR back (no signal yet): backing pump on next")
            self._set_phase("cold")

    def _warming_step(self, dt: float, age: float) -> None:
        w = self.w
        w.backing = w.roots = w.filling = False
        w.liquid = age < 0.3 * WARMUP_S
        tau = WARMUP_S / 4.0
        warm = self._warm(w.t).temps
        for s in FRIDGE + CUP + MAGNET:
            w.temps[s] = relax(w.temps[s], warm[s], tau, dt)
        w.magnet_level = max(0.0, w.magnet_level - 12.0 * dt / 3600.0)
        w.fridge_level = relax(w.fridge_level, -16.0, tau, dt)
        w.cell = relax(w.cell, 760.0, 600.0, dt)
        w.flow = relax(w.flow, FLOW_ZERO, 300.0, dt)
        w.bath = NAN if not w.liquid else relax(w.bath, BATH_4K, 600.0, dt)
        if age >= WARMUP_S:
            self.w = self._warm(w.t)
            self.events.append("warm and off")

    def _vacuum_step(self, dt: float) -> None:
        w = self.w
        m = min(max((w.temps["M3"] - 4.0) / (ROOM_K - 4.0), 0.0), 1.0)
        base = math.exp(math.log(SHELLS_COLD) + (math.log(SHELLS_WARM) - math.log(SHELLS_COLD)) * math.sqrt(m))
        target = SHELLS_LEAK if w.shells_leak else base
        w.shells = math.exp(relax(math.log(w.shells), math.log(target), 300.0 if w.shells_leak else 600.0, dt))

    # ----------------------------------------------------------------- values
    def _field(self) -> float:
        try:
            b = float(self.field_fn())
        except Exception:                    # noqa: BLE001 - a missing magnet reads 0 T
            return 0.0
        return b if math.isfinite(b) else 0.0

    def _value(self, channel: str) -> float:
        w = self.w
        if channel in CUP and not w.sensors_up:
            return NAN
        if channel in w.temps:
            return float(w.temps[channel])
        if channel in ("manometer_hi", "manometer_lo"):
            return float(w.cell)
        if channel == "vp_temp":
            T = ph.he4_t90_K(w.cell) if w.liquid else NAN
            return T if math.isfinite(T) and 0.5 < T < 5.5 else NAN
        if channel == "roots_pressure":
            if w.backing and w.roots:
                return 0.5
            return 0.45 * w.cell if w.backing else w.cell
        if channel == "ionivac":
            return float(w.shells)
        if channel == "fringe_g":
            return 2.5 * self._field() + 0.4
        if channel == "roots_flow_r":
            return float(w.flow)
        if channel == "roots_flow_l":
            return FLOW_ZERO
        if channel == "separator_flow":
            on = w.phase in ("magnet_lhe", "fridge_cool", "pumpdown", "cold")
            return SEPARATOR_FLOW if on else FLOW_ZERO
        if channel == "fridge_he_level":
            return float(w.fridge_level)
        if channel == "magnet_lhe_level":
            return float(w.magnet_level)
        return NAN

    # --------------------------------------------------------------- controls
    def act(self, action: str, value=None) -> str:
        """Apply one world action; returns what happened (for the event log)."""
        with self._lock:
            w = self.w
            on = bool(value) if value is not None else True
            cold = w.phase in ("cold", "pumpdown")
            if action == "start_cooldown":
                if w.phase != "warm":
                    raise ValueError(f"start the cool-down from warm (now: {PHASE_TEXT[w.phase]})")
                self._set_phase("magnet_ln2")
                return "cool-down started: magnet LN2 precool"
            if action == "backing":
                if not (cold or w.phase == "inserting") and on:
                    raise ValueError("nothing to pump yet: start the cool-down first")
                if w.phase == "inserting":
                    raise ValueError("wait for the insert to finish (NMR back)")
                w.backing = on
                if not on and w.roots:
                    w.roots = False
                    self.events.append("Roots off with the backing pump")
                return f"backing pump {'on' if on else 'off'}"
            if action == "roots":
                if on and not w.backing:
                    raise ValueError("the Roots needs the backing pump: turn the backing pump on first")
                if on and w.phase != "cold":
                    raise ValueError("wait until the fridge is cold")
                if on and not w.roots:
                    w.roots_on_at = w.t
                w.roots = on
                return f"Roots {'on' if on else 'off'}"
            if action == "magnet_fill":
                if w.phase in ("warm", "magnet_ln2", "warming"):
                    raise ValueError("the magnet is not cold: start the cool-down first")
                w.filling = True
                return "magnet LHe fill started"
            if action == "shells_leak":
                w.shells_leak = on
                return f"shells leak {'on' if on else 'fixed'}"
            if action == "cell_leak":
                w.cell_leak = on
                return f"cell leak {'on' if on else 'fixed'}"
            if action == "insert":
                if w.phase != "cold":
                    raise ValueError("insert the target stick into a cold fridge")
                w.backing = w.roots = False
                w.sensors_up = w.nmr_up = False
                self.inserts += 1
                self._set_phase("inserting")
                return "target stick insert: pumps off, T1/T3 and NMR down"
            if action == "warm_up":
                if w.phase == "warm":
                    raise ValueError("already warm")
                self._set_phase("warming")
                return "warm-up started"
            if action == "reset_warm":
                self.w = self._warm(w.t)
                self.events.append("reset to warm and off")
                return "reset to warm and off"
            raise ValueError(f"unknown world action {action!r}")

    # ---------------------------------------------------------------- status
    def auto_speed(self, max_speed: float = 600.0) -> float | None:
        """The time warp an automatic stage wants (sim s per wall s), or None."""
        with self._lock:
            phase = self.w.phase
            if phase not in WALL_TARGET_S:
                return None
            return min(max(STAGE_SIM_S[phase] / WALL_TARGET_S[phase], 1.0), max_speed)

    def phase_id(self) -> tuple[str, float]:
        with self._lock:
            return self.w.phase, self.w.phase_t0

    def hint(self) -> str:
        w = self.w
        if w.phase == "warm":
            return "Press Start Cool-down Sim"
        if w.phase in ("magnet_ln2", "magnet_lhe", "fridge_cool", "pumpdown", "warming"):
            return f"{PHASE_TEXT[w.phase]} (automatic, time warp)"
        if w.phase == "inserting":
            return "Target stick going in: wait for T1/T3 and the NMR"
        if not w.backing:
            return "Turn the backing pump on (fridge to ~20 Torr, ~1.9 K)"
        if not w.roots:
            return "Turn the Roots on (fridge to ~1.1 K)"
        if w.magnet_level < LEVEL_PERMIT_IN:
            return "Fill the magnet LHe (the magnet needs 20 in)"
        if self._field() < 0.5:
            return "Ready: ramp the magnet (Magnet tab) for NMR"
        return "Running: microwaves, NMR, ssRF as you like"

    def status(self) -> dict:
        with self._lock:
            w = self.w
            return {"phase": w.phase, "phase_text": PHASE_TEXT.get(w.phase, w.phase), "hint": self.hint(),
                    "fridge_level_in": w.fridge_level,
                    "covered": [s for s in BATH_REGION if self.covered(s)],
                    "backing": w.backing, "roots": w.roots, "filling": w.filling,
                    "shells_leak": w.shells_leak, "cell_leak": w.cell_leak,
                    "magnet_level_in": w.magnet_level, "bath_K": w.bath if w.liquid else NAN,
                    "cell_torr": w.cell, "sensors_up": w.sensors_up, "nmr_up": w.nmr_up,
                    "auto": w.phase in WALL_TARGET_S}

    def bath_temperature(self, t: float) -> float:
        """The helium bath (K) at t, NaN before there is liquid."""
        with self._lock:
            if t >= self.w.t:
                self.advance(t)
            return float(self.w.bath) if self.w.liquid else NAN

    def nmr_up(self) -> bool:
        with self._lock:
            return self.w.nmr_up

    def pop_events(self) -> list[str]:
        with self._lock:
            out = list(self.events)
            self.events.clear()
            return out

    def pop_alerts(self) -> list[str]:
        with self._lock:
            out = list(self.alerts)
            self.alerts.clear()
            return out
