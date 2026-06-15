import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db as db_module


def _fresh_db():
    """Return an in-memory connection via init_db."""
    db_module._conn = None
    return db_module.init_db(path=Path(":memory:"))


def test_upsert_rider_roundtrip():
    _fresh_db()
    rider = {
        "id": 12345,
        "firstname": "Alice",
        "lastname": "Smith",
        "fullname": "Alice Smith",
        "location": "Istanbul",
        "member_since": "Jan 2020",
        "avatar_path": "riders/12345/avatar.jpg",
        "kudos_count": 5,
    }
    db_module.upsert_rider(rider)
    result = db_module.get_rider(12345)
    assert result is not None
    assert result["firstname"] == "Alice"
    assert result["location"] == "Istanbul"


def test_upsert_rider_updates_existing():
    _fresh_db()
    db_module.upsert_rider({"id": 1, "firstname": "Bob", "lastname": "X"})
    db_module.upsert_rider({"id": 1, "firstname": "Robert", "lastname": "X"})
    result = db_module.get_rider(1)
    assert result["firstname"] == "Robert"


def test_get_rider_missing():
    _fresh_db()
    assert db_module.get_rider(99999) is None


def test_get_all_riders():
    _fresh_db()
    db_module.upsert_rider({"id": 1, "firstname": "A"})
    db_module.upsert_rider({"id": 2, "firstname": "B"})
    all_riders = db_module.get_all_riders()
    assert len(all_riders) == 2


def test_scraped_activities_roundtrip():
    _fresh_db()
    db_module.insert_scraped_activity(187003192, "2026-06-06", 18804777797, "Ride")
    rows = db_module.get_scraped_activities(187003192, "2026-06-06")
    assert len(rows) == 1
    assert rows[0]["activity_id"] == 18804777797
    assert rows[0]["activity_type"] == "Ride"


def test_scraped_activities_empty_for_other_date():
    _fresh_db()
    db_module.insert_scraped_activity(187003192, "2026-06-06", 18804777797, "Ride")
    rows = db_module.get_scraped_activities(187003192, "2026-06-07")
    assert rows == []


def test_similarity_cache_roundtrip():
    _fresh_db()
    db_module.upsert_similarity(100, 200, 0.75)
    score = db_module.get_similarity(100, 200)
    assert abs(score - 0.75) < 1e-9


def test_similarity_cache_update():
    _fresh_db()
    db_module.upsert_similarity(100, 200, 0.5)
    db_module.upsert_similarity(100, 200, 0.9)
    assert abs(db_module.get_similarity(100, 200) - 0.9) < 1e-9


def test_similarity_missing():
    _fresh_db()
    assert db_module.get_similarity(1, 2) is None


def test_riders_json_migration(tmp_path, monkeypatch):
    riders_data = [
        {"id": 100, "firstname": "Charlie", "lastname": "D", "fullname": "Charlie D",
         "kudos_count": 3},
        {"id": 200, "firstname": "Eve", "lastname": "F"},
    ]
    riders_json = tmp_path / "riders.json"
    riders_json.write_text(json.dumps(riders_data), encoding="utf-8")

    monkeypatch.setattr(db_module, "RIDERS_JSON", riders_json)
    db_module._conn = None
    db_module.init_db(path=Path(":memory:"))

    assert db_module.get_rider(100)["firstname"] == "Charlie"
    assert db_module.get_rider(200)["firstname"] == "Eve"
    assert riders_json.with_suffix(".json.bak").exists()
    assert not riders_json.exists()
