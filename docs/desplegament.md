# Desplegament al PC LAB i integració amb la xarxa corporativa

Aquest document és la **checklist de posada en marxa** del sistema al
laboratori d'ESPA. Està dividit en tres blocs:

1. **IT** (Abel) — preparació de la base de dades Oracle, xarxa i reverse proxy.
2. **PC LAB** (Martí) — instal·lació, configuració i arrencada del programari.
3. **Posada en marxa conjunta** — validacions creuades.

> El programari del PC LAB ja funciona de manera autònoma amb el buffer SQLite
> local. La integració amb Oracle i el reverse proxy d'IT és **opcional** per
> al funcionament intern, però **obligatòria** per al desplegament corporatiu.

---

## 1. Tasques d'IT

### 1.1 Base de dades Oracle

- [ ] Crear un **esquema/usuari de servei** dedicat (p. ex. `SALAFATIGA`) amb
      permisos `CREATE SESSION`, `CREATE TABLE`, `CREATE SEQUENCE`,
      `CREATE INDEX` i quota sobre el tablespace que correspongui.
- [ ] Decidir si l'esquema es desplega:
  - **automàticament** per l'aplicació (`oracle.auto_create_schema: true` al
    PC LAB), o
  - **manualment** per IT executant
    [`salafatiga/storage/schema_oracle.sql`](../salafatiga/storage/schema_oracle.sql).
- [ ] Generar credencials i fer-les arribar al Martí per un canal segur
      (no per email/Teams sense xifrar).
- [ ] Indicar la **cadena de connexió**:
  - Connexió directa: `host`, `port` (per defecte `1521`) i `service_name`.
  - O bé **wallet** d'Oracle (mTLS): lliurar el directori del wallet i l'àlies
    TNS (`dsn`) del `tnsnames.ora` inclòs.

### 1.2 Xarxa

- [ ] Assignar **IP fixa** al PC LAB a la xarxa interna.
- [ ] Obrir al firewall **TCP 1521 sortint** des de la IP del PC LAB cap al
      host d'Oracle (o el port que correspongui si s'usa wallet/listener
      diferent).
- [ ] Verificar que el PC LAB té accés al **servidor NTP corporatiu** (les
      marques temporals de les lectures han d'estar sincronitzades amb la
      resta de la infraestructura).

### 1.3 Reverse proxy + dashboard web

- [ ] Reservar un **subdomini intern** (p. ex. `salafatiga.espa.local`) i fer
      que apunti a la IP del PC LAB.
- [ ] Configurar el **reverse proxy** corporatiu davant del port d'uvicorn
      (per defecte `8000`):
  - HTTPS amb certificat intern vàlid.
  - Login **Office 365** (SSO corporatiu) abans d'arribar al dashboard.
  - Capçaleres `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-For`.
- [ ] Comunicar al Martí la(es) **IP(s) o CIDR del proxy** perquè es puguin
      indicar a `web.forwarded_allow_ips` al `config.yaml`.

### 1.4 Operació

- [ ] Confirmar que el PC LAB està inclòs a la política de **backups**
      corporativa (o, alternativament, acceptar que el buffer SQLite no es
      respatlla perquè la font de veritat és Oracle).
- [ ] Confirmar la política d'**actualitzacions de Windows** i, si cal,
      excloure el PC del reinici automàtic en hores d'assaig.

---

## 2. Tasques al PC LAB

### 2.1 Instal·lació base

