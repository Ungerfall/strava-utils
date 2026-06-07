import json
import time
from pathlib import Path
import requests

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
STRAVA_API = "https://www.strava.com/api/v3"
TOKEN_SERVER = "https://mcp.strava.com/mcp"


def _load_token() -> dict:
    data = json.loads(CREDENTIALS_PATH.read_text())
    mcp = data.get("mcpOAuth", {})
    entry = next(
        (v for v in mcp.values() if v.get("serverUrl") == TOKEN_SERVER), None
    )
    if not entry:
        raise RuntimeError(
            "Strava MCP credentials not found in ~/.claude/.credentials.json.\n"
            "Reconnect via the strava-mcp tool in Claude Code."
        )
    # expiresAt is milliseconds since epoch
    if entry.get("expiresAt", 0) < time.time() * 1000:
        raise RuntimeError(
            "Strava token has expired. Reconnect via the strava-mcp tool in Claude Code."
        )
    return entry


def get_headers() -> dict:
    entry = _load_token()
    return {"Authorization": f"Bearer {entry['accessToken']}"}


def _get(path: str, params: dict = None) -> dict | list:
    r = requests.get(f"{STRAVA_API}{path}", headers=get_headers(), params=params or {})
    r.raise_for_status()
    return r.json()


def get_today_ride(date_str: str = None) -> dict:
    """Return the most recent Ride activity for the given date (default: today)."""
    import datetime
    if date_str:
        day = datetime.date.fromisoformat(date_str)
    else:
        day = datetime.date.today()
    midnight = int(datetime.datetime.combine(day, datetime.time.min).timestamp())
    end_of_day = midnight + 86400

    activities = _get("/athlete/activities", {"after": midnight, "before": end_of_day, "per_page": 30})
    rides = [a for a in activities if a.get("type") in ("Ride", "VirtualRide", "GravelRide")]
    if not rides:
        raise RuntimeError(f"No ride activity found for {day}.")
    # Pick the longest ride
    return max(rides, key=lambda a: a.get("distance", 0))


def get_activity_detail(activity_id: int) -> dict:
    return _get(f"/activities/{activity_id}", {"include_all_efforts": True})


def get_streams(activity_id: int, keys: list[str]) -> dict:
    """Return streams as {key: [values]}."""
    raw = _get(f"/activities/{activity_id}/streams", {"keys": ",".join(keys), "key_by_type": True})
    return {k: v["data"] for k, v in raw.items() if "data" in v}


def get_athlete_profile(athlete_id: int) -> dict:
    """Fetch public profile for a given athlete ID. Returns {} on error."""
    try:
        a = _get(f"/athletes/{athlete_id}")
        return {
            "id": a.get("id"),
            "firstname": a.get("firstname", ""),
            "lastname": a.get("lastname", ""),
            "profile_medium": a.get("profile_medium", ""),
        }
    except Exception as e:
        print(f"  [warn] Could not fetch athlete {athlete_id}: {e}")
        return {}


def summarize_streams(streams: dict, device_watts: bool) -> dict:
    """Return per-km averages: {metric: [avg_val_km1, avg_val_km2, ...]}."""
    dist = streams.get("distance", [])
    if not dist:
        return {}

    max_km = int(dist[-1] / 1000)
    result = {}

    for metric in ("watts", "cadence", "heartrate"):
        if metric == "watts" and not device_watts:
            continue
        values = streams.get(metric)
        if not values or len(values) != len(dist):
            continue
        km_avgs = []
        for km in range(1, max_km + 1):
            segment = [
                v for d, v in zip(dist, values)
                if (km - 1) * 1000 <= d < km * 1000 and v is not None
            ]
            km_avgs.append(sum(segment) / len(segment) if segment else None)
        result[metric] = km_avgs

    return result
