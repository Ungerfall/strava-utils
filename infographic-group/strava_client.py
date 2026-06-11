import json
import math
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


# ── Geo helpers ───────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _find_idx_at_distance(distances: list, target_m: float) -> int:
    """Binary search: index of the distance value closest to target_m."""
    lo, hi = 0, len(distances) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if distances[mid] < target_m:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _nearest_idx_and_dist(latlng: list, ref_lat: float, ref_lon: float) -> tuple[int, float]:
    """Linear scan: index and distance (m) of the closest GPS point to (ref_lat, ref_lon)."""
    best_idx, best_dist = 0, float("inf")
    for i, (lat, lon) in enumerate(latlng):
        d = _haversine_m(ref_lat, ref_lon, lat, lon)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx, best_dist


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


def summarize_streams_aligned(
    ref_latlng: list,
    ref_distance: list,
    rider_streams: dict,
    device_watts: bool,
    max_snap_m: float = 100.0,
    window: int = 5,
) -> dict:
    """
    Align rider metrics to the reference route by GPS proximity.

    For each km marker on the reference route, find the geographically nearest
    point in the rider's GPS track. If it is within max_snap_m the rider was
    present there and we average their metrics in a ±window index range. If it
    exceeds max_snap_m the rider had not joined yet (or had already left) and
    we emit None so the chart line breaks at that position.

    Returns {metric: [val_or_None, …]} with one entry per km of the reference.
    """
    rider_latlng = rider_streams.get("latlng", [])
    if not rider_latlng or not ref_distance:
        return {}

    n_km = int(ref_distance[-1] / 1000)
    if n_km == 0:
        return {}

    # Pre-compute the reference GPS index for each km marker once.
    ref_idx_per_km = [
        _find_idx_at_distance(ref_distance, km * 1000) for km in range(1, n_km + 1)
    ]

    result = {}
    for metric in ("watts", "cadence", "heartrate"):
        if metric == "watts" and not device_watts:
            continue
        values = rider_streams.get(metric)
        if not values or len(values) != len(rider_latlng):
            continue

        km_avgs = []
        for km_i, ref_idx in enumerate(ref_idx_per_km):
            ref_lat, ref_lon = ref_latlng[ref_idx]
            rider_idx, snap_dist = _nearest_idx_and_dist(rider_latlng, ref_lat, ref_lon)

            if snap_dist > max_snap_m:
                km_avgs.append(None)
                continue

            start = max(0, rider_idx - window)
            end = min(len(values), rider_idx + window + 1)
            segment = [v for v in values[start:end] if v is not None]
            km_avgs.append(sum(segment) / len(segment) if segment else None)

        result[metric] = km_avgs

    return result
