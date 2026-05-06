"""
SQLite storage layer.

Replaces the previous parquet/JSON cache files with a single
`cache/isitin.db` containing:
  - gauge_readings   per-river hourly USGS readings
  - precip_readings  per-river hourly Open-Meteo precip
  - cache_meta       last-fetch timestamp per (river_id, kind)
  - river_requests   user-submitted river suggestions
"""

import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd

DB_DIR = Path(__file__).resolve().parent.parent / "cache"
DB_PATH = DB_DIR / "isitin.db"


@contextmanager
def _connect():
    DB_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gauge_readings (
                river_id    TEXT NOT NULL,
                time        TEXT NOT NULL,
                value       REAL NOT NULL,
                column_name TEXT NOT NULL,
                PRIMARY KEY (river_id, time)
            );

            CREATE TABLE IF NOT EXISTS precip_readings (
                river_id  TEXT NOT NULL,
                time      TEXT NOT NULL,
                precip_mm REAL NOT NULL,
                PRIMARY KEY (river_id, time)
            );

            CREATE TABLE IF NOT EXISTS cache_meta (
                river_id   TEXT NOT NULL,
                kind       TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (river_id, kind)
            );

            CREATE TABLE IF NOT EXISTS river_requests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                river_name   TEXT NOT NULL,
                location     TEXT NOT NULL DEFAULT '',
                gauge_id     TEXT NOT NULL DEFAULT '',
                notes        TEXT NOT NULL DEFAULT '',
                submitted_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS models (
                river_id TEXT PRIMARY KEY,
                payload  BLOB NOT NULL,
                saved_at TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Cache freshness
# ---------------------------------------------------------------------------

def cache_updated_at(river_id: str, kind: str) -> datetime | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT updated_at FROM cache_meta WHERE river_id=? AND kind=?",
            (river_id, kind),
        ).fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def is_cache_fresh(river_id: str, kind: str, max_age_hours: float) -> bool:
    ts = cache_updated_at(river_id, kind)
    if ts is None:
        return False
    return (datetime.now() - ts) < timedelta(hours=max_age_hours)


def _touch_cache(conn: sqlite3.Connection, river_id: str, kind: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO cache_meta (river_id, kind, updated_at) VALUES (?, ?, ?)",
        (river_id, kind, datetime.now().isoformat()),
    )


# ---------------------------------------------------------------------------
# Gauge readings
# ---------------------------------------------------------------------------

def save_gauge(river_id: str, df: pd.DataFrame, column_name: str) -> None:
    """Replace all gauge readings for `river_id` with the rows in `df`."""
    rows = [
        (river_id, ts.isoformat(), float(val), column_name)
        for ts, val in df[column_name].dropna().items()
    ]
    with _connect() as conn:
        conn.execute("DELETE FROM gauge_readings WHERE river_id=?", (river_id,))
        conn.executemany(
            "INSERT INTO gauge_readings (river_id, time, value, column_name) VALUES (?, ?, ?, ?)",
            rows,
        )
        _touch_cache(conn, river_id, "gauge")


def load_gauge(river_id: str, column_name: str) -> pd.DataFrame:
    with _connect() as conn:
        df = pd.read_sql_query(
            "SELECT time, value FROM gauge_readings WHERE river_id=? ORDER BY time",
            conn,
            params=(river_id,),
        )
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/New_York")
    df = df.set_index("time").rename(columns={"value": column_name})
    return df


# ---------------------------------------------------------------------------
# Precipitation readings
# ---------------------------------------------------------------------------

def save_precip(river_id: str, df: pd.DataFrame) -> None:
    rows = [
        (river_id, ts.isoformat(), float(val))
        for ts, val in df["precip_mm"].items()
        if pd.notna(ts) and pd.notna(val)
    ]
    with _connect() as conn:
        conn.execute("DELETE FROM precip_readings WHERE river_id=?", (river_id,))
        conn.executemany(
            "INSERT INTO precip_readings (river_id, time, precip_mm) VALUES (?, ?, ?)",
            rows,
        )
        _touch_cache(conn, river_id, "precip")


def load_precip(river_id: str) -> pd.DataFrame:
    with _connect() as conn:
        df = pd.read_sql_query(
            "SELECT time, precip_mm FROM precip_readings WHERE river_id=? ORDER BY time",
            conn,
            params=(river_id,),
        )
    # Stored ISO strings span DST, so offsets vary between -04:00 and -05:00.
    # utc=True parses through the mixed offsets; then convert to ET for downstream.
    df["time"] = (
        pd.to_datetime(df["time"], utc=True)
          .dt.tz_convert("America/New_York")
    )
    df = df[df["time"].notna()].set_index("time")
    return df


# ---------------------------------------------------------------------------
# River requests
# ---------------------------------------------------------------------------

def add_river_request(
    river_name: str, location: str = "", gauge_id: str = "", notes: str = ""
) -> dict:
    submitted_at = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO river_requests (river_name, location, gauge_id, notes, submitted_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (river_name, location, gauge_id, notes, submitted_at),
        )
    return {
        "river_name": river_name,
        "location": location,
        "gauge_id": gauge_id,
        "notes": notes,
        "submitted_at": submitted_at,
    }


# ---------------------------------------------------------------------------
# Trained models
# ---------------------------------------------------------------------------

def save_model(river_id: str, model) -> None:
    buf = io.BytesIO()
    joblib.dump(model, buf)
    payload = buf.getvalue()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO models (river_id, payload, saved_at) VALUES (?, ?, ?)",
            (river_id, payload, datetime.now().isoformat()),
        )


def load_model(river_id: str):
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM models WHERE river_id=?", (river_id,)
        ).fetchone()
    if not row:
        return None
    return joblib.load(io.BytesIO(row[0]))


def list_river_requests() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT river_name, location, gauge_id, notes, submitted_at "
            "FROM river_requests ORDER BY id"
        ).fetchall()
    return [
        {
            "river_name": r[0],
            "location": r[1],
            "gauge_id": r[2],
            "notes": r[3],
            "submitted_at": r[4],
        }
        for r in rows
    ]


init_db()
