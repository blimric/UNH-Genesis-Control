"""The live cool-down from warm (``--source warm``; Ells, 2026-11-04).

The live background's stages and its convergence rule, the speed slider, the
engine's time warp and auto drop to 1x, the session settings, and the live
magnet coupling (field from the IPS120 emulator, a new target on insert).
"""

import math

import pytest

from cooldown_sim import warp
from cooldown_sim.synth import live
from cooldown_sim.synth.live import BATH_REGION, LiveBackground

T0 = 1.8e9


def run_until(bg, phase, t, step=300.0, limit=24 * 3600.0):
    end = t + limit
    while bg.w.phase != phase and t < end:
        t += step
        bg.advance(t)
    assert bg.w.phase == phase, bg.w.phase
    return t


# ------------------------------------------------------------------ background
def test_starts_warm_and_off():
    bg = LiveBackground(T0)
    assert bg.w.phase == "warm" and bg.auto_speed() is None
    for s in ("F1", "F4", "T1", "M1", "M5"):
        assert bg.value_at(s, T0) > 250.0
    assert bg.value_at("magnet_lhe_level", T0) == 0.0
    assert math.isnan(bg.value_at("vp_temp", T0))
    assert bg.has("F11") and not bg.has("online_p") and math.isnan(bg.value_at("central_field", T0))


def test_cool_down_magnet_first_then_the_fridge_with_convergence():
    bg = LiveBackground(T0)
    bg.act("start_cooldown")
    t = run_until(bg, "fridge_cool", T0)
    # the magnet is cold and full before the fridge starts (data: M3-M5 4.0-4.4 K)
    for s in ("M3", "M4", "M5"):
        assert 3.9 < bg.value_at(s, t) < 4.6, s
    assert bg.value_at("magnet_lhe_level", t) == pytest.approx(live.LEVEL_FULL_IN, abs=0.2)
    # convergence: no bath-region sensor below ~4.2 K until all are near it
    while bg.w.phase == "fridge_cool":
        t += 60.0
        bg.advance(t)
        temps = [bg.value_at(s, t) for s in BATH_REGION]
        if min(temps) < live.BATH_4K - 0.15:
            assert bg.w.phase != "fridge_cool"
    assert t - T0 < 9 * 3600.0
    # F1/F2 at the top never get cold
    assert bg.value_at("F1", t) > 150.0 and bg.value_at("F2", t) > 80.0


def test_backing_pump_then_roots_then_insert():
    bg = LiveBackground(T0)
    bg.act("start_cooldown")
    t = run_until(bg, "cold", T0)
    assert bg.w.backing and not bg.w.roots
    assert bg.value_at("vp_temp", t) == pytest.approx(live.BATH_BACKING, abs=0.1)
    assert 15.0 < bg.value_at("manometer_hi", t) < 30.0          # ~20 Torr
    bg.act("backing", 0)
    with pytest.raises(ValueError):
        bg.act("roots", 1)                                       # the Roots needs the backing pump
    bg.act("backing", 1)
    bg.act("roots", 1)
    spike = bg.value_at("roots_flow_r", t + 30.0)
    assert spike > 30.0                                          # the switch-on spike
    assert bg.value_at("T1", t + 300.0) < 1.4                   # the cup answers within minutes
    t += 3600.0
    assert bg.value_at("T1", t) == pytest.approx(1.25, abs=0.05)
    assert bg.value_at("roots_flow_r", t) < 10.0
    # target stick insert: pumps off, T1/T3 and the NMR down, the bath to ~4.2 K
    bg.act("insert")
    assert not bg.w.backing and not bg.w.roots and not bg.nmr_up()
    assert math.isnan(bg.value_at("T1", t + 60.0))
    assert bg.value_at("manometer_hi", t + 500.0) > 760.0      # slightly above atmospheric
    assert bg.value_at("T1", t + 700.0) > 4.0                   # T1 back, not superfluid
    bg.advance(t + 1000.0)
    assert bg.nmr_up() and bg.w.phase == "cold" and bg.inserts == 1
    assert "backing pump" in bg.hint().lower()


