"""Kick storage. SQLite by default; Postgres (Tiger Data / TimescaleDB) when DATABASE_URL is set.

The Postgres backend also streams every raw sample into a hypertable, which is what makes
Tiger Data a natural fit: 500 Hz sensor data, time-bucketed with continuous aggregates.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from config import DATABASE_URL, SAMPLE_RATE_HZ, SQLITE_PATH

_COLS = "id, ts, session, target, technique, predicted, confidence, overall, features, score, probs, label"


def _row_to_kick(r) -> dict:
    return {
        "id": r[0], "ts": r[1], "session": r[2], "target": r[3], "technique": r[4],
        "predicted": r[5], "confidence": r[6], "overall": r[7],
        "features": json.loads(r[8]), "score": json.loads(r[9]),
        "probs": json.loads(r[10]), "label": r[11],
    }


class SqliteStore:
    name = "sqlite"

    def __init__(self, path: str = SQLITE_PATH) -> None:
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute("""CREATE TABLE IF NOT EXISTS kicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, session TEXT, target TEXT,
                technique TEXT, predicted TEXT, confidence REAL, overall REAL,
                features TEXT, score TEXT, probs TEXT, window TEXT, label TEXT)""")
            self.db.commit()

    def add_kick(self, k: dict) -> int:
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO kicks (ts, session, target, technique, predicted, confidence, overall,"
                " features, score, probs, window, label) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (k["ts"], k["session"], k["target"], k["technique"], k["predicted"],
                 k["confidence"], k["overall"], json.dumps(k["features"]), json.dumps(k["score"]),
                 json.dumps(k["probs"]), json.dumps(k["window"])))
            self.db.commit()
            return int(cur.lastrowid)

    def list_kicks(self, session: str | None = None, limit: int = 500) -> list[dict]:
        q = f"SELECT {_COLS} FROM kicks"
        args: list = []
        if session:
            q += " WHERE session = ?"
            args.append(session)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        return [_row_to_kick(r) for r in reversed(rows)]

    def get_kick(self, kick_id: int) -> dict | None:
        with self.lock:
            r = self.db.execute(f"SELECT {_COLS}, window FROM kicks WHERE id = ?", (kick_id,)).fetchone()
        if not r:
            return None
        k = _row_to_kick(r[:12])
        k["window"] = json.loads(r[12])
        return k

    def set_label(self, kick_id: int, label: str | None) -> None:
        with self.lock:
            self.db.execute("UPDATE kicks SET label = ? WHERE id = ?", (label, kick_id))
            self.db.commit()

    def labeled(self) -> list[tuple[dict, str]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT features, label FROM kicks WHERE label IS NOT NULL").fetchall()
        return [(json.loads(f), l) for f, l in rows]

    def insert_samples(self, session: str, t_end: float, samples: list) -> None:
        return  # SQLite keeps kick windows only. Use Postgres for the raw stream.


class PgStore:
    """Untested against a live server in this repo. Needs: pip install "psycopg[binary]"."""
    name = "postgres"

    def __init__(self, url: str = DATABASE_URL) -> None:
        import psycopg
        self.conn = psycopg.connect(url, autocommit=True)
        self.lock = threading.Lock()
        with self.lock, self.conn.cursor() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS kicks (
                id BIGSERIAL PRIMARY KEY, ts DOUBLE PRECISION, session TEXT, target TEXT,
                technique TEXT, predicted TEXT, confidence REAL, overall REAL,
                features TEXT, score TEXT, probs TEXT, window TEXT, label TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS samples (
                time TIMESTAMPTZ NOT NULL, session TEXT, ax REAL, ay REAL, az REAL,
                gx REAL, gy REAL, gz REAL, f0 SMALLINT, f1 SMALLINT, f2 SMALLINT, f3 SMALLINT)""")
            try:
                c.execute("SELECT create_hypertable('samples', 'time', if_not_exists => TRUE)")
                c.execute("""CREATE MATERIALIZED VIEW IF NOT EXISTS samples_100ms
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('100 milliseconds', time) AS bucket, session,
                           max(sqrt(ax*ax + ay*ay + az*az)) AS peak_g,
                           max(sqrt(gx*gx + gy*gy + gz*gz)) AS peak_dps,
                           max(greatest(f0, f1, f2, f3)) AS peak_force
                    FROM samples GROUP BY bucket, session WITH NO DATA""")
            except Exception:
                pass  # plain Postgres: samples stay a normal table

    def add_kick(self, k: dict) -> int:
        with self.lock, self.conn.cursor() as c:
            c.execute(
                "INSERT INTO kicks (ts, session, target, technique, predicted, confidence, overall,"
                " features, score, probs, window) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " RETURNING id",
                (k["ts"], k["session"], k["target"], k["technique"], k["predicted"],
                 k["confidence"], k["overall"], json.dumps(k["features"]), json.dumps(k["score"]),
                 json.dumps(k["probs"]), json.dumps(k["window"])))
            return int(c.fetchone()[0])

    def list_kicks(self, session: str | None = None, limit: int = 500) -> list[dict]:
        q = f"SELECT {_COLS} FROM kicks"
        args: list = []
        if session:
            q += " WHERE session = %s"
            args.append(session)
        q += " ORDER BY id DESC LIMIT %s"
        args.append(limit)
        with self.lock, self.conn.cursor() as c:
            c.execute(q, args)
            rows = c.fetchall()
        return [_row_to_kick(r) for r in reversed(rows)]

    def get_kick(self, kick_id: int) -> dict | None:
        with self.lock, self.conn.cursor() as c:
            c.execute(f"SELECT {_COLS}, window FROM kicks WHERE id = %s", (kick_id,))
            r = c.fetchone()
        if not r:
            return None
        k = _row_to_kick(r[:12])
        k["window"] = json.loads(r[12])
        return k

    def set_label(self, kick_id: int, label: str | None) -> None:
        with self.lock, self.conn.cursor() as c:
            c.execute("UPDATE kicks SET label = %s WHERE id = %s", (label, kick_id))

    def labeled(self) -> list[tuple[dict, str]]:
        with self.lock, self.conn.cursor() as c:
            c.execute("SELECT features, label FROM kicks WHERE label IS NOT NULL")
            return [(json.loads(f), l) for f, l in c.fetchall()]

    def insert_samples(self, session: str, t_end: float, samples: list) -> None:
        n = len(samples)
        rows = []
        for i, s in enumerate(samples):
            ts = datetime.fromtimestamp(t_end - (n - 1 - i) / SAMPLE_RATE_HZ, tz=timezone.utc)
            rows.append((ts, session, *s.a, *s.g, *s.f))
        with self.lock, self.conn.cursor() as c:
            c.executemany(
                "INSERT INTO samples VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)


def make_store():
    if DATABASE_URL:
        return PgStore(DATABASE_URL)
    return SqliteStore()
