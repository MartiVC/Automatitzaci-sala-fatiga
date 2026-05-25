# Arquitectura del sistema — PC LAB de la sala de fatiga

> Aquest document resumeix l'arquitectura del programari. Per al context, els
> requisits i els diagrames originals, vegeu a l'arrel del repositori:
> `0- plec de condicions_fatiga.pdf`, `Informe inicial.pdf`,
> `Informe de progrés 1 - 1637919.pdf`, `Protocol Modbus Speedrive_V2.pdf`,
> `capa fisica lab.drawio (1).png` i `capa dades.drawio.png`.

## 1. Context i abast

El **PC LAB** és l'ordinador del laboratori que actua com a **node central de
supervisió** de la sala de fatiga. Les seves funcions:

- Lectura periòdica del variador **SPEEDRIVE V2** per **Modbus RTU** (RS-485). Només lectura.
- Recepció de dades del **PLC** per **Modbus TCP** (el PLC concentra els sensors
  externs: temperatures, vibracions, rpm). El PC LAB **no** parla amb sensors.
- Marca temporal de cada lectura, validació bàsica i detecció d'errors de comunicació.
- Unificació de totes les variables en un **model de dades comú**.
- Visualització en temps real (aplicació Qt local).
- Registre històric (base de dades local).
- Gestió d'alarmes i esdeveniments.
- Exportació de dades.
- Publicació per a consulta remota (dashboard web), sense exposar els dispositius de camp.

Fora d'abast en aquesta fase: control o escriptura sobre els equips (l'escriptura
per Modbus RTU del variador, a més, està anul·lada pel fabricant).

## 2. Capa física (resum)

```
        PUMP (bomba centrífuga + variador SPEEDRIVE V2)
          │                              │
   Variador  ── Modbus RTU / RS-485 ──┐  └─ Sensors externs (T, vibració, rpm)
   (intensitat, pressió, Hz,          │                     │
    estats, alarmes)                  │              senyals de camp
                                      │                     │
                                      │                    PLC  (adquisició de sensors)
                                      │                     │
                                      ▼                     ▼  Modbus TCP / Ethernet
                              ┌───────────────────────────────────┐
                              │   PC LAB  (node de supervisió)     │
                              └───────────────────────────────────┘
                                      │ publicació / consulta
                              Gateway / Router / Firewall industrial
                                      │
                                  XARXA ESPA  ──►  PCs d'oficina (consulta d'històrics)
```

La xarxa és **segmentada**: el PC LAB queda a la xarxa local del laboratori amb
el PLC i el variador; l'accés des de la xarxa corporativa es fa a través del
gateway/firewall (i, en última instància, contra l'històric, no contra els
dispositius de camp).

## 3. Capes de programari i flux de dades

```
   ┌──────────────┐   ┌──────────────────────┐
   │  variador/   │   │  plc/                │   ← acquisition/
   │  (Modbus RTU)│   │  (Modbus TCP + sim)  │
   └──────┬───────┘   └──────────┬───────────┘
          │  Reading / Event     │
          └──────────┬───────────┘
                     ▼
            processing/  (validació, qualitat de dada)
                     │  Reading / Event (validats)
                     ▼
            services/bus  (bus de senyals)
            ┌────────┼─────────────┬───────────────┐
            ▼        ▼             ▼               ▼
        storage/  alarms/        ui/            (export/, remote/)
        (SQLite)  (regles,       (Qt: valors,    bolcats des de
                  esdeveniments) gràfiques,      l'històric
                                 alarmes,
                                 històric, config)
```

- **Adquisició** (`acquisition/`): cada font (variador, PLC) llegeix periòdicament
  i emet `Reading`/`Event` ja normalitzats. El PLC té una implementació real
  (Modbus TCP) i un **simulador** intercanviable.
- **Processament** (`processing/`): comprova rangs, salts impossibles i antiguitat;
  assigna la qualitat (`GOOD` / `UNCERTAIN` / `STALE` / `BAD`).
- **Bus de senyals** (`services/bus.py`): desacobla l'adquisició de la resta
  (Qt signals). El `services/acquisition_service.py` orquestra les fonts amb temporitzadors.
- **Emmagatzematge** (`storage/`): persistència estructurada en SQLite, separant
  **sèries temporals** (mesures) i **esdeveniments** (alarmes, estats, incidències).
- **Alarmes** (`alarms/`): catàleg d'alarmes (del variador + de sistema), motor de
  regles de llindar amb antirebot, i generació d'esdeveniments.
- **UI** (`ui/`): aplicació de supervisió Qt (PySide6, gràfiques pintades amb QPainter):
  valors actuals per equip, gràfiques en viu, estat de comunicació, alarmes actives,
  històric i opcions de configuració (port sèrie, freqüència de lectura, equip
  seleccionat, variables a visualitzar).
- **Exportació** (`export/`): bolcat a CSV (i Parquet opcional) d'un rang/equip.
- **Remot** (`remote/`): API + pàgina web que consulta l'històric (procés separat).

## 3.bis Buffer SQLite local + Oracle corporatiu

Per al desplegament real al PC LAB l'històric viu a la base de dades **Oracle
corporativa**, però el PC LAB no en depèn per funcionar: el SQLite continua
sent el primer destí d'escriptura i actua com a **buffer** davant talls de
xarxa amb Oracle.

