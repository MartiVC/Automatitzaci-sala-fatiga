"""Models de configuració de l'aplicació del PC LAB.

Defineix dataclasses tipades que reflecteixen l'estructura de ``config.yaml``.
La càrrega i validació es fan a :mod:`salafatiga.config.loader`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

Parity = Literal["N", "E", "O"]
VariadorMode = Literal["rtu", "sim_inproc"]
PlcMode = Literal["tcp", "sim_inproc"]


@dataclass(slots=True)
class AppConfig:
    nom_installacio: str = "Sala de fatiga"
    poll_period_s: float = 1.0


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    dir: Path = Path("logs")
    max_bytes: int = 5_000_000
    backup_count: int = 10


@dataclass(slots=True)
class EquipVariador:
    """Un equip (bomba) accessible a través del variador, a l'adreça @x del grup."""

    id: str
    addr: int  # adreça @0..@7 dins el grup de pressió
    descripcio: str = ""


@dataclass(slots=True)
class VariadorConfig:
    enabled: bool = True
    mode: VariadorMode = "rtu"
    port: str = "COM5"
    slave_id: int = 1
    baudrate: int = 9600
    parity: Parity = "N"
    bytesize: int = 8
    stopbits: int = 1
    timeout_s: float = 0.35
    poll_period_s: float = 1.0
    comm_lost_after: int = 3
    equips: list[EquipVariador] = field(default_factory=list)


@dataclass(slots=True)
class PlcConfig:
    enabled: bool = True
    mode: PlcMode = "tcp"
    host: str = "127.0.0.1"
    port: int = 5020
    unit_id: int = 1
    timeout_s: float = 1.0
    poll_period_s: float = 1.0


@dataclass(slots=True)
class StorageConfig:
    db_path: Path = Path("data/historic.sqlite")
    flush_period_s: float = 5.0
    retention_days: int = 0


@dataclass(slots=True)
class ExportConfig:
    dir: Path = Path("data/exports")
    default_format: str = "csv"


@dataclass(slots=True)
class WebConfig:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    # Confia en X-Forwarded-* del reverse proxy intern (subdomini + HTTPS).
    behind_proxy: bool = False
    # IPs o CIDRs autoritzats com a proxy ("*" per permetre qualsevol).
    forwarded_allow_ips: str = "127.0.0.1"


@dataclass(slots=True)
class OracleConfig:
    """Connexió al servidor Oracle corporatiu."""

    enabled: bool = False
    # Connexió directa (sense wallet): host + port + service_name.
    host: Optional[str] = None
    port: int = 1521
    service_name: Optional[str] = None
    # Credencials. En desplegament real es recomana llegir-les d'una variable
    # d'entorn (ORACLE_PASSWORD) i no escriure-les al config.yaml.
    user: str = ""
    password: str = ""
    # Connexió amb wallet (mTLS): cal indicar el directori del wallet i,
    # opcionalment, la seva contrasenya i l'àlias TNS (dsn).
    wallet_dir: Optional[Path] = None
    wallet_password: Optional[str] = None
    dsn: Optional[str] = None
    # Pool de connexions.
    pool_min: int = 1
    pool_max: int = 4
    # Si True, intenta crear l'esquema/taules a l'arrencada (idempotent).
    auto_create_schema: bool = True


@dataclass(slots=True)
class SyncConfig:
    """Paràmetres del servei de push SQLite → Oracle."""

    enabled: bool = False
    push_period_s: float = 30.0
    batch_size: int = 1000
    backoff_max_s: float = 300.0
    # Dies de retenció del buffer local un cop les files són a Oracle.
    # 0 = no purgar mai (el SQLite creixerà indefinidament).
    retention_local_days: int = 7
    retention_check_period_s: float = 3600.0


@dataclass(slots=True)
class UiConfig:
    chart_window_s: int = 120
    equip_per_defecte: Optional[str] = None


@dataclass(slots=True)
class Config:
    """Configuració completa de l'aplicació."""

    app: AppConfig = field(default_factory=AppConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    variador: VariadorConfig = field(default_factory=VariadorConfig)
    plc: PlcConfig = field(default_factory=PlcConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    web: WebConfig = field(default_factory=WebConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    oracle: OracleConfig = field(default_factory=OracleConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    # Ruta del fitxer des d'on s'ha carregat (informativa).
    source_path: Optional[Path] = None

    def equip_addr(self, equip_id: str) -> int:
        """Adreça @x del grup per a un equip pel seu id; KeyError si no existeix."""
        for e in self.variador.equips:
            if e.id == equip_id:
                return e.addr
        raise KeyError(f"Equip desconegut: {equip_id!r}")