- [ ] Instal·lar **Python 3.11+** (64 bits).
- [ ] Clonar/copiar el repositori a `C:\salafatiga\` (o la ruta acordada).
- [ ] Crear el `venv` i instal·lar dependències:
      ```powershell
      python -m venv .venv
      .venv\Scripts\activate
      pip install -r requirements.txt
      ```
- [ ] Copiar `config\config.example.yaml` a `config\config.yaml` i editar-lo:
  - `variador.port`, `variador.equips` segons la instal·lació real.
  - `plc.host`, `plc.port` segons el PLC real.

### 2.2 Activar la integració amb Oracle

- [ ] Editar `config\config.yaml`:
      ```yaml
      oracle:
        enabled: true
        host: <de-l-Abel>
        port: 1521
        service_name: <de-l-Abel>
        user: SALAFATIGA
        password: env:ORACLE_PASSWORD
        auto_create_schema: false   # si IT ha desplegat l'esquema manualment

      sync:
        enabled: true
        push_period_s: 30.0
        batch_size: 1000
        retention_local_days: 7
      ```
- [ ] Definir la contrasenya com a **variable d'entorn permanent**:
      ```powershell
      setx ORACLE_PASSWORD "<la contrasenya>"
      ```
      (Tanca i torna a obrir la sessió PowerShell perquè la nova variable
      sigui visible.)
- [ ] Si IT lliura **wallet**, copiar-lo a `C:\oracle\wallet_salafatiga\` i
      substituir el bloc `oracle:` pel format amb `wallet_dir` + `dsn`
      (veure [README.md](../README.md#desplegament-corporatiu-oracle--sync)).
- [ ] Validar la configuració arrencant **sense UI**:
      ```powershell
      python run_app.py --no-ui
      ```
      Hauria d'aparèixer al log `Oracle: ON | user=SALAFATIGA pool=1..4` i
      `Oracle sync: ON push_period=30.0s ...`. Si surt `Oracle: ON però no
      accessible`, hi ha un problema de xarxa/credencials que cal resoldre
      abans de seguir.

### 2.3 Activar el dashboard web darrere del reverse proxy

- [ ] A `config\config.yaml`:
      ```yaml
      web:
        enabled: true
        host: 0.0.0.0
        port: 8000
        behind_proxy: true
        forwarded_allow_ips: "<IP-del-proxy-d-IT>"
      ```
- [ ] Provar localment que arrenca:
      ```powershell
      python run_web.py --host 127.0.0.1 --port 8000
      ```
      i obrir `http://127.0.0.1:8000` per verificar que es veu el chip
      **"Oracle"** en verd al capçal.

### 2.4 Auto-arrencada (Windows Task Scheduler)

El repo inclou dos wrappers `.bat` i dos scripts PowerShell que registren
ambdós processos al **Task Scheduler natiu de Windows** (no requereix
NSSM ni cap altre programari extern):

- `scripts/run_app_service.bat` — arrenca `run_app.py --start`.
- `scripts/run_web_service.bat` — arrenca `run_web.py`.
- `scripts/install_tasks.ps1` — registra les dues tasques (idempotent).
- `scripts/uninstall_tasks.ps1` — les desregistra.

Comportament un cop instal·lades:

| Tasca | Trigger | Compte | Reinici si peta |
|---|---|---|---|
| `SalaFatiga - Dashboard web` | A l'arrencada (boot) | `SYSTEM` | 3 intents, cada 1 min |
| `SalaFatiga - Adquisicio (Qt)` | Al login de l'usuari actual | usuari interactiu | 3 intents, cada 1 min |

L'app Qt s'enregistra al **login** perquè necessita escriptori actiu;
el dashboard FastAPI al **boot** perquè ha de respondre encara que ningú
estigui logat al PC LAB.

Passos:

