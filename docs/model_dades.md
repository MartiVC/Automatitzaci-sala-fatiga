# Model de dades comú

Tota dada que entra al PC LAB (del variador, del PLC o del propi sistema) es
normalitza immediatament a un d'aquests dos tipus, definits a
`salafatiga/core/datamodel.py`:

- **`Reading`** — una mesura puntual d'una variable d'un equip (sèrie temporal).
- **`Event`** — un esdeveniment puntual (alarma, canvi d'estat, incidència de comunicació).

El catàleg de variables (`salafatiga/core/variables.py`) defineix, per a cada
variable, l'origen previst, la unitat, la conversió raw→enginyeria i els límits.

## `Reading`

| Camp | Tipus | Descripció |
|---|---|---|
| `ts` | float | Marca temporal UNIX (segons, UTC) |
| `equip_id` | str | Identificador de l'equip/bomba (p. ex. `GRUP1_B1`) |
| `origin` | `Origin` | `VARIADOR` \| `PLC` \| `SISTEMA` |
| `variable_id` | str | Id de la variable al catàleg (p. ex. `intensitat`) |
| `value` | float \| None | Valor en unitats d'enginyeria; `None` si la lectura ha fallat |
| `unit` | str | Unitat (`A`, `bar`, `Hz`, `°C`, `mm/s`, `rpm`, ...) |
| `quality` | `Quality` | `GOOD` \| `UNCERTAIN` \| `STALE` \| `BAD` |
| `raw` | int \| None | Valor cru llegit del dispositiu (registre Modbus), si escau |
| `status_code` | int \| None | Codi d'estat/alarma associat (p. ex. valor del registre 30049), si escau |
| `note` | str | Text lliure (motiu de qualitat dolenta, etc.) |

Cobreix els camps mínims demanats al plec: *timestamp, equip/bomba, origen de la
dada, variable, valor, unitat, qualitat de dada / estat de comunicació, codi
d'alarma o estat si aplica*.

## `Event`

| Camp | Tipus | Descripció |
|---|---|---|
| `ts` | float | Marca temporal UNIX (segons, UTC) |
| `equip_id` | str | Equip afectat, o `SISTEMA` per esdeveniments globals |
| `origin` | `Origin` | `VARIADOR` \| `PLC` \| `SISTEMA` |
| `type` | `EventType` | `ALARM_SET` \| `ALARM_CLEAR` \| `WARNING_SET` \| `WARNING_CLEAR` \| `STATE_CHANGE` \| `COMM_LOST` \| `COMM_RESTORED` \| `SYSTEM` |
| `severity` | `Severity` | `INFO` \| `WARNING` \| `ALARM` \| `CRITICAL` |
| `code` | str | Codi intern de l'esdeveniment/alarma |
| `message` | str | Descripció llegible |
| `variable_id` | str \| None | Variable relacionada, si escau |
| `value` | float \| None | Valor que ha disparat l'esdeveniment, si escau |

## Catàleg de variables (estat inicial)

| `variable_id` | Nom | Origen | Tipus | Unitat | Notes |
|---|---|---|---|---|---|
| `freq_hz` | Freqüència motor | variador | analògica | Hz | registre 30029 + ADDRx |
| `intensitat` | Intensitat motor | variador | analògica | A | registre 30013 + 2·ADDRx |
| `pressio` | Pressió | variador | analògica | bar | registre 30014 + 2·ADDRx |
| `alarma_codi` | Codi d'alarma del variador | variador | codi | — | registre 30049 (0=cap, 17..41=codi) |
| `estat_alarma` | Equip en alarma | variador | digital | — | ALARMA_ADDRx |
| `estat_auto_manual` | Mode automàtic/manual | variador | digital | — | AUTO_ADDRx |
| `comm_485_nok` | Sense comunicació RS-485 (equip) | variador | digital | — | BUS_485_ADDx (1 = no comunica) |
| `t_rodament_de` | Temp. rodament DE | PLC | analògica | °C | avís 80 / alarma 95 (orientatiu) |
| `t_rodament_nde` | Temp. rodament NDE | PLC | analògica | °C | avís 80 / alarma 95 (orientatiu) |
| `t_motor` | Temp. motor | PLC | analògica | °C | avís 90 / alarma 110 (orientatiu) |
| `t_fluid` | Temp. fluid | PLC | analògica | °C | avís 60 / alarma 80 (orientatiu) |
| `t_ambient` | Temp. ambient | PLC | analògica | °C | — |
| `vib_de` | Vibració DE (RMS) | PLC | analògica | mm/s | avís 4,5 / alarma 7,1 (ref. ISO 10816, orientatiu) |
| `vib_nde` | Vibració NDE (RMS) | PLC | analògica | mm/s | avís 4,5 / alarma 7,1 (ref. ISO 10816, orientatiu) |
| `rpm_motor` | RPM motor | PLC | analògica | rpm | — |
| `comm_variador` | Comunicació variador | sistema | digital | — | 1 = OK |
| `comm_plc` | Comunicació PLC | sistema | digital | — | 1 = OK |

> Els llindars d'avís/alarma són valors **inicials**; s'han d'afinar amb dades
> reals i amb la potència de cada bomba (2 / 3 / 5,5 / 7,5 HP segons el plec).

## Esquema de la base de dades (SQLite) — *pas 2 implementat*

Esquema implementat a `salafatiga/storage/schema.sql`:

```sql
-- Catàleg estàtic d'equips i variables (per integritat referencial i metadades)
CREATE TABLE devices  (id TEXT PRIMARY KEY, descripcio TEXT, addr INTEGER);
CREATE TABLE variables (id TEXT PRIMARY KEY, nom TEXT, origin TEXT, kind TEXT, unit TEXT);

-- Sèries temporals (mesures)
CREATE TABLE measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,          -- UNIX time (s, UTC)
    equip_id    TEXT    NOT NULL,
    origin      TEXT    NOT NULL,           -- variador | plc | sistema
    variable_id TEXT    NOT NULL,
    value       REAL,                       -- NULL si lectura fallida
    unit        TEXT    NOT NULL,
    quality     TEXT    NOT NULL,           -- good | uncertain | stale | bad
    raw         INTEGER,
    status_code INTEGER,
    note        TEXT    NOT NULL
);
CREATE INDEX idx_meas_ts        ON measurements (ts);
CREATE INDEX idx_meas_eq_var_ts ON measurements (equip_id, variable_id, ts);

-- Esdeveniments / alarmes / estats
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL NOT NULL,
    equip_id    TEXT NOT NULL,
    origin      TEXT NOT NULL,
    type        TEXT NOT NULL,              -- alarm_set | alarm_clear | ...
    severity    INTEGER NOT NULL,           -- 0..3
    code        TEXT NOT NULL,
    message     TEXT NOT NULL,
    variable_id TEXT,
    value       REAL
);
CREATE INDEX idx_evt_ts ON events (ts);
```

> Extensió futura possible: una taula `sessions(id, equip_id, ts_inici, ts_fi, descripcio)`
> per agrupar i etiquetar períodes d'assaig de fatiga. Encara no està implementada
> (`storage/schema.sql` només crea `measurements`, `events` i els catàlegs `devices`/`variables`).
