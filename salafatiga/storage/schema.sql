PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    descripcio TEXT NOT NULL DEFAULT '',
    addr INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS variables (
    id TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    origin TEXT NOT NULL,
    kind TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    per_equip INTEGER NOT NULL DEFAULT 1,
    descripcio TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    equip_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    variable_id TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL DEFAULT '',
    quality TEXT NOT NULL,
    raw INTEGER,
    status_code INTEGER,
    note TEXT NOT NULL DEFAULT '',
    -- Marca temporal UNIX (s) en què el sync ha confirmat la inserció a Oracle.
    -- NULL mentre la fila encara està pendent de bolcar.
    synced_at REAL
);

CREATE INDEX IF NOT EXISTS idx_meas_ts
    ON measurements (ts);

CREATE INDEX IF NOT EXISTS idx_meas_eq_var_ts
    ON measurements (equip_id, variable_id, ts);

CREATE INDEX IF NOT EXISTS idx_meas_var_ts
    ON measurements (variable_id, ts);

-- L'índex idx_meas_sync el crea la migració, perquè sobre BD existents la
-- columna 'synced_at' encara no hi és quan s'executa aquest script.

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    equip_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    type TEXT NOT NULL,
    severity INTEGER NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    variable_id TEXT,
    value REAL,
    synced_at REAL
);

CREATE INDEX IF NOT EXISTS idx_evt_ts
    ON events (ts);

CREATE INDEX IF NOT EXISTS idx_evt_eq_ts
    ON events (equip_id, ts);

CREATE INDEX IF NOT EXISTS idx_evt_code_ts
    ON events (code, ts);

-- L'índex idx_evt_sync també el crea la migració (vegeu nota més amunt).