```
   adquisició                escriptura immediata
   ───────────►   SQLite local   ────────────────►   OracleSyncService
                  (buffer +                            (thread; lots +
                  synced_at)                           backoff exponencial)
                       │                                       │
                       │                                       ▼
                       │                              Oracle corporatiu
                       │                              (font de veritat)
                       │                                       │
                       └───────── fallback ◄───── ReadFacade ──┘
                                                       │
                                                       ▼
                                            FastAPI / dashboard web
```

- **Escriptura** (UI Qt i fonts d'adquisició): sempre al SQLite local
  (`StorageRepository.add_*`). Cada fila duu un camp `synced_at` (NULL fins que
  el sync l'empeny a Oracle).
- **Sync** (`services/oracle_sync.py`): thread en background que, cada
  `sync.push_period_s` segons, llegeix lots de files amb `synced_at IS NULL`,
  els insereix a Oracle i marca el `synced_at`. Si Oracle no respon fa
  backoff exponencial fins a `sync.backoff_max_s`. Cada
  `sync.retention_check_period_s` purga del SQLite les files ja sincronitzades
  més antigues que `sync.retention_local_days`.
- **Lectura** (`storage/read_facade.py`): el dashboard consulta sempre a través
  de `ReadFacade`, que prova Oracle primer i, si falla, cau al SQLite local i
  marca `mode = "degraded"` durant un cooldown. Així la web mai queda cega.
- **Estat exposat**: `/api/health` retorna `storage_mode` (`remote` / `degraded`
  / `local`) i `storage_error`. La UI Qt i el dashboard pinten un badge "Oracle"
  amb aquest estat (verd / groc / gris).

## 4. Mòduls (mapa de paquets)

| Paquet | Responsabilitat | Estat |
|---|---|---|
| `salafatiga/config/` | Models de configuració + carregador/validador de `config.yaml` | ✅ pas 1 |
| `salafatiga/core/` | Model de dades comú, catàleg de variables, unitats | ✅ pas 1 |
| `salafatiga/acquisition/variador/registers.py` | Mapa de registres del SPEEDRIVE V2 i conversió d'adreces | ✅ pas 1 |
| `salafatiga/logging_setup.py` | Logs interns amb rotació | ✅ pas 1 |
| `salafatiga/storage/` | Base de dades històrica (SQLite): esquema, connexió, repositori | fet pas 2 |
| `salafatiga/acquisition/variador/` (modbus_rtu, source) | Client Modbus RTU i font de dades del variador | fet pas 3 |
| `salafatiga/acquisition/plc/` | Client Modbus TCP, font de dades del PLC i simulador in-process | fet pas 3 |
| `salafatiga/services/` | Bus de senyals + servei d'adquisició | fet pas 3 |
| `run_plc_simulator.py` + `acquisition/plc/map.py` | Simulador del PLC (servidor Modbus TCP autònom) | fet pas 4 |
| `salafatiga/processing/` | Validació i tractament bàsic | fet pas 5 |
| `salafatiga/alarms/` | Catàleg d'alarmes, motor de regles, esdeveniments | fet pas 5 |
| `salafatiga/ui/` | Interfície Qt (PySide6; gràfiques en viu amb QPainter) | fet pas 6 |
| `salafatiga/export/` | Exportació de dades | fet pas 7 |
| `salafatiga/remote/` + `run_web.py` | API + dashboard web | fet pas 8 |
| `salafatiga/storage/oracle_*.py` + `schema_oracle.sql` | Pool Oracle, repositori i esquema corporatiu | fet pas 9 |
| `salafatiga/storage/read_facade.py` | Façana de lectura amb fallback Oracle → SQLite | fet pas 9 |
| `salafatiga/services/oracle_sync.py` | Sync periòdic SQLite → Oracle amb backoff i purga | fet pas 9 |

## 5. Decisions tècniques

| Àmbit | Decisió | Motiu |
|---|---|---|
| Llenguatge | Python 3.11+ | Continuïtat amb els scripts de proves existents |
| GUI local | PySide6 (Qt6) | El plec demana Qt/PyQt/PySide; binding oficial, LGPL |
| Gràfiques en viu | QPainter (PySide6) | Suficient per a temps real i sense dependències addicionals |
| Modbus RTU (variador) | minimalmodbus + pyserial | El que ja s'utilitza a `proba_usb.py` |
| Modbus TCP (PLC) | pymodbus | Client (PC LAB) i servidor (simulador) amb la mateixa llibreria |
| Històric local | SQLite (fitxer únic) | Buffer simple i robust, transaccional. Sempre present, encara que Oracle estigui actiu |
| Històric corporatiu | Oracle (esquema propi, `oracledb` thin) | Font de veritat per a IT i altres consultors. Connexió directa o via wallet (mTLS) |
| Configuració | YAML + dataclasses tipades | Editable a mà i validable |
| Consulta remota | FastAPI + HTML/JS | Procés separat que llegeix l'històric; no exposa cap dispositiu de camp |
| Logs | `logging` + RotatingFileHandler | Estàndard |

## 6. Filosofia d'implementació (ordre del pla)

1. Esquelet + fonaments (config, model de dades, catàleg de variables, registres del Speedrive, logs).
2. Emmagatzematge (SQLite: esquema + repositori).
3. Adquisició (variador + PLC) + bus + servei d'adquisició.
4. Simulador del PLC autònom.
5. Processament/validació + alarmes/esdeveniments.
6. Interfície Qt.
7. Exportació.
8. Dashboard web.
9. Oracle corporatiu + sync periòdic + fallback de lectura a SQLite.