- [ ] Tenir el repo a la ruta definitiva (p. ex. `C:\salafatiga\`) — moure
      el repo després d'instal·lar les tasques deixaria les tasques apuntant
      a una ruta inexistent.
- [ ] Tenir Python disponible per al wrapper. Els `.bat` busquen, en aquest ordre:
      1. `.venv\Scripts\python.exe` dins del repo (recomanat al PC LAB per
         aïllar dependències).
      2. `python` al `PATH` (fallback; útil si fas servir el Python del sistema).
      Si cap dels dos no està disponible, el wrapper escriu un error al log
      i surt amb codi `2`.
- [ ] Probar manualment els wrappers (sense Task Scheduler encara):
      ```powershell
      .\scripts\run_web_service.bat
      ```
      Si arrenca el servidor i el pots aturar amb `Ctrl+C`, el wrapper
      funciona. Fes el mateix amb `run_app_service.bat`.
- [ ] Obrir PowerShell **com a administrador** i executar:
      ```powershell
      powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1
      ```
- [ ] Verificar que les tasques s'han registrat:
      ```powershell
      Get-ScheduledTask -TaskName 'SalaFatiga*' | Format-Table TaskName, State
      ```
- [ ] Arrencar-les manualment per validar (sense haver de fer reboot):
      ```powershell
      Start-ScheduledTask -TaskName 'SalaFatiga - Dashboard web'
      Start-ScheduledTask -TaskName 'SalaFatiga - Adquisicio (Qt)'
      ```
- [ ] Comprovar `logs\run_web_stdout.log` i `logs\run_app_stdout.log`.

Per desregistrar:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\uninstall_tasks.ps1
```

> Si has copiat el repo a una nova ruta, torna a executar
> `install_tasks.ps1` — les tasques es recrearan apuntant al nou camí.

---

## 3. Posada en marxa conjunta (validació)

Aquestes proves s'haurien de fer **un cop el PC LAB té la connectivitat
Oracle i el reverse proxy actiu**, amb el Martí i l'Abel disponibles.

- [ ] El PC LAB arrenca `run_app.py --start` i l'UI mostra el badge
      **Oracle: OK** (verd) al sinòptic.
- [ ] El dashboard web a través del subdomini intern
      (`https://salafatiga.espa.local`) demana login Office 365 i, un cop
      autenticat, mostra el chip **"Oracle"** en verd al capçal.
- [ ] Provoca un tall de xarxa cap a Oracle (desconnectar cable, regla de
      firewall temporal). Verifica que:
  - L'UI Qt mostra **Oracle: DEGRADAT** (vermell) al cap d'uns segons.
  - El dashboard web mostra el chip **"Oracle (fallback)"** en groc i
      continua servint lectures (de fet, del SQLite local).
  - El servei segueix adquirint i guardant al SQLite (mira els logs).
- [ ] Restableix la xarxa. Verifica que:
  - El backoff del sync es relaxa i les files acumulades del buffer
      s'envien a Oracle (consulta la taula `MEASUREMENTS` corporativa per
      veure les noves files).
  - Els badges tornen a verd.
- [ ] Comprova que els **timestamps** de les files a Oracle estan
      sincronitzats amb l'hora corporativa (validació indirecta del NTP).

---

## Annex A — proves locals amb Oracle Free 23ai (Docker)

Aquest annex descriu com aixecar una **Oracle Free 23ai** al portàtil amb
Docker per validar el sync de cap a peus abans del desplegament corporatiu.
És el que el Martí fa servir per a proves manuals end-to-end (línia 1 del
pla post-implementació).

Requereix Docker Desktop a Windows.

### A.1 — Arrencar el contenidor

```powershell
docker run -d `
  --name oracle-fatiga-dev `
  -p 1521:1521 `
  -e ORACLE_PWD=Oracle_Fatiga_Dev_1 `
  container-registry.oracle.com/database/free:latest
```

La primera vegada baixa ~3 GB. L'arrencada interna triga 2-3 minuts.
Per veure quan està llest:

```powershell
docker logs -f oracle-fatiga-dev
```

Quan vegis `DATABASE IS READY TO USE!` al log, prem `Ctrl+C` per sortir
del seguiment (el contenidor segueix corrent).

> Si el port `1521` ja està ocupat al portàtil, canvia el primer `1521`
> del `-p` a un altre (p. ex. `1522:1521`) i ajusta `oracle.port` al
> `config/config.local.yaml`.

### A.2 — Crear l'usuari SALAFATIGA

```powershell
docker exec -i oracle-fatiga-dev sqlplus -S "sys/Oracle_Fatiga_Dev_1@FREEPDB1 as sysdba" < scripts/oracle_dev_setup.sql
```

