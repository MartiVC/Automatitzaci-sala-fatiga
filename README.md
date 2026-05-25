# Automatització i monitorització de la sala de fatiga

Sistema de captura, registre, visualització i consulta de dades de funcionament
de bombes centrífugues a la sala de fatiga del laboratori.

Aquest repositori conté el programari del **PC LAB**, l'ordinador del laboratori
que actua com a node central de supervisió: llegeix el variador **SPEEDRIVE V2**
per Modbus RTU (RS-485), **rep** dades del **PLC** per Modbus TCP (sensors externs
ja concentrats: temperatures, vibracions, rpm), unifica-ho tot en un model de
dades comú, ho valida, ho mostra en temps real, ho registra en un històric i ho
publica per a consulta remota.

> El PC LAB **mai** parla amb un sensor: només llegeix variables/tags que el PLC
> li exposa. Tota la lògica de sensors viu al PLC.

## Documentació de referència

A `docs/`:

- `0- plec de condicions_fatiga.pdf` — plec de condicions del projecte (ESPA).
- `Informe inicial.pdf`, `Informe de progrés 1 - 1637919.pdf` — informes del TFG.
- `Protocol Modbus Speedrive_V2.pdf` — protocol Modbus del variador (mapa de registres).

## Estructura del projecte

```
.
├─ run_app.py                  # python run_app.py           → app Qt del PC LAB
├─ run_plc_simulator.py        # python run_plc_simulator.py → simulador del PLC (Modbus TCP)
├─ run_web.py                  # python run_web.py           → dashboard web de consulta remota
├─ requirements.txt
├─ config/
│  ├─ config.example.yaml      # plantilla de configuració (versionada)
│  └─ config.yaml              # configuració real del PC LAB (NO versionada)
├─ docs/                       # documentació tècnica del programari + PDFs de referència
├─ data/                       # (runtime) historic.sqlite, exports/  — NO versionat
├─ logs/                       # (runtime) logs de l'aplicació          — NO versionat
├─ tests/                      # tests unitaris
└─ salafatiga/                 # paquet de l'aplicació
   ├─ config/                  # models de configuració + carregador/validador YAML
   ├─ core/                    # model de dades comú (Reading/Event), catàleg de variables, unitats
   ├─ acquisition/             # adquisició de dades
   │  ├─ variador/             # SPEEDRIVE V2 (Modbus RTU): mapa de registres, client, font + simulador
   │  └─ plc/                  # PLC (Modbus TCP): mapa de tags, client, font + simulador (in-process i servidor)
   ├─ processing/              # validació de rangs/salts/antiguitat + pipeline
   ├─ alarms/                  # catàleg d'alarmes del variador, motor de regles de llindar, esdeveniments
   ├─ storage/                 # base de dades històrica (SQLite): esquema, connexió, repositori
   ├─ export/                  # exportació de mesures/esdeveniments a CSV
   ├─ services/                # bus de senyals + servei d'adquisició
   ├─ ui/                      # interfície Qt (PySide6; gràfiques en viu pintades amb QPainter)
   └─ remote/                  # API FastAPI + dashboard web estàtic (consulta remota)
```

## Estat actual

Pla base d'implementació complet (config → emmagatzematge → adquisició → simulador
PLC → processament/alarmes → UI Qt → exportació → dashboard web). En resum:

