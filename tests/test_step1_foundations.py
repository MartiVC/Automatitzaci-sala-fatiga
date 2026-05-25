"""Tests bàsics dels fonaments (pas 1): configuració, model de dades, catàleg de
variables i mapa de registres del SPEEDRIVE V2.

Executar des de l'arrel del repositori:  pytest
"""
from __future__ import annotations

from pathlib import Path

import pytest

from salafatiga.acquisition.variador import registers as reg
from salafatiga.config import ConfigError, load_config
from salafatiga.core import datamodel as dm
from salafatiga.core import variables as cat

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
#  Configuració
# --------------------------------------------------------------------------- #
def test_load_example_config():
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    assert cfg.variador.baudrate == 9600
    assert cfg.variador.mode in ("rtu", "sim_inproc")
    assert cfg.variador.parity == "N"
    assert {e.id for e in cfg.variador.equips} == {"GRUP1_B1", "GRUP2_B1"}
    assert cfg.equip_addr("GRUP1_B1") == 0
    assert cfg.plc.mode in ("tcp", "sim_inproc")


def test_config_rejects_bad_equip_addr():
    bad = ROOT / "tests" / "fixtures" / "bad_config_addr.yaml"
    with pytest.raises(ConfigError):
        load_config(bad)


def test_config_missing_file():
    with pytest.raises(ConfigError):
        load_config("no/such/file.yaml")


# --------------------------------------------------------------------------- #
#  Model de dades
# --------------------------------------------------------------------------- #
def test_reading_now_and_usable():
    r = dm.Reading.now("GRUP1_B1", dm.Origin.VARIADOR, cat.V_INTENSITAT, 12.3, unit="A")
    assert r.is_usable
    assert r.value == 12.3 and r.unit == "A"
    bad = dm.Reading.now("GRUP1_B1", dm.Origin.VARIADOR, cat.V_INTENSITAT, None,
                         quality=dm.Quality.BAD)
    assert not bad.is_usable


def test_event_now():
    e = dm.Event.now(dm.SISTEMA_EQUIP_ID, dm.Origin.SISTEMA, dm.EventType.SYSTEM,
                     dm.Severity.INFO, "START", "Arrencada")
    assert e.equip_id == "SISTEMA" and e.severity == dm.Severity.INFO


# --------------------------------------------------------------------------- #
#  Catàleg de variables
# --------------------------------------------------------------------------- #
def test_variable_catalog():
    v = cat.get(cat.V_PRESSIO)
    assert v.origin is dm.Origin.VARIADOR and v.unit == "bar"
    assert v.to_eng(10) == 10.0  # scale=1, offset=0 per defecte
    assert all(d.origin is dm.Origin.PLC for d in cat.by_origin(dm.Origin.PLC))
    with pytest.raises(KeyError):
        cat.get("no_existeix")


# --------------------------------------------------------------------------- #
#  Mapa de registres del SPEEDRIVE V2
# --------------------------------------------------------------------------- #
def test_address_conversion():
    # Exemple del document: 30007 -> offset 6, funció 04
    assert reg.addr_of(30007) == 6
    assert reg.function_of(30007) == 4
    # Coils i discrete inputs
    assert reg.addr_of(reg.COIL_LED_FAULT) == 0 and reg.function_of(1) == 1
    assert reg.addr_of(10010) == 9 and reg.function_of(10010) == 2
    with pytest.raises(ValueError):
        reg.addr_of(20000)


def test_per_equip_registers():
    assert reg.reg_intensitat(0) == 30013 and reg.reg_pressio(0) == 30014
    assert reg.reg_hz_motor(0) == 30029
    assert reg.reg_intensitat(7) == 30027 and reg.reg_pressio(7) == 30028
    assert reg.reg_hz_motor(7) == 30036
    assert reg.reg_alarma_equip(0) == 10021 and reg.reg_auto_manual(0) == 10022
    assert reg.reg_bus485_nok(0) == 10023 and reg.reg_alarma_equip(7) == 10042
    rs = reg.EquipRegisterSet(3)
    assert rs.intensitat == 30019 and rs.hz_motor == 30032 and rs.alarma == 10030
    with pytest.raises(ValueError):
        reg.reg_intensitat(8)


def test_alarm_text():
    assert reg.alarm_text(0) == "Sense alarma"
    assert "sec" in reg.alarm_text(33).lower()
    assert "desconeguda" in reg.alarm_text(99).lower()
