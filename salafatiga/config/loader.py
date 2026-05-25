"""Càrrega i validació de la configuració des de YAML."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AppConfig,
    Config,
    EquipVariador,
    ExportConfig,
    LoggingConfig,
    OracleConfig,
    PlcConfig,
    StorageConfig,
    SyncConfig,
    UiConfig,
    VariadorConfig,
    WebConfig,
)

DEFAULT_CONFIG_PATH = Path("config/config.yaml")
EXAMPLE_CONFIG_PATH = Path("config/config.example.yaml")

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_PARITIES = {"N", "E", "O"}
_VARIADOR_MODES = {"rtu", "sim_inproc"}
_PLC_MODES = {"tcp", "sim_inproc"}


class ConfigError(Exception):
    """Error de configuració (fitxer inexistent, sintaxi incorrecta, camp invàlid...)."""


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _as_path(value: Any, default: Path) -> Path:
    return default if value is None else Path(str(value))


def _section(data: dict, name: str) -> dict:
    sec = data.get(name)
    if sec is None:
        return {}
    if not isinstance(sec, dict):
        raise ConfigError(f"La secció '{name}' ha de ser un mapping (clau: valor).")
    return sec


def _resolve_secret(value: Any) -> str:
    """Resol secrets ofuscats al config:

    - Cadena ``env:NOM_VAR``         → ``os.environ["NOM_VAR"]``
    - Cadena ``${NOM_VAR}``           → ``os.environ["NOM_VAR"]``
    - Qualsevol altra cosa             → es retorna tal qual (cast a str)

    Si la variable d'entorn no està definida es retorna cadena buida, no es
    llança excepció: la connexió Oracle ja la rebutjarà més tard amb un
    missatge específic, i així el config segueix sent carregable per a les
    altres parts del sistema.
    """
    if value is None:
        return ""
    s = str(value)
    if s.startswith("env:"):
        return os.environ.get(s[4:], "")
    if s.startswith("${") and s.endswith("}"):
        return os.environ.get(s[2:-1], "")
    return s


def _equips_from(var_section: dict) -> list[EquipVariador]:
    equips: list[EquipVariador] = []
    raw_list = var_section.get("equips") or []
    if not isinstance(raw_list, list):
        raise ConfigError("'variador.equips' ha de ser una llista.")
    for i, e in enumerate(raw_list):
        if not isinstance(e, dict) or "id" not in e or "addr" not in e:
            raise ConfigError(f"variador.equips[{i}]: cal un mapping amb 'id' i 'addr'.")
        try:
            addr = int(e["addr"])
        except (TypeError, ValueError):
            raise ConfigError(f"variador.equips[{i}].addr ha de ser un enter.") from None
        if not 0 <= addr <= 7:
            raise ConfigError(f"variador.equips[{i}].addr ha d'estar entre 0 i 7 (és {addr}).")
        equips.append(
            EquipVariador(id=str(e["id"]), addr=addr, descripcio=str(e.get("descripcio", "")))
        )
    return equips


# --------------------------------------------------------------------------- #
#  Construcció del model
# --------------------------------------------------------------------------- #
def _build(data: dict) -> Config:
    app_s = _section(data, "app")
    log_s = _section(data, "logging")
    var_s = _section(data, "variador")
    plc_s = _section(data, "plc")
    sto_s = _section(data, "storage")
    exp_s = _section(data, "export")
    web_s = _section(data, "web")
    ui_s = _section(data, "ui")
    ora_s = _section(data, "oracle")
    syn_s = _section(data, "sync")

    default_poll = float(app_s.get("poll_period_s", 1.0))

    cfg = Config(
        app=AppConfig(
            nom_installacio=str(app_s.get("nom_installacio", AppConfig.nom_installacio)),
            poll_period_s=default_poll,
        ),
        logging=LoggingConfig(
            level=str(log_s.get("level", "INFO")).upper(),
            dir=_as_path(log_s.get("dir"), Path("logs")),
            max_bytes=int(log_s.get("max_bytes", 5_000_000)),
            backup_count=int(log_s.get("backup_count", 10)),
        ),
        variador=VariadorConfig(
            enabled=bool(var_s.get("enabled", True)),
            mode=str(var_s.get("mode", "rtu")),
            port=str(var_s.get("port", "COM5")),
            slave_id=int(var_s.get("slave_id", 1)),
            baudrate=int(var_s.get("baudrate", 9600)),
            parity=str(var_s.get("parity", "N")).upper(),
            bytesize=int(var_s.get("bytesize", 8)),
            stopbits=int(var_s.get("stopbits", 1)),
            timeout_s=float(var_s.get("timeout_s", 0.35)),
            poll_period_s=float(var_s.get("poll_period_s", default_poll)),
            comm_lost_after=int(var_s.get("comm_lost_after", 3)),
            equips=_equips_from(var_s),
        ),
        plc=PlcConfig(
            enabled=bool(plc_s.get("enabled", True)),
            mode=str(plc_s.get("mode", "tcp")),
            host=str(plc_s.get("host", "127.0.0.1")),
            port=int(plc_s.get("port", 5020)),
            unit_id=int(plc_s.get("unit_id", 1)),
            timeout_s=float(plc_s.get("timeout_s", 1.0)),
            poll_period_s=float(plc_s.get("poll_period_s", default_poll)),
        ),
        storage=StorageConfig(
            db_path=_as_path(sto_s.get("db_path"), Path("data/historic.sqlite")),
            flush_period_s=float(sto_s.get("flush_period_s", 5.0)),
            retention_days=int(sto_s.get("retention_days", 0)),
        ),
        export=ExportConfig(
            dir=_as_path(exp_s.get("dir"), Path("data/exports")),
            default_format=str(exp_s.get("default_format", "csv")).lower(),
        ),
        web=WebConfig(
            enabled=bool(web_s.get("enabled", False)),
            host=str(web_s.get("host", "0.0.0.0")),
            port=int(web_s.get("port", 8000)),
            behind_proxy=bool(web_s.get("behind_proxy", False)),
            forwarded_allow_ips=str(web_s.get("forwarded_allow_ips", "127.0.0.1")),
        ),
        ui=UiConfig(
            chart_window_s=int(ui_s.get("chart_window_s", 120)),
            equip_per_defecte=(
                str(ui_s["equip_per_defecte"]) if ui_s.get("equip_per_defecte") else None
            ),
        ),
        oracle=OracleConfig(
            enabled=bool(ora_s.get("enabled", False)),
            host=(str(ora_s["host"]) if ora_s.get("host") else None),
            port=int(ora_s.get("port", 1521)),
            service_name=(
                str(ora_s["service_name"]) if ora_s.get("service_name") else None
            ),
            user=str(ora_s.get("user", "") or ""),
            password=_resolve_secret(ora_s.get("password", "")),
            wallet_dir=_as_path(ora_s.get("wallet_dir"), Path("")) if ora_s.get("wallet_dir") else None,
            wallet_password=_resolve_secret(ora_s.get("wallet_password")) or None,
            dsn=(str(ora_s["dsn"]) if ora_s.get("dsn") else None),
            pool_min=int(ora_s.get("pool_min", 1)),
            pool_max=int(ora_s.get("pool_max", 4)),
            auto_create_schema=bool(ora_s.get("auto_create_schema", True)),
        ),
        sync=SyncConfig(
            enabled=bool(syn_s.get("enabled", False)),
            push_period_s=float(syn_s.get("push_period_s", 30.0)),
            batch_size=int(syn_s.get("batch_size", 1000)),
            backoff_max_s=float(syn_s.get("backoff_max_s", 300.0)),
            retention_local_days=int(syn_s.get("retention_local_days", 7)),
            retention_check_period_s=float(syn_s.get("retention_check_period_s", 3600.0)),
        ),
    )
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.logging.level not in _LOG_LEVELS:
        raise ConfigError(f"logging.level invàlid: {cfg.logging.level!r} (opcions: {sorted(_LOG_LEVELS)}).")
    if cfg.variador.parity not in _PARITIES:
        raise ConfigError(f"variador.parity invàlid: {cfg.variador.parity!r} (opcions: N, E, O).")
    if cfg.variador.mode not in _VARIADOR_MODES:
        raise ConfigError(f"variador.mode invàlid: {cfg.variador.mode!r} (opcions: {sorted(_VARIADOR_MODES)}).")
    if cfg.plc.mode not in _PLC_MODES:
        raise ConfigError(f"plc.mode invàlid: {cfg.plc.mode!r} (opcions: {sorted(_PLC_MODES)}).")
    if cfg.export.default_format not in {"csv", "parquet"}:
        raise ConfigError(f"export.default_format invàlid: {cfg.export.default_format!r}.")
    if cfg.variador.enabled and not cfg.variador.equips:
        raise ConfigError("variador.enabled=true però 'variador.equips' és buit.")

    ids = [e.id for e in cfg.variador.equips]
    if len(ids) != len(set(ids)):
        raise ConfigError("Hi ha identificadors d'equip duplicats a 'variador.equips'.")
    addrs = [e.addr for e in cfg.variador.equips]
    if len(addrs) != len(set(addrs)):
        raise ConfigError("Hi ha adreces @x duplicades a 'variador.equips'.")

    if cfg.ui.equip_per_defecte and cfg.variador.enabled and cfg.ui.equip_per_defecte not in ids:
        raise ConfigError(
            f"ui.equip_per_defecte={cfg.ui.equip_per_defecte!r} no correspon a cap equip definit."
        )
    for name, port in (("plc.port", cfg.plc.port), ("web.port", cfg.web.port)):
        if not 1 <= port <= 65535:
            raise ConfigError(f"{name} fora de rang (1..65535): {port}.")

    if cfg.oracle.enabled:
        if not 1 <= cfg.oracle.port <= 65535:
            raise ConfigError(f"oracle.port fora de rang (1..65535): {cfg.oracle.port}.")
        if not cfg.oracle.user:
            raise ConfigError("oracle.enabled=true però falta 'oracle.user'.")
        if cfg.oracle.wallet_dir is None and not (cfg.oracle.host and cfg.oracle.service_name):
            raise ConfigError(
                "Cal definir 'oracle.host' + 'oracle.service_name', o bé 'oracle.wallet_dir'."
            )
        if cfg.oracle.pool_min < 1 or cfg.oracle.pool_max < cfg.oracle.pool_min:
            raise ConfigError("oracle.pool_min/max inconsistents (mín>=1 i max>=min).")

    if cfg.sync.enabled and not cfg.oracle.enabled:
        raise ConfigError("sync.enabled=true requereix oracle.enabled=true.")
    if cfg.sync.push_period_s <= 0:
        raise ConfigError("sync.push_period_s ha de ser > 0.")
    if cfg.sync.batch_size < 1:
        raise ConfigError("sync.batch_size ha de ser >= 1.")


# --------------------------------------------------------------------------- #
#  API pública
# --------------------------------------------------------------------------- #
def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Carrega la configuració des d'un fitxer YAML.

    Si ``path`` és ``None``, prova ``config/config.yaml`` i, si no existeix,
    recorre a ``config/config.example.yaml``. Llança :class:`ConfigError` si el
    fitxer no existeix, té sintaxi incorrecta o algun camp no és vàlid.
    """
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        if path is None and EXAMPLE_CONFIG_PATH.exists():
            p = EXAMPLE_CONFIG_PATH
        else:
            raise ConfigError(f"No s'ha trobat el fitxer de configuració: {p}")

    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Error de sintaxi YAML a {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"El fitxer {p} no conté un mapping a l'arrel.")

    cfg = _build(data)
    cfg.source_path = p
    return cfg