- **Configuració** (`salafatiga/config/`): models tipats + carregador/validador de `config.yaml`.
- **Model de dades comú** (`salafatiga/core/`): `Reading`, `Event`, enumeracions, catàleg de
  variables (amb llindars d'avís/alarma) i unitats.
- **Adquisició** (`salafatiga/acquisition/` + `salafatiga/services/`): contracte comú de fonts,
  client Modbus RTU del variador + font (i simulador in-process), mapa de tags del PLC + client
  Modbus TCP + font (i simulador in-process), bus de senyals i servei d'adquisició.
- **Simulador PLC autònom** (`run_plc_simulator.py`): servidor Modbus TCP amb els mateixos
  registres que l'app llegeix del PLC real, anomalies simulades (`heat`, `vibration`), mode `--once`.
- **Processament i alarmes** (`salafatiga/processing/`, `salafatiga/alarms/`): validació de rangs,
  antiguitat i salts amb assignació de `Quality`; catàleg d'alarmes del variador; regles de llindar
  amb antirebot que generen `Event`.
- **Emmagatzematge** (`salafatiga/storage/`): esquema SQLite (`measurements`, `events`, catàlegs
  `devices`/`variables`), inserció per lots, consultes d'històric, últimes lectures, purga per retenció.
- **UI Qt** (`salafatiga/ui/`): finestra amb Sinòptic, Gràfiques, Alarmes, Històric i Config;
  inici/aturada d'adquisició, selecció d'equip, persistència; gràfiques en viu pintades amb QPainter
  (selecció de variables, autoescala i finestra temporal configurable).
- **Exportació** (`salafatiga/export/`): CSV de mesures i esdeveniments amb metadades de variable.
- **Dashboard web** (`salafatiga/remote/` + `run_web.py`): API FastAPI de consulta de l'històric
  (`/api/health`, `/api/variables`, `/api/latest`, `/api/measurements`, `/api/events`) i pàgina web
  estàtica (KPIs, targetes de variable amb estat de llindars, gràfic de tendència SVG amb finestra
  configurable i tooltip, taula d'esdeveniments, detall de lectures). No exposa cap dispositiu de camp.
- **Oracle corporatiu + sync** (`salafatiga/storage/oracle_*.py`, `salafatiga/services/oracle_sync.py`,
  `salafatiga/storage/read_facade.py`): el SQLite local fa de buffer i el `OracleSyncService` empeny
  periòdicament les noves files a Oracle (amb backoff exponencial i purga del buffer). El dashboard
  llegeix sempre a través d'una `ReadFacade` que cau al SQLite si Oracle no respon. La UI Qt i el web
  pinten un badge "Oracle" amb l'estat actual (verd / groc / gris).

Pendents futurs possibles: proves de camp amb hardware real, ajust dels factors d'escala dels
registres del variador i afinat dels llindars d'avís/alarma amb dades reals.

## Posada en marxa (estat actual)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

copy config\config.example.yaml config\config.yaml   # i edita'l (port COM, equips, IP del PLC...)
python run_app.py                 # obre la UI Qt
python run_app.py --no-ui         # només valida config + SQLite
python run_app.py --start         # obre la UI i inicia l'adquisició
```

Demo fora del laboratori, sense hardware:

```yaml
variador:
  enabled: true
  mode: sim_inproc

plc:
  enabled: true
  mode: sim_inproc
```

Amb aquesta configuració només cal:

```bash
python run_app.py --start
```

Simulador PLC:

```bash
python run_plc_simulator.py --once
python run_plc_simulator.py --host 127.0.0.1 --port 5020
python run_plc_simulator.py --anomaly heat
```

Dashboard web:

```bash
python run_web.py --host 127.0.0.1 --port 8000
```

Un cop arrencat: `http://127.0.0.1:8000`

## Desplegament corporatiu (Oracle + sync)

Per a la integració amb la xarxa d'ESPA, el PC LAB pot escriure l'històric a la
base de dades **Oracle corporativa** mantenint el SQLite local com a buffer.
Així el sistema continua adquirint i guardant encara que la xarxa amb Oracle
caigui — quan torna, el sync recupera les files pendents automàticament.

Edita `config/config.yaml` i activa-ho:

```yaml
oracle:
  enabled: true
  host: oracle.espa.local
  port: 1521
  service_name: ESPAPRD
  user: SALAFATIGA
  password: env:ORACLE_PASSWORD     # llegida d'una variable d'entorn
  auto_create_schema: true          # si IT no ha desplegat l'esquema manualment

sync:
  enabled: true
  push_period_s: 30.0
  batch_size: 1000
  retention_local_days: 7
```

Després cal definir la contrasenya com a variable d'entorn (no la posis al YAML):

```powershell
# PowerShell — sessió actual
$env:ORACLE_PASSWORD = "..."

# Permanent per a l'usuari
setx ORACLE_PASSWORD "..."
```

Amb wallet d'Oracle (mTLS), substitueix `host`/`port`/`service_name` per:

```yaml
oracle:
  enabled: true
  wallet_dir: C:\oracle\wallet_salafatiga
  wallet_password: env:ORACLE_WALLET_PASSWORD
  dsn: SALAFATIGA_HIGH              # àlies del tnsnames.ora del wallet
  user: SALAFATIGA
  password: env:ORACLE_PASSWORD
```

Per a la posada en marxa real al laboratori (firewall, reverse proxy,
certificat, NTP, backups...) vegeu [docs/desplegament.md](docs/desplegament.md).

## Requisits

- Python 3.11 o superior.
- Adaptador RS-485 ↔ USB per al variador (Windows assigna un port `COMx`).
- Accés de xarxa al PLC (o al simulador local) per Modbus TCP.

## Proba simulació - NO PLC - NO VARIADOR
python run_app.py --start                         ##Qt -> t1

python run_web.py --host 127.0.0.1 --port 8000    ##web -> t2
http://127.0.0.1:8000


## Proba simulació - NO PLC - SI VARIADOR

# Llista els ports sèrie disponibles
[System.IO.Ports.SerialPort]::GetPortNames()

variador:
  enabled: true
  mode: rtu              # ← abans: sim_inproc
  port: COM3             # ← el port real que has vist al pas 1
  slave_id: 1            # adreça Modbus de l'esclau (per defecte 1 al Speedrive)
  baudrate: 9600         # ha de coincidir amb la config del variador
  parity: N
  bytesize: 8
  stopbits: 1
  timeout_s: 0.35        # si dóna timeouts, prova a pujar-ho (0.5–1.0)
  poll_period_s: 1.0
  comm_lost_after: 3
  equips:
    - id: GRUP1_B1
      addr: 0            # adreça @0..@7 del variador dins el grup; ha de coincidir amb el real
      descripcio: "..."
    # deixa només els equips que realment estiguin connectats i alimentats

plc:
  enabled: true
  mode: sim_inproc       # PLC dins el procés, sense xarxa