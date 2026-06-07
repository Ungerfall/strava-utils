#!/usr/bin/env python3
"""Generate a WhatsApp-ready group ride infographic from today's Strava activity.

Usage:
    python infographic.py [--date YYYY-MM-DD] [--output PATH]
"""

import argparse
import datetime
import json
from pathlib import Path

import strava_client as sc
import map_renderer
import elevation_renderer
import layout_composer

RIDERS_JSON = Path("riders.json")


def load_riders_cache() -> dict:
    if not RIDERS_JSON.exists():
        return {}
    riders = json.loads(RIDERS_JSON.read_text(encoding="utf-8"))
    return {r["id"]: r for r in riders if r.get("id")}

ATHLETE_PALETTE = ["#FC4C02", "#1E90FF", "#2ECC71", "#FFD700", "#DC50DC", "#00D2D2"]


def build_athlete_data(activity: dict) -> dict:
    return {
        "id": activity["athlete"]["id"],
        "name": activity["athlete"].get("firstname", "You"),
        "avatar_url": "",
        "color": ATHLETE_PALETTE[0],
    }


def enrich_primary_avatar(athlete_entry: dict) -> None:
    """Fetch the authenticated athlete's own profile to get their avatar URL."""
    try:
        profile = sc._get("/athlete")
        athlete_entry["name"] = profile.get("firstname", athlete_entry["name"])
        athlete_entry["avatar_url"] = profile.get("profile_medium", "")
    except Exception as e:
        print(f"  [warn] Could not fetch own profile: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD (default: today)")
    parser.add_argument("--output", help="Output PNG path (default: group_ride_YYYYMMDD.png)")
    parser.add_argument("--fetch-riders", action="store_true",
                        help="Fetch all followed athletes and save to riders.json, then exit")
    parser.add_argument("--riders", help="Comma-separated Strava athlete IDs for today's group")
    args = parser.parse_args()

    # ── Fetch-riders mode ───────────────────────────────────────────────────
    if args.fetch_riders:
        print("NOTE: Strava's social/following API endpoints have been removed.")
        print()
        print("To find a rider's Strava ID:")
        print("  1. Open their profile in the Strava app or strava.com")
        print("  2. Their ID is the number in the URL:  strava.com/athletes/XXXXXXXX")
        print()
        print("Then generate the infographic with:")
        print("  python infographic.py --riders ID1,ID2,ID3,ID4,ID5")
        return

    target_date = args.date or datetime.date.today().isoformat()

    print(f"[1/6] Fetching today's ride for {target_date}…")
    activity = sc.get_today_ride(target_date)
    activity_id = activity["id"]
    print(f"      Found: '{activity['name']}' ({activity['distance']/1000:.1f} km)")

    print("[2/6] Fetching activity detail and streams…")
    detail = sc.get_activity_detail(activity_id)
    streams = sc.get_streams(activity_id, ["latlng", "altitude", "distance"])

    print("[3/6] Building athlete data…")
    primary = build_athlete_data(detail)
    enrich_primary_avatar(primary)
    athletes = [primary]
    riders_cache = load_riders_cache()

    if args.riders:
        ids = [int(x.strip()) for x in args.riders.split(",") if x.strip()]
        for i, aid in enumerate(ids[:5]):
            profile = sc.get_athlete_profile(aid)
            cached = riders_cache.get(aid, {})

            if profile:
                name = f"{profile.get('firstname', '')} {profile.get('lastname', '')}".strip()
                avatar_url = profile.get("profile_medium", "")
                avatar_path = ""
            elif cached:
                name = cached.get("fullname") or f"{cached.get('firstname', '')} {cached.get('lastname', '')}".strip()
                avatar_url = ""
                avatar_path = cached.get("avatar_path", "")
                print(f"      [info] Using cached data for {aid}")
            else:
                print(f"      [warn] Could not fetch athlete {aid}, skipping")
                continue

            print(f"      + {name} (id={aid})")
            athletes.append({
                "name": name or f"Rider {aid}",
                "avatar_url": avatar_url,
                "avatar_path": avatar_path,
                "color": ATHLETE_PALETTE[min(i + 1, len(ATHLETE_PALETTE) - 1)],
                "device_watts": False,
                "km_data": {},
            })
    else:
        print("      No --riders specified; use --fetch-riders to build your group list.")

    print(f"      Total athletes: {len(athletes)}")

    print("[4/6] Rendering route map…")
    map_img = map_renderer.render_route(streams.get("latlng", []))

    print("[5/6] Rendering elevation profile…")
    elev_img = elevation_renderer.render_elevation(streams)

    print("[6/6] Composing final infographic…")
    output_img = layout_composer.compose(detail, map_img, elev_img, athletes)

    out_path = args.output or f"group_ride_{target_date.replace('-', '')}.png"
    output_img.save(out_path, "PNG", optimize=True)
    print(f"\n✓  Saved: {Path(out_path).resolve()}")
    print(f"   Size: {output_img.width}×{output_img.height} px")


if __name__ == "__main__":
    main()
