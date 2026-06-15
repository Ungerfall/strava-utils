import json
import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "strava_cache.db"
RIDERS_JSON = Path(__file__).parent / "riders.json"

_conn: sqlite3.Connection | None = None


def init_db(path: Path = DB_PATH) -> sqlite3.Connection:
    global _conn
    _conn = sqlite3.connect(str(path))
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _create_schema(_conn)
    _migrate_riders_json(_conn)
    return _conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS riders (
            id           INTEGER PRIMARY KEY,
            firstname    TEXT,
            lastname     TEXT,
            fullname     TEXT,
            location     TEXT,
            member_since TEXT,
            avatar_path  TEXT,
            kudos_count  INTEGER DEFAULT 0,
            updated_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS scraped_activities (
            athlete_id    INTEGER NOT NULL,
            date          TEXT NOT NULL,
            activity_id   INTEGER NOT NULL,
            activity_type TEXT,
            scraped_at    TEXT NOT NULL,
            PRIMARY KEY (athlete_id, activity_id)
        );
        CREATE TABLE IF NOT EXISTS similarity_cache (
            ref_activity_id   INTEGER NOT NULL,
            rider_activity_id INTEGER NOT NULL,
            score             REAL NOT NULL,
            computed_at       TEXT NOT NULL,
            PRIMARY KEY (ref_activity_id, rider_activity_id)
        );
        CREATE TABLE IF NOT EXISTS activity_cache (
            activity_id  INTEGER PRIMARY KEY,
            detail_json  TEXT,
            streams_json TEXT,
            cached_at    TEXT NOT NULL
        );
    """)
    conn.commit()


def _migrate_riders_json(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) FROM riders").fetchone()
    if row[0] > 0 or not RIDERS_JSON.exists():
        return
    riders = json.loads(RIDERS_JSON.read_text(encoding="utf-8"))
    now = datetime.datetime.now().isoformat()
    for r in riders:
        if not r.get("id"):
            continue
        conn.execute(
            """INSERT OR IGNORE INTO riders
               (id, firstname, lastname, fullname, location, member_since, avatar_path, kudos_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["id"],
                r.get("firstname"),
                r.get("lastname"),
                r.get("fullname"),
                r.get("location"),
                r.get("member_since"),
                r.get("avatar_path"),
                r.get("kudos_count", 0),
                now,
            ),
        )
    conn.commit()
    RIDERS_JSON.rename(RIDERS_JSON.with_suffix(".json.bak"))
    print(f"  [db] Migrated {len(riders)} riders from riders.json → riders.json.bak")


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("Call db.init_db() before using the database.")
    return _conn


# ── Riders ────────────────────────────────────────────────────────────────────

def get_rider(athlete_id: int) -> dict | None:
    row = _get_conn().execute("SELECT * FROM riders WHERE id = ?", (athlete_id,)).fetchone()
    return dict(row) if row else None


def upsert_rider(rider: dict) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO riders (id, firstname, lastname, fullname, location, member_since,
               avatar_path, kudos_count, updated_at)
           VALUES (:id, :firstname, :lastname, :fullname, :location, :member_since,
               :avatar_path, :kudos_count, :updated_at)
           ON CONFLICT(id) DO UPDATE SET
               firstname=excluded.firstname, lastname=excluded.lastname,
               fullname=excluded.fullname, location=excluded.location,
               member_since=excluded.member_since, avatar_path=excluded.avatar_path,
               kudos_count=excluded.kudos_count, updated_at=excluded.updated_at""",
        {
            "id": rider["id"],
            "firstname": rider.get("firstname"),
            "lastname": rider.get("lastname"),
            "fullname": rider.get("fullname"),
            "location": rider.get("location"),
            "member_since": rider.get("member_since"),
            "avatar_path": rider.get("avatar_path"),
            "kudos_count": rider.get("kudos_count", 0),
            "updated_at": datetime.datetime.now().isoformat(),
        },
    )
    conn.commit()


def get_all_riders() -> list[dict]:
    rows = _get_conn().execute("SELECT * FROM riders").fetchall()
    return [dict(r) for r in rows]


# ── Scraped activities ────────────────────────────────────────────────────────

def get_scraped_activities(athlete_id: int, date_str: str) -> list[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM scraped_activities WHERE athlete_id = ? AND date = ?",
        (athlete_id, date_str),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_scraped_activity(
    athlete_id: int, date_str: str, activity_id: int, activity_type: str
) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT OR IGNORE INTO scraped_activities
               (athlete_id, date, activity_id, activity_type, scraped_at)
           VALUES (?, ?, ?, ?, ?)""",
        (athlete_id, date_str, activity_id, activity_type, datetime.datetime.now().isoformat()),
    )
    conn.commit()


# ── Similarity cache ──────────────────────────────────────────────────────────

def get_similarity(ref_activity_id: int, rider_activity_id: int) -> float | None:
    row = _get_conn().execute(
        "SELECT score FROM similarity_cache WHERE ref_activity_id = ? AND rider_activity_id = ?",
        (ref_activity_id, rider_activity_id),
    ).fetchone()
    return row[0] if row else None


def upsert_similarity(ref_activity_id: int, rider_activity_id: int, score: float) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO similarity_cache (ref_activity_id, rider_activity_id, score, computed_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ref_activity_id, rider_activity_id) DO UPDATE SET
               score=excluded.score, computed_at=excluded.computed_at""",
        (ref_activity_id, rider_activity_id, score, datetime.datetime.now().isoformat()),
    )
    conn.commit()


# ── Activity cache ────────────────────────────────────────────────────────────

def get_activity_detail_cache(activity_id: int) -> dict | None:
    row = _get_conn().execute(
        "SELECT detail_json FROM activity_cache WHERE activity_id = ? AND detail_json IS NOT NULL",
        (activity_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def get_activity_streams_cache(activity_id: int) -> dict | None:
    row = _get_conn().execute(
        "SELECT streams_json FROM activity_cache WHERE activity_id = ? AND streams_json IS NOT NULL",
        (activity_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def upsert_activity_detail_cache(activity_id: int, detail: dict) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO activity_cache (activity_id, detail_json, cached_at)
           VALUES (?, ?, ?)
           ON CONFLICT(activity_id) DO UPDATE SET
               detail_json=excluded.detail_json, cached_at=excluded.cached_at""",
        (activity_id, json.dumps(detail), datetime.datetime.now().isoformat()),
    )
    conn.commit()


def upsert_activity_streams_cache(activity_id: int, streams: dict) -> None:
    conn = _get_conn()
    existing = get_activity_streams_cache(activity_id)
    if existing:
        existing.update(streams)
        streams = existing
    conn.execute(
        """INSERT INTO activity_cache (activity_id, streams_json, cached_at)
           VALUES (?, ?, ?)
           ON CONFLICT(activity_id) DO UPDATE SET
               streams_json=excluded.streams_json, cached_at=excluded.cached_at""",
        (activity_id, json.dumps(streams), datetime.datetime.now().isoformat()),
    )
    conn.commit()