def test_magnet_level_boils_off_faster_at_field_and_alerts_below_20_in():
    bg = LiveBackground(T0)
    bg.act("start_cooldown")
    t = run_until(bg, "cold", T0)
    level = bg.value_at("magnet_lhe_level", t)
    bg.field_fn = lambda: 5.0
    t += 3600.0
    drop = level - bg.value_at("magnet_lhe_level", t)
    assert drop == pytest.approx(live.BOILOFF_0T + 5.0 * live.BOILOFF_PER_T, rel=0.05)   # ~2.2 in/h
    bg.pop_alerts()
    while bg.value_at("magnet_lhe_level", t) >= live.LEVEL_PERMIT_IN:
        t += 3600.0
    assert any("below 20" in a for a in bg.pop_alerts())
    bg.act("magnet_fill")
    t += 1800.0                                                  # ~20 min to fill, then boil-off
    assert bg.value_at("magnet_lhe_level", t) > live.LEVEL_FULL_IN - 1.0 and not bg.w.filling


def test_shells_leak_raises_the_vacuum_and_fixes():
    bg = LiveBackground(T0)
    bg.act("start_cooldown")
    t = run_until(bg, "cold", T0)
    base = bg.value_at("ionivac", t)
    bg.act("shells_leak", 1)
    assert bg.value_at("ionivac", t + 1800.0) > 100 * base
    bg.act("shells_leak", 0)
    assert bg.value_at("ionivac", t + 9000.0) < 10 * base


def test_auto_stages_ask_for_about_a_minute_of_wall_time():
    bg = LiveBackground(T0)
    bg.act("start_cooldown")
    speed = bg.auto_speed()
    assert speed is not None and 1.0 < speed <= 600.0
    assert live.STAGE_SIM_S["fridge_cool"] / live.WALL_TARGET_S["fridge_cool"] <= 600.0


def test_warm_up_and_reset():
    bg = LiveBackground(T0)
    bg.act("start_cooldown")
    t = run_until(bg, "cold", T0)
    bg.act("warm_up")
    t = run_until(bg, "warm", t, step=600.0)
    assert bg.value_at("F11", t) > 200.0 and bg.value_at("magnet_lhe_level", t) == 0.0
    bg.act("start_cooldown")
    bg.act("reset_warm")
    assert bg.w.phase == "warm"


# --------------------------------------------------------------------- slider
@pytest.mark.parametrize("pos,speed", [(0.0, 0.0), (1.5, 0.0), (8.5, 1.0), (10.0, 1.0), (11.9, 1.0),
                                       (100.0, 600.0)])
def test_slider_clicks_at_pause_and_1x(pos, speed):
    assert warp.to_speed(pos) == pytest.approx(speed)


def test_slider_is_smooth_and_round_trips():
    for speed in (0.1, 0.3, 2.0, 10.0, 60.0, 250.0, 600.0):
        assert warp.to_speed(warp.to_pos(speed)) == pytest.approx(speed, rel=1e-6)
    speeds = [warp.to_speed(p) for p in range(13, 101)]
    assert speeds == sorted(speeds) and warp.to_pos(1.0, running=False) == 0.0


# -------------------------------------------------------------- engine warp
class FakeClock:
    def __init__(self):
        self.speed, self.running, self.t = 5.0, True, T0

    def now(self):
        return self.t

    def set_speed(self, s):
        self.speed = s
        return self.t

    def play(self):
        self.running = True
        return self.t


class FakeEvents:
    def __init__(self):
        self.rows = []

    def write(self, sim, kind, detail=""):
        self.rows.append((kind, detail))


def make_engine(bg):
    from cooldown_sim.engine import SimEngine
    eng = SimEngine.__new__(SimEngine)
    eng.clock, eng.events, eng.background = FakeClock(), FakeEvents(), bg
    eng._warp, eng._warp_cancelled, eng.auto_drop, eng.last_event = None, None, True, ""
    return eng


def test_warp_runs_the_automatic_stages_and_gives_the_speed_back():
    bg = LiveBackground(T0)
    eng = make_engine(bg)
    bg.act("start_cooldown")
    eng.warp_tick()
    assert eng.clock.speed == pytest.approx(bg.auto_speed()) and eng._warp is not None
    eng.alert("new major cryo alarm")                 # expected while warm: ignored
    assert eng.clock.speed > 1.0
    eng.clock.t = run_until(bg, "cold", T0)
    eng.warp_tick()
    assert eng.clock.speed == 5.0 and eng._warp is None
    eng.alert("magnet quench (supply)")               # now it drops the warp
    assert eng.clock.speed == 1.0 and "dropped to 1x" in eng.last_event


