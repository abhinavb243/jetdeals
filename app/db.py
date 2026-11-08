"""SQLite storage."""
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    ticker TEXT,
    cik TEXT,
    hq_city TEXT,
    hq_airports TEXT,          -- comma-separated ICAO codes near HQ
    sector TEXT,
    watch INTEGER DEFAULT 0,
    is_sample INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS aircraft (
    icao24 TEXT PRIMARY KEY,   -- lowercase hex Mode S address
    tail TEXT NOT NULL,
    registrant TEXT,           -- name on FAA registry (company / LLC)
    registrant_type TEXT,      -- corporation, llc, partnership, ...
    company_id INTEGER REFERENCES companies(id),  -- resolved operating company
    model TEXT,
    is_sample INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY,
    icao24 TEXT NOT NULL,
    callsign TEXT,
    origin TEXT,               -- ICAO airport
    dest TEXT,
    dep_ts INTEGER,            -- unix seconds
    arr_ts INTEGER,
    source TEXT,
    UNIQUE(icao24, dep_ts)
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY,
    acquirer_id INTEGER REFERENCES companies(id),
    target_id INTEGER REFERENCES companies(id),
    kind TEXT,                 -- announced, rumor, 8-K, SC 13D, ...
    ts INTEGER,
    title TEXT,
    url TEXT,
    source TEXT,
    UNIQUE(source, url, title)
);
CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY,
    source TEXT,
    mode TEXT,                 -- live or sample
    ts INTEGER,
    rows INTEGER,
    note TEXT
);
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def log_run(conn, source: str, mode: str, rows: int, note: str = "") -> None:
    import time
    conn.execute(
        "INSERT INTO ingest_runs(source, mode, ts, rows, note) VALUES (?,?,?,?,?)",
        (source, mode, int(time.time()), rows, note),
    )