L'script és **idempotent**: el pots tornar a executar sense por.
Hauria d'imprimir `=== SALAFATIGA preparat al PDB FREEPDB1 ===`.

### A.3 — Configurar el PC LAB

```powershell
# Variable d'entorn només per a la sessió actual:
$env:ORACLE_PASSWORD = "Oracle_Fatiga_Dev_1"
```

Comprova que el `config/config.local.yaml` existeix (es crea a mà
copiant la plantilla; **no està versionat**).

### A.4 — Arrencar el PC LAB en mode prova

```powershell
python run_app.py --config config/config.local.yaml --start
```

Al log de l'arrencada has de veure:

```
Oracle: ON  | user=SALAFATIGA  pool=1..4
Oracle sync: ON  push_period=10.0s  batch=500  retention_local=7d
```

A la UI Qt → pestanya **Sinòptic** → fila **Oracle (històric): OK** (verd).

En paral·lel, en una altra terminal:

```powershell
python run_web.py --config config/config.local.yaml
```

i obre `http://127.0.0.1:8000`. El chip **"Oracle"** ha de sortir en verd
al capçal.

### A.5 — Provocar el fallback (validar la recuperació)

Amb el `run_app.py` corrent, atura el contenidor:

```powershell
docker stop oracle-fatiga-dev
```

Al cap d'uns segons hauràs de veure:

- **UI Qt**: badge **Oracle: DEGRADAT** (vermell) al sinòptic, amb tooltip
  amb el missatge d'error d'Oracle.
- **Logs**: `Oracle sync: ... (proper intent en Ns)` amb el backoff
  creixent (10s → 20s → 40s → ... → 60s màx).
- **Dashboard web**: chip **"Oracle (fallback)"** en groc. Les KPIs
  continuen actualitzant-se (es serveixen del SQLite local).
- **El sistema segueix adquirint** lectures simulades i acumulant-les
  al SQLite local (`data/historic_local.sqlite`).

### A.6 — Recuperar el servei

```powershell
docker start oracle-fatiga-dev
```

Al cap d'uns segons (depenent del backoff):

- El proper intent de sync ha de tenir èxit i el log ha de mostrar com
  s'envien les files acumulades a Oracle (`Oracle sync: N mesures enviades`).
- Els badges tornen a verd.

### A.7 — Inspeccionar les dades a Oracle (opcional)

```powershell
docker exec -it oracle-fatiga-dev sqlplus "salafatiga/Oracle_Fatiga_Dev_1@FREEPDB1"
```

Dins de SQL*Plus:

```sql
SELECT table_name FROM user_tables;
SELECT COUNT(*) FROM measurements;
SELECT COUNT(*) FROM events;
SELECT * FROM measurements ORDER BY ts DESC FETCH FIRST 5 ROWS ONLY;
EXIT
```

### A.8 — Netejar quan acabis

```powershell
docker stop oracle-fatiga-dev
docker rm oracle-fatiga-dev
# Si vols recuperar els ~3 GB de la imatge:
docker rmi container-registry.oracle.com/database/free:latest
```

El fitxer `data/historic_local.sqlite` el pots esborrar manualment quan
vulguis tornar a començar de zero.

---

## Annex B — referències

- Esquema Oracle: [`salafatiga/storage/schema_oracle.sql`](../salafatiga/storage/schema_oracle.sql)
- Codi del sync: [`salafatiga/services/oracle_sync.py`](../salafatiga/services/oracle_sync.py)
- Façana de lectura amb fallback: [`salafatiga/storage/read_facade.py`](../salafatiga/storage/read_facade.py)
- Plantilla de configuració: [`config/config.example.yaml`](../config/config.example.yaml)
- Script SQL de proves locals: [`scripts/oracle_dev_setup.sql`](../scripts/oracle_dev_setup.sql)
- Arquitectura general: [`docs/arquitectura.md`](arquitectura.md)
