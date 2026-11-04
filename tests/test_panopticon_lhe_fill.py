"""Panopticon insert drawing: the liquid helium fills (Elena Long, 2026-11-04).

The magnet space below its measured level, and the fridge below its highest
covered thermometer, are filled in two shades of blue, behind every other
detail (each fill sits right above its outline)."""

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOB = ROOT / "gui" / "genesis_panopticon.bob"


def widgets():
    return ET.parse(BOB).getroot().findall("widget")


def test_fills_sit_right_above_their_outlines_and_below_the_details():
    names = [w.findtext("name") for w in widgets()]
    for outline, fills in (("Magnet_LHe_Space", ("Magnet_LHe_Fill_Bore", "Magnet_LHe_Fill_Belly")),
                           ("Shape_Fridge_Can", ("Fridge_LHe_Fill",)),
                           ("Shape_Nose", ("Fridge_LHe_Fill_Nose",))):
        i = names.index(outline)
        assert names[i + 1:i + 1 + len(fills)] == list(fills), outline
    assert names.index("Magnet_LHe_Fill_Belly") < names.index("Magnet_LHe_Level") < names.index("Coil_L")
    assert names.index("Fridge_LHe_Fill") < names.index("Baffle_U1")


def test_magnet_fill_follows_the_level_and_the_fridge_fill_the_thermometers():
    by = {w.findtext("name"): w for w in widgets()}
    for n in ("Magnet_LHe_Fill_Bore", "Magnet_LHe_Fill_Belly"):
        pvs = {p.text for p in by[n].iter("pv_name")}
        assert pvs == {"ca://UNH:GEN:CRYO:MAG:LHE:Magnet_LI"}
        assert {r.get("prop_id") for r in by[n].iter("rule")} == {"y", "height", "visible"}
    script = by["Fridge_LHe_Fill"].find("scripts/script")
    pvs = [p.text for p in script.findall("pv_name")]
    assert pvs[0] == "ca://UNH:GEN:CRYO:VAC:LOW:Mano_VapT"
    assert "ca://UNH:GEN:CRYO:MAG:T1_TI" in pvs and "ca://UNH:GEN:CRYO:FRIDGE:F11_TI" in pvs
    shade = lambda n: tuple(by[n].find("background_color/color").get(k) for k in ("red", "green", "blue"))
    assert shade("Magnet_LHe_Fill_Bore") != shade("Fridge_LHe_Fill")