def test_operator_speed_cancels_the_warp_for_that_stage():
    bg = LiveBackground(T0)
    eng = make_engine(bg)
    bg.act("start_cooldown")
    eng.warp_tick()
    eng.set_speed(20.0)
    eng.warp_tick()
    assert eng.clock.speed == 20.0 and eng._warp is None


def test_auto_drop_can_be_switched_off():
    eng = make_engine(LiveBackground(T0))
    eng.auto_drop = False
    eng.alert("safety interlock trip")
    assert eng.clock.speed == 5.0


def test_a_live_cool_down_cannot_seek():
    eng = make_engine(LiveBackground(T0))
    with pytest.raises(ValueError):
        eng.seek(T0 + 60)


# ------------------------------------------------------------ session settings
def test_session_settings_are_a_closed_list(tmp_path):
    from cooldown_sim import profile
    with pytest.raises(ValueError):
        profile.generate(tmp_path, ("cryo",), session={"ls224_fridge": {"write_enabled": (True, "no")}})


def test_warm_session_enables_only_the_magnet_and_cold_board(tmp_path):
    import argparse

    import yaml

    from cooldown_sim import ports, profile
    from cooldown_sim.cli_run import session_settings
    stacks = ports.load_stacks()
    args = argparse.Namespace(mode="interactive", source="warm")
    stack = profile.generate(tmp_path, ("cryo",), session=session_settings(args, stacks, 0))
    enabled = {}
    for s in stack.iocs:
        cfg = yaml.safe_load(open(f"{s.folder}/settings.yaml", encoding="utf-8"))[s.ioc]
        enabled[s.ioc] = bool(cfg.get("write_enabled", False))
        if s.ioc == "trend_history":
            assert cfg["time_pv"] == "UNH:GEN:SIM:SIM_TIME" and cfg["backfill"] is False
    assert enabled.get("ips120") and enabled.get("siglent_coldboard")
    assert not any(v for k, v in enabled.items() if k not in ("ips120", "siglent_coldboard"))


# --------------------------------------------------------------- live magnet
def test_the_field_follows_the_emulated_magnet_and_an_insert_resets_p():
    from cooldown_sim import channel_map
    from cooldown_sim.clock import SimClock
    from cooldown_sim.emulators.ips120 import IPS120
    from cooldown_sim.model.provider import ModelProvider
    clock = SimClock(T0, 1.0, running=False)
    bg = LiveBackground(T0)
    prov = ModelProvider(bg, channel_map.load(), clock, t0=T0)
    emu = IPS120(initial_current_a=48.666, clock=clock.now)

    class Host:
        hosted = {"ips120": type("H", (), {"emulator": emu})()}
    prov.host = Host()
    assert prov.model.field_T(T0) == pytest.approx(5.0, abs=0.01)
    assert prov.model.magic_GHz("+", T0) == pytest.approx(140.1, abs=0.3)
    assert bg.value_at("fringe_g", T0) == pytest.approx(2.5 * 5.0 + 0.4, abs=0.05)
    prov.model.state.P = 0.4
    bg.act("start_cooldown")
    bg.w.phase = "cold"
    bg.act("insert")
    prov.live_tick()
    assert prov.model.state.P == 0.0
    # out of its helium with current in it, the magnet quenches
    bg.w.magnet_level = 1.0
    prov.live_tick()
    assert emu.system == 1 and prov.model.field_T(T0) == 0.0


def test_no_bath_until_there_is_liquid():
    # the warm cell's 760 Torr of gas is no vapour pressure: no 4.2 K bath while warm
    from cooldown_sim import channel_map
    from cooldown_sim.clock import SimClock
    from cooldown_sim.model.provider import ModelProvider
    bg = LiveBackground(T0)
    prov = ModelProvider(bg, channel_map.load(), SimClock(T0, 1.0, running=False), t0=T0)
    assert prov.model.hist_bath_T(T0) == pytest.approx(live.ROOM_K)       # falls back to T1
    bg.act("start_cooldown")
    t = run_until(bg, "cold", T0)
    assert prov.model.hist_bath_T(t) == pytest.approx(live.BATH_BACKING, abs=0.06)
