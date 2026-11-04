"""ModelProvider: the record, plus the closed-loop target model's response.

Drop-in replacement for ReplayProvider.  Thermometers, the cell pressure and
the shells' vacuum (IONIVAC) are passed through TargetModel, as are
Manometer-Lo (the same cell response as Manometer-Hi) and the two Roots
flowmeters (the record plus the modelled boil-off change); every other channel
-- separator flow, helium levels, fringe field -- is the plain record.
Exposes ``truth()``, ``set_input()`` and ``reset()`` for the engine / Sim
Control.
"""

from __future__ import annotations

import math

from ..providers import ReplayProvider
from .target import TargetModel, field_from_current

THERMO_INSTRUMENTS = ("ls224_fridge", "ls224_magnet")
#: Roots-line flowmeter IOC -> side
ROOTS_FLOWMETERS = {"flowmeter_left": "L", "flowmeter_pi": "R"}

#: Sim Control / ctl model keys -> Inputs fields (with coercion)
INPUT_KEYS = {
    "coldboard_heat_W": float, "quench": bool, "nmr_noise_x": float,
    "nmr_phase_offset_deg": float, "line_offset_MHz": float,
    "nmr_center_MHz": float, "nmr_span_MHz": float,
    "mw_on": bool, "mw_freq_GHz": float, "mw_power_dB": float, "mw_uca_V": float,
}


class ModelProvider(ReplayProvider):
    def __init__(self, timeline, cmap, clock, *, t0: float, params: dict | None = None,
                 cooldown: str | None = None, **kw):
        super().__init__(timeline, cmap, clock, **kw)
        self.model = TargetModel(timeline, t0, params, cooldown)
        self.host = None                 # set by the engine: lets inputs drive emulators
        self.fit_P = float("nan")        # online fitter's latest P (%), set by the NMR leg
        #: the interactive warm start's live cryostat (synth/live.py), or None
        self.background = timeline if hasattr(timeline, "act") else None
        self._inserts = 0
        self._magnet_quenched = False
        if self.background is not None:
            # Elena Long (2026-11-04): a live magnet -- the field is the IPS120
            # emulator's, so a ramp moves the NMR line and the DNP optimum
            self.model.field_source = self.magnet_field_T
            self.background.field_fn = self.magnet_field_T

    def recorded(self, instrument: str, channel: str, t: float) -> float:
        base = super().recorded(instrument, channel, t)
        if (instrument, channel) in self.overrides:
            return base
        if instrument in THERMO_INSTRUMENTS:
            return self.model.temperature(channel, base, t)
        if instrument == "mks902b":
            return self.model.cell_pressure(base, t)
        if instrument == "ionivac":
            return self.model.shells_pressure(base, t)
        if instrument == "manometer_low":
            return self.model.lo_cell_pressure(base, t)
        if instrument in ROOTS_FLOWMETERS:
            return self.model.roots_flow(ROOTS_FLOWMETERS[instrument], base, t)
        self.model.advance(t)
        return base

    # ------------------------------------------------------- live magnet
    def _magnet(self):
        h = self.host.hosted.get("ips120") if self.host else None
        return h.emulator if h is not None else None

    def magnet_field_T(self) -> float:
        """Field at the target (T) from the emulated supply's magnet current."""
        emu = self._magnet()
        if emu is None:
            return 0.0
        with emu._lock:
            emu.advance()
            amps = emu.magnet
        return field_from_current(amps)

    def live_tick(self) -> None:
        """Once a second (the session loop): couple the live cryostat, the
        magnet supply and the target model."""
        bg = self.background
        if bg is None:
            return
        t = self.clock.now()
        bg.advance(t)
        if bg.inserts != self._inserts:              # a new target: unpolarized
            self._inserts = bg.inserts
            with self.model._lock:
                self.model.advance(t)
                s = self.model.state
                s.P = s.Q = 0.0
                s.Pe = float("nan")
        emu = self._magnet()
        if emu is None:
            return
        with emu._lock:
            emu.advance()
            quenched, amps = emu.system == 1, abs(emu.magnet)
        # the solenoid out of its helium with current in it quenches
        if not quenched and amps > 1.0 and bg.w.magnet_level < 3.0:
            emu.quench()
            quenched = True
        if quenched and not self._magnet_quenched:
            bg.magnet_quenched()
        self._magnet_quenched = quenched

    def nmr_up(self) -> bool:
        """False while the live cryostat has the NMR down (a target insert)."""
        return self.background.nmr_up() if self.background is not None else True

    # ------------------------------------------------------------ control
    def truth(self, t: float) -> dict:
        out = self.model.truth(t)
        out["fit_P"] = self.fit_P
        out["fit_resid_P"] = self.fit_P - out["P"] if math.isfinite(self.fit_P) else float("nan")
        return out

    def reset(self, t: float) -> None:
        self.model.reset(t)

    def set_input(self, key: str, value) -> None:
        inp = self.model.inputs
        self.model.advance(self.clock.now())         # integrate up to now with the old inputs
        if key == "take_baseline":
            inp.baseline_requests += 1
            return
        if key not in INPUT_KEYS:
            raise ValueError(f"unknown model input {key!r}")
        if key == "mw_mode" or key.startswith("mw_"):
            inp.mw_mode = "operator"
        was = getattr(inp, key)
        setattr(inp, key, INPUT_KEYS[key](value))
        if key == "coldboard_heat_W":
            self._show_coldboard(float(value))
        if key == "quench" and bool(value) and not was and self.background is not None:
            emu = self._magnet()                     # a live magnet quenches with the target
            if emu is not None:
                emu.quench()

    def observe_mw(self, on: bool, freq_GHz: float, power_dB: float,
                   uca_V: float = float("nan")) -> bool:
        """The Microwave leg's REAL read-backs drive the model (no event logging
        here; the caller logs changes).  ``uca_V`` is the UCA voltage the chain
        sees (the caller maps output OFF to 5 V); NaN keeps the last value.
        Returns True if the RF state changed."""
        inp = self.model.inputs
        self.model.advance(self.clock.now())
        changed = inp.mw_mode != "operator" or inp.mw_on != bool(on)
        inp.mw_mode = "operator"
        inp.mw_on = bool(on)
        if math.isfinite(freq_GHz) and 100.0 < freq_GHz < 200.0:
            inp.mw_freq_GHz = float(freq_GHz)
        if math.isfinite(power_dB):
            inp.mw_power_dB = float(power_dB)
        if math.isfinite(uca_V):
            inp.mw_uca_V = float(uca_V)
        return changed

    def _show_coldboard(self, watts: float) -> None:
        """Make the emulated coldboard supply show the heat being applied (as if
        set at its front panel -- the Genesis coldboard IOC stays read-only)."""
        h = (self.host.hosted.get("siglent_coldboard") if self.host else None)
        if h is None:
            return
        load = h.emulator.load_ohms
        if watts > 0:
            v = math.sqrt(watts * load)
            h.emulator.set_state(voltage=v, current=min(v / load * 1.2, h.emulator.max_current),
                                 output=True)
        else:
            h.emulator.set_state(output=False)
