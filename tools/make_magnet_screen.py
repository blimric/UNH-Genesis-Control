#!/usr/bin/env python3
"""Generate gui/genesis_magnet.bob: the magnet's IPS120-10 control screen.

Run:  python tools/make_magnet_screen.py

The Phoebus tab for magnet_ioc (``UNH:GEN:MAG``), ported from the student's
Magnet_V3 / V4 screens with the review's screen fixes (issue 14): heater ON
and OFF, MATCH and the outage button ask for confirmation; RAMP and HOLD do
not (Elena Long, 2026-11-04: the RAMP pop-up came up on every field trim).
The switch heater shows its read-back state and has two explicit buttons
instead of one toggle.  From V4: the SYSTEM CHECKS line, the heater ON and OFF bars, the
R20 heater verification, the inductance check and its bypass, the low-helium
warning; the helium level and the fringe field are read from the Genesis
IOCs (the AMI 135, the LS455), not typed in.  The big red POWER OUTAGE
button is review issue 19.  Opened from the Panopticon's magnet card.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "gui" / "genesis_magnet.bob"
W, H = 1400, 860

_spec = importlib.util.spec_from_file_location("make_panopticon", Path(__file__).with_name("make_panopticon.py"))
pan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pan)

MAG = "UNH:GEN:MAG"
CRYO = "UNH:GEN:CRYO"
RED = (200, 30, 30)
RED_LIGHT = (245, 205, 205)
AMBER_LIGHT = (255, 235, 200)
GREEN_LIGHT = (215, 240, 215)


# ------------------------------------------------------------------ control widgets
def command(text, pv, x, y, w, h=30, confirm=None, bg=None, size=11, bold=False, name=None, fg=None):
    """A button that writes 1 to an Action PV, optionally after a confirmation."""
    conf = (f"<show_confirm_dialog>true</show_confirm_dialog>"
            f"<confirm_message>{escape(confirm)}</confirm_message>") if confirm else ""
    back = f"<background_color>{pan.col(bg)}</background_color>" if bg else ""
    back += f"<foreground_color>{pan.col(fg)}</foreground_color>" if fg else ""
    return (f'<widget type="action_button" version="3.0.0"><name>{name or pan._name("Cmd")}</name>'
            f"<x>{x}</x><y>{y}</y><width>{w}</width><height>{h}</height>"
            f'<actions><action type="write_pv"><pv_name>ca://{pv}</pv_name><value>1</value>'
            f"<description>{escape(text)}</description></action></actions>"
            f"<text>{escape(text)}</text>{pan.font(size, bold)}{back}{conf}</widget>")


def entry(pv, x, y, w, h=26, name=None, tooltip=""):
    tip = f"<tooltip>{escape(tooltip)}</tooltip>" if tooltip else ""
    return (f'<widget type="textentry" version="3.0.0"><name>{name or pan._name("Entry")}</name>'
            f"<pv_name>ca://{pv}</pv_name><x>{x}</x><y>{y}</y><width>{w}</width><height>{h}</height>"
            f"{pan.font(11, True)}<background_color>{pan.col(pan.WHITE)}</background_color>{tip}</widget>")


def combo(pv, x, y, w, h=26, name=None, confirm=True):
    return (f'<widget type="combo" version="2.0.0"><name>{name or pan._name("Combo")}</name>'
            f"<pv_name>ca://{pv}</pv_name><x>{x}</x><y>{y}</y><width>{w}</width><height>{h}</height>"
            f"<items_from_pv>true</items_from_pv><confirm>{str(confirm).lower()}</confirm></widget>")


def progress(pv, x, y, w, h=18, name=None):
    return (f'<widget type="progressbar" version="2.0.0"><name>{name or pan._name("Bar")}</name>'
            f"<pv_name>ca://{pv}</pv_name><x>{x}</x><y>{y}</y><width>{w}</width><height>{h}</height>"
            f"<limits_from_pv>false</limits_from_pv><minimum>0.0</minimum><maximum>100.0</maximum>"
            f"</widget>")


def fld(caption, pv, x, y, w, size=11, prec=None, fmt=None, bold=True):
    return pan.field(caption, pv, x, y, w, size, prec=prec, fmt=fmt, bold=bold)


# ------------------------------------------------------------------ panels
def header():
    w = [pan.rect(0, 0, W, 44, pan.NAVY_DARK, name="Header"),
         pan.label("UNH Genesis - Magnet (IPS120-10)", 14, 2, 520, 26, 18, True, pan.WHITE, name="Title"),
         pan.label("AMI magnet power supply.  Moves need the cryogenics running (permit below).",
                   15, 26, 620, 16, 9, False, pan.WHITE)]
    w.append(pan.label("Supply", 700, 4, 60, 16, 9, False, pan.WHITE))
    w.append(pan.led(f"{MAG}:COMM", 700, 21, 18))
    w.append(pan.update(f"{MAG}:COMM", 722, 19, 110, 22, 10, True))
    w.append(pan.label("Writes", 840, 4, 60, 16, 9, False, pan.WHITE))
    w.append(pan.update(f"{MAG}:WRITE_ENABLED", 840, 19, 130, 22, 10, True, name="WriteEnabled"))
    w.append(pan.label("System checks", 980, 4, 120, 16, 9, False, pan.WHITE))
    w.append(pan.update(f"{MAG}:SYSTEM_CHECK_STATE", 980, 19, 250, 22, 10, True, name="SystemCheck"))
    w.append(pan.open_button("Panopticon", "genesis_panopticon.bob", 1238, 8, 90, 28))
    w.append(pan.open_button("Cryo", "genesis_cryo.bob", 1334, 8, 58, 28))
    return w


def magnet_card():
    x, y = 8, 52
    w = [pan.card("Magnet", x, y, 440, 230, "Magnet")]
    w.append(pan.label("Field (NMR-measured equation)", 18, 84, 280, 16, 9, False, pan.MUTED))
    w.append(pan.update(f"{MAG}:FIELD", 18, 100, 260, 44, 26, True, prec=5, name="Field"))
    w.append(fld("Magnet current", f"{MAG}:MAGNET_CURRENT", 290, 84, 150, 12, prec=4))
    w.append(fld("Field from", f"{MAG}:FIELD_SOURCE", 290, 124, 150, 10, bold=False))
    w.append(fld("Deuteron NMR", f"{MAG}:NMR_D", 18, 162, 135, 11, prec=4))
    w.append(fld("Proton NMR", f"{MAG}:NMR_P", 160, 162, 135, 11, prec=3))
    w.append(fld("Persistent current", f"{MAG}:PERSISTENT_CURRENT", 302, 162, 138, 11, prec=4))
    w.append(pan.label("B = slope x I + offset:", 18, 204, 150, 18, 9, False, pan.MUTED))
    w.append(pan.update(f"{MAG}:FIELD_SLOPE", 170, 204, 120, 18, 9, False, prec=7))
    w.append(pan.update(f"{MAG}:FIELD_OFFSET", 296, 204, 140, 18, 9, False, prec=8))
    w.append(pan.label("Quench", 18, 232, 60, 16, 9, False, pan.MUTED))
    w.append(pan.led(f"{MAG}:QUENCH", 18, 250, 20))
    w.append(pan.update(f"{MAG}:SYSTEM", 44, 248, 200, 24, 11, True, name="System"))
    w.append(fld("Trip current", f"{MAG}:TRIP_CURRENT", 250, 232, 90, 10, prec=3, bold=False))
    w.append(fld("Fringe (LS455)", f"{MAG}:FRINGE_FIELD_G", 346, 232, 94, 10, prec=2, bold=False))
    return w


def supply_card():
    x, y = 8, 288
    w = [pan.card("Supply", x, y, 440, 268, "Supply")]
    rows = (("Demand current (R0)", "CURRENT", 4), ("Measured current (R2)", "CURRENT_MEAS", 4),
            ("Voltage (R1)", "VOLTAGE", 4), ("Set point (R5)", "SETPOINT", 4),
            ("Sweep rate (R6)", "SWEEP_RATE", 3))
    for i, (cap, pv, prec) in enumerate(rows):
        w.append(fld(cap, f"{MAG}:{pv}", 18 + (i % 2) * 214, 318 + (i // 2) * 42, 200, 11, prec=prec))
    for i, (cap, pv) in enumerate((("Activity", "ACTIVITY"), ("Control", "CONTROL"),
                                   ("Heater", "HEATER"), ("Motion", "MOTION"), ("Limits", "LIMITS"))):
        w.append(fld(cap, f"{MAG}:{pv}", 18 + (i % 2) * 214, 444 + (i // 2) * 36, 200, 10, bold=False))
    w.append(fld("Status word", f"{MAG}:STATUS", 232, 516, 200, 10, bold=False))
    w.append(fld("Supply - persistent", f"{MAG}:CURRENT_DIFFERENCE", 232, 402, 200, 11, prec=4))
    return w


def settings_card():
    x, y = 8, 562
    w = [pan.card("Supply settings (checked before every ramp)", x, y, 440, 290, "Settings")]
    rows = (("Inductance R24 (38 H)", "INDUCTANCE", 2), ("Inductance seen ramping", "INDUCTANCE_MEAS", 1),
            ("Heater current R20 (40 mA)", "HEATER_MA", 1), ("Lead resistance R23", "LEAD_RES", 2),
            ("Safe limit, negative R21", "SAFE_NEG", 3), ("Safe limit, positive R22", "SAFE_POS", 3))
    for i, (cap, pv, prec) in enumerate(rows):
        w.append(fld(cap, f"{MAG}:{pv}", 18 + (i % 2) * 214, 594 + (i // 2) * 42, 200, 11, prec=prec))
    w.append(fld("Inductance check (38 +/- 0.3 H)", f"{MAG}:INDUCTANCE_CHECK", 18, 720, 200, 10))
    w.append(pan.label("R24 check", 232, 720, 200, 15, 9, False, pan.MUTED))
    w.append(combo(f"{MAG}:IGNORE_INDUCTANCE", 232, 735, 200, name="IgnoreInductance"))
    w.append(fld("Last event", f"{MAG}:LAST_EVENT", 18, 768, 414, 10, bold=False))
    w.append(fld("Supply / communication", f"{MAG}:VERSION", 18, 810, 200, 10, bold=False))
    w.append(pan.update(f"{MAG}:ERROR", 232, 825, 200, 21, 10, False))
    return w


def ramp_card():
    x, y = 456, 52
    w = [pan.card("Ramp", x, y, 460, 300, "Ramp")]
    # Elena Long (2026-11-06): current, field or NMR frequency; typing any one
    # fills in the other two (the IOC converts)
    w.append(pan.label("Target current (A)", 466, 84, 142, 16, 9, False, pan.MUTED))
    w.append(entry(f"{MAG}:TARGET_CURRENT", 466, 100, 142, name="TargetCurrent",
                   tooltip="0 to just under the software limit, to 0.1 mA (the IPS120's finest "
                           "step); a 0.1 mA digit switches the supply to 0.1 mA steps"))
    w.append(pan.label("or target field (T)", 612, 84, 142, 16, 9, False, pan.MUTED))
    w.append(entry(f"{MAG}:TARGET_FIELD", 612, 100, 142, name="TargetField",
                   tooltip="sets the target current by the field equation"))
    nucleus = pan.update(f"{MAG}:TARGET_NUCLEUS", 758, 84, 148, 16, 9, False, fg=pan.MUTED,
                         name="TargetNucleus")
    w.append(nucleus.replace("</widget>", "<transparent>true</transparent></widget>"))
    w.append(entry(f"{MAG}:TARGET_NMR", 758, 100, 148, name="TargetNMR",
                   tooltip="the target's NMR frequency: the deuteron, or the proton for NH3, "
                           "as the target material on the Cryo Safety screen; sets the field "
                           "and the current"))
    # Elena Long (2026-11-04): RAMP no longer asks (during field trims the
    # pop-up came up on every press); the IOC's checks, the 3 A/min cap and
    # HOLD are unchanged, and a change too small to send is reported in State
    w.append(command("RAMP to target", f"{MAG}:RAMP", 466, 140, 200, 40,
                     bg=AMBER_LIGHT, size=12, bold=True, name="RampButton"))
    w.append(command("HOLD", f"{MAG}:HOLD", 680, 140, 200, 40, bg=RED_LIGHT, size=14, bold=True,
                     name="HoldButton"))
    w.append(pan.label("RAMP and HOLD act at once (no pop-up).", 680, 184, 230, 16, 8, False, pan.MUTED))
    w.append(fld("State", f"{MAG}:STATE", 466, 212, 440, 12))
    w.append(fld("Operation", f"{MAG}:OPERATION", 466, 254, 214, 11, bold=False))
    w.append(pan.label("Busy", 690, 254, 60, 15, 9, False, pan.MUTED))
    w.append(pan.led(f"{MAG}:BUSY", 690, 274, 18))
    w.append(fld("Supply step", f"{MAG}:RESOLUTION", 740, 254, 166, 10, bold=False))
    w.append(pan.label("3 A/min, never faster.  Smallest change 0.1 mA: a target with a 0.1 mA "
                       "digit switches the supply to 0.1 mA steps first; finer is refused.  Ramps "
                       "only in driven mode: from persistent, MATCH, then heater ON (H1), then RAMP.",
                       466, 300, 440, 46, 9, False, pan.MUTED, wrap=True))
    return w


def heater_card():
    x, y = 456, 358
    w = [pan.card("Switch heater", x, y, 460, 198, "Heater")]
    w.append(pan.label("Heater", 466, 390, 60, 15, 9, False, pan.MUTED))
    w.append(pan.led(f"{MAG}:HEATER_ON", 466, 408, 22))
    w.append(pan.update(f"{MAG}:HEATER_ON", 494, 406, 160, 26, 12, True, name="HeaterState"))
    w.append(pan.label("R20 verification", 664, 390, 240, 15, 9, False, pan.MUTED))
    w.append(pan.update(f"{MAG}:HEATER_CURRENT_STATE", 664, 406, 240, 26, 10, True,
                        name="HeaterVerify"))
    w.append(command("Heater ON (driven)", f"{MAG}:HEATER_ON_CMD", 466, 446, 214, 32,
                     confirm="Open the superconducting switch (H1)? The supply is matched to the "
                             "persistent current first; 20 s wait.", name="HeaterOnButton"))
    w.append(command("Heater OFF (persistent)", f"{MAG}:HEATER_OFF_CMD", 690, 446, 214, 32,
                     confirm="Close the superconducting switch and make the magnet persistent? "
                             "20 s wait; the supply stays energized (this cool-down).",
                     name="HeaterOffButton"))
    w.append(command("Match supply to magnet", f"{MAG}:MATCH", 466, 486, 214, 28,
                     confirm="Bring the supply to the persistent current (switch closed)?",
                     name="MatchButton"))
    w.append(pan.label("ON wait (20 s)", 690, 482, 100, 14, 8, False, pan.MUTED))
    w.append(progress(f"{MAG}:HEATER_PROGRESS", 790, 482, 114, 14, name="HeaterProgress"))
    w.append(pan.label("OFF wait (20 s)", 690, 500, 100, 14, 8, False, pan.MUTED))
    w.append(progress(f"{MAG}:HEATER_OFF_PROGRESS", 790, 500, 114, 14, name="HeaterOffProgress"))
    w.append(pan.label("R20 reads", 466, 520, 70, 16, 9, False, pan.MUTED))
    w.append(pan.update(f"{MAG}:R20_MEANING", 536, 518, 150, 20, 9, False))
    w.append(pan.update(f"{MAG}:HEATER_MA", 690, 518, 214, 20, 9, False, prec=2))
    return w


def permit_card():
    x, y = 456, 562
    w = [pan.card("Cryogenics permit", x, y, 460, 290, "Permit")]
    w.append(pan.label("Magnet moves allowed", 466, 594, 200, 15, 9, False, pan.MUTED))
    w.append(pan.led(f"{MAG}:PERMIT", 466, 612, 22))
    w.append(pan.update(f"{MAG}:PERMIT", 494, 610, 140, 26, 12, True, name="PermitState"))
    w.append(fld("Reason", f"{MAG}:PERMIT_REASON", 466, 646, 440, 11))
    w.append(fld("Magnet LHe (AMI 135)", f"{MAG}:HELIUM_LEVEL", 466, 692, 140, 12, prec=1))
    w.append(fld("M4 (K)", f"{CRYO}:MAG:M4_TI", 616, 692, 140, 12, prec=3))
    w.append(fld("M5 (K)", f"{CRYO}:MAG:M5_TI", 766, 692, 140, 12, prec=3))
    w.append(fld("Shells vacuum (Torr)", f"{CRYO}:ION:Ion_PI", 466, 736, 200, 12, prec=2, fmt=2))
    w.append(pan.label("LHe floor: 20 in (Expert: 16 in)", 680, 736, 226, 16, 9, False, pan.MUTED))
    w.append(pan.label("Mode", 680, 754, 60, 15, 9, False, pan.MUTED))
    w.append(combo(f"{MAG}:EXPERT", 740, 752, 166, name="ExpertMode"))
    w.append(pan.update(f"{MAG}:HELIUM_LOW_WARNING", 466, 790, 200, 24, 11, True, name="HeliumWarning"))
    w.append(pan.label("HOLD, heater OFF and the outage button never need the permit or the "
                       "inductance check.", 466, 818, 440, 30, 9, False, pan.MUTED, wrap=True))
    return w


#: Elena Long (2026-11-04): the field and current trends open on the last 30 min
#: (a 0-48 A ramp at 3 A/min takes 16 min); zoom out with the plot toolbar to the
#: 2 h the trend history keeps (configs/target_physical/trend_history).
TREND_SPAN_MIN = 30


def outage_and_trend():
    x, y = 924, 52
    w = [pan.card("Power outage", x, y, 468, 150, "Outage")]
    w.append(command("POWER OUTAGE: make the magnet safe", f"{MAG}:OUTAGE", 934, 84, 448, 70,
                     confirm="Power outage procedure: HOLD, make the magnet persistent (heater off, "
                             "20 s). Continue?", bg=RED, fg=pan.WHITE, size=15, bold=True, name="OutageButton"))
    w.append(pan.label("For an outage that is coming or on backup power: once the power is gone "
                       "the IOC is gone too.", 934, 160, 448, 36, 9, False, pan.MUTED, wrap=True))
    w.append(pan.card("Field trend and fringe calibration", x, 208, 468, 644, "Trend"))
    w.append(pan.history_plot("MagnetField", "Magnet field (T)", 932, 238, 452, 300, "MAGNET",
                              [("Field", "FIELD", pan.NAVY, 0)], [("T", False, 0, 7)], TREND_SPAN_MIN))
    w.extend(fringe_calibration(932, 544))
    return w


def fringe_plot(x, y, w, h):
    """Magnet field (x) against the fringe gaussmeter (y): the chart's points
    and, after Fit, the fitted line (magnet_ioc/fringe_cal.py)."""
    small = '<font family="Liberation Sans" style="REGULAR" size="9.0"/>'
    fonts = f"<title_font>{small}</title_font><scale_font>{small}</scale_font>"

    def axis(tag, title):
        return (f"<{tag}><title>{escape(title)}</title><autoscale>true</autoscale>"
                f"<log_scale>false</log_scale><minimum>0.0</minimum><maximum>1.0</maximum>"
                f"<show_grid>true</show_grid>{fonts}<visible>true</visible></{tag}>")

    def trace(name, xs, ys, rgb, kind, point, size):
        return (f"<trace><name>{name}</name><x_pv>ca://{MAG}:{xs}</x_pv><y_pv>ca://{MAG}:{ys}</y_pv>"
                f"<axis>0</axis><trace_type>{kind}</trace_type><color>{pan.col(rgb)}</color>"
                f"<line_width>2</line_width><point_type>{point}</point_type>"
                f"<point_size>{size}</point_size><visible>true</visible></trace>")
    traces = (trace("Points", "CAL_FIELD", "CAL_FRINGE", pan.NAVY, 0, 2, 4)
              + trace("Fit", "CAL_LINE_FIELD", "CAL_LINE_FRINGE", (230, 110, 0), 1, 0, 1))
    return (f'<widget type="xyplot" version="3.0.0"><name>FringeCalibrationPlot</name>'
            f"<x>{x}</x><y>{y}</y><width>{w}</width><height>{h}</height>"
            f"<title>Fringe field vs magnet field</title>"
            f'<title_font><font family="Liberation Sans" style="BOLD" size="10.0"/></title_font>'
            f"<show_toolbar>true</show_toolbar><show_legend>false</show_legend>"
            f"{axis('x_axis', 'Magnet field (T)')}<y_axes>{axis('y_axis', 'Fringe field (G)')}</y_axes>"
            f"<traces>{traces}</traces></widget>")


def fringe_calibration(x, y):
    """Elena Long (2026-11-06, Ells): in place of the supply-current trend, the
    magnet field against the fringe field, with Clear chart and Fit (a line
    for B_magnet from B_fringe)."""
    w = [fringe_plot(x, y, 452, 236)]
    w.append(command("Clear chart", f"{MAG}:CAL_CLEAR", x, y + 242, 104, 28, name="CalClearButton",
                     confirm="Clear the fringe calibration chart?  Its points stay saved in the "
                             "magnet event folder; new points start a new file."))
    w.append(command("Fit", f"{MAG}:CAL_FIT", x + 110, y + 242, 70, 28, bg=GREEN_LIGHT, bold=True,
                     name="CalFitButton"))
    w.append(pan.update(f"{MAG}:CAL_EQUATION", x + 186, y + 242, 266, 28, 10, True, name="CalEquation"))
    w.append(pan.label("Points", x, y + 276, 44, 22, 9, False, pan.MUTED))
    w.append(pan.update(f"{MAG}:CAL_N", x + 44, y + 276, 56, 22, 10, False, name="CalN"))
    w.append(pan.label("rms", x + 110, y + 276, 30, 22, 9, False, pan.MUTED))
    w.append(pan.update(f"{MAG}:CAL_RMS", x + 140, y + 276, 110, 22, 10, False, prec=6, name="CalRms"))
    w.append(pan.label("Bf: fringe field in G.  A point every 2 mT of field change (or 5 min).",
                       x + 256, y + 272, 196, 30, 8, False, pan.MUTED, wrap=True))
    return w


def build() -> str:
    pan._n[0] = 0
    w = [pan.rect(0, 0, W, H, pan.WHITE, name="Page")]
    for part in (header, magnet_card, supply_card, settings_card, ramp_card, heater_card,
                 permit_card, outage_and_trend):
        w.extend(part())
    body = "\n  ".join(w)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<!-- Generated by tools/make_magnet_screen.py: edit the generator, not this file. -->\n"
            f'<display version="2.0.0">\n'
            f"  <name>Genesis Magnet</name>\n  <width>{W}</width>\n  <height>{H}</height>\n"
            f"  <background_color>{pan.col(pan.WHITE)}</background_color>\n  {body}\n</display>\n")


def main():
    OUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
