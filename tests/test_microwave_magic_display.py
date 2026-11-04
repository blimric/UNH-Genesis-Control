"""Magic +/- at the present field, shown in the Microwave tab's supervisor section
(Elena Long, 2026-11-04): factor (GHz/T, per dopant and material) x the magnet
IOC's field; 0 until a material and dopant with Magic constants are selected."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from cooldown_sim.testing import softioc_stub

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "configs/commissioning/microwave_physical/supervisor/settings.yaml"


class PV:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value, **_kw):
        self.value = value


def supervisor(dopant_name):
    with softioc_stub.installed():
        from logic_devices.microwave_supervisor.device import Device
    cfg = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))["microwave_supervisor"]
    names = [d["name"] for d in cfg["dopants"]]
    pvs = {k: PV() for k in ("MagicPlusGHz", "MagicMinusGHz", "MagicFieldT", "MagicStatus")}
    pvs["Dopant"] = PV(names.index(dopant_name))
    return Device, SimpleNamespace(dopants=cfg["dopants"], pvs=pvs), cfg


def test_settings_name_the_field():
    _, _, cfg = supervisor("None")
    assert cfg["field_pv"] == "UNH:GEN:MAG:FIELD"


def test_irradiated_d_butanol_at_5_tesla():
    Device, dev, _ = supervisor("Irradiated")
    Device.publish_magic(dev, "d-butanol", 5.0)
    assert dev.pvs["MagicPlusGHz"].value == pytest.approx(28.0236 * 5.0)       # 140.118
    assert dev.pvs["MagicMinusGHz"].value == pytest.approx(28.0438 * 5.0)      # 140.219
    assert "d-butanol" in dev.pvs["MagicStatus"].value


@pytest.mark.parametrize("dopant,material,field", [("None", "d-butanol", 5.0),
                                                    ("Irradiated", None, 5.0),
                                                    ("Irradiated", "d-propanediol", 5.0),
                                                    ("Irradiated", "d-butanol", float("nan"))])
def test_zero_until_material_dopant_and_field_are_known(dopant, material, field):
    Device, dev, _ = supervisor(dopant)
    Device.publish_magic(dev, material, field)
    assert dev.pvs["MagicPlusGHz"].value == 0.0 and dev.pvs["MagicMinusGHz"].value == 0.0


def test_the_microwave_tab_shows_them_beside_the_frequency_with_the_material_button():
    text = (ROOT / "gui" / "genesis_microwave.bob").read_text(encoding="utf-8")
    for pv in ("MagicPlusGHz", "MagicMinusGHz", "MagicStatus"):
        assert f"ca://UNH:GEN:MW:SUP:{pv}</pv_name>" in text
    button = re.search(r"<name>SUP_SetTargetMaterial</name>.*?</widget>", text, re.S).group(0)
    assert "<file>genesis_cryo_safety.bob</file>" in button
    assert (ROOT / "gui" / "genesis_cryo_safety.bob").exists()
