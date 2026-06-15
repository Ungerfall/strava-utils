#!/usr/bin/env python3
"""Generate a WhatsApp-ready group ride infographic from a Strava ride activity.

Usage:
    python infographic.py [--activity ID] [--date YYYY-MM-DD] [--riders ID1,ID2,...]
                          [--photo-placeholder] [--output PATH]

--activity accepts any public or follower-visible Strava activity ID, not just
your own. If the OAuth token returns 404 (activity belongs to another athlete
and is not public via the API) the script falls back to the Playwright browser
session automatically.
"""

import argparse
import datetime
from pathlib import Path

import requests

import db
import strava_client as sc
import map_renderer
import elevation_renderer
import layout_composer
import strava_scraper as scraper
from strava_scraper import BrowserSession
from chart_renderer import render_chart

ATHLETE_PALETTE = ["#FC4C02", "#1E90FF", "#2ECC71", "#FFD700", "#DC50DC", "#00D2D2", "#FF6B6B", "#A3E635"]


def build_athlete_data(activity: dict) -> dict:
    return {
        "id": activity["athlete"]["id"],
        "name": activity["athlete"].get("firstname", "You"),
        "avatar_url": "",
        "color": ATHLETE_PALETTE[0],
        "device_watts": False,
        "km_data": {},
    }


def enrich_primary_avatar(athlete_entry: dict) -> None:
    try:
        profile = sc._get("/athlete")
        athlete_entry["name"] = profile.get("firstname", athlete_entry["name"])
        athlete_entry["avatar_url"] = profile.get("profile_medium", "")
    except Exception as e:
        print(f"  [warn] Could not fetch own profile: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activity", type=int,
                        help="Strava activity ID — any athlete's activity, not just yours")
    parser.add_argument("--date", help="Date in YYYY-MM-DD (default: today)")
    parser.add_argument("--output", help="Output PNG path")
    parser.add_argument("--fetch-riders", action="store_true",
                        help="Print instructions for finding rider IDs, then exit")
    parser.add_argument("--riders", help="Comma-separated Strava athlete IDs for today's group")
    parser.add_argument("--photo-placeholder", action="store_true",
                        help="Include a group photo placeholder section at the bottom")
    parser.add_argument("--min-similarity", type=float, default=0.25,
                        help="Minimum GPS overlap (0–1) to count as a route match (default: 0.25)")
    parser.add_argument("--title", help="Custom title shown in the infographic header")
    args = parser.parse_args()

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

    db.init_db()

    # One shared BrowserSession opened lazily when the OAuth API returns 404.
    _browser: BrowserSession | None = None
    _detail_via_oauth: bool = True  # False when the browser session was used

    def _api_detail(activity_id: int) -> dict:
        nonlocal _browser, _detail_via_oauth
        cached = db.get_activity_detail_cache(activity_id)
        if cached:
            _detail_via_oauth = False
            return cached
        try:
            result = sc.get_activity_detail(activity_id)
            _detail_via_oauth = True
            db.upsert_activity_detail_cache(activity_id, result)
            return result
        except requests.HTTPError as e:
            if e.response.status_code not in (403, 404):
                raise
        _detail_via_oauth = False
        print("      [info] Not accessible via OAuth — using browser session…")
        if _browser is None:
            _browser = BrowserSession().__enter__()
        result = _browser.get_activity_detail(activity_id)
        db.upsert_activity_detail_cache(activity_id, result)
        return result

    def _api_streams(activity_id: int, keys: list) -> dict:
        cached = db.get_activity_streams_cache(activity_id)
        if cached:
            return {k: v for k, v in cached.items() if k in keys}
        try:
            result = sc.get_streams(activity_id, keys)
            db.upsert_activity_streams_cache(activity_id, result)
            return result
        except requests.HTTPError as e:
            if e.response.status_code != 404:
                raise
        nonlocal _browser
        if _browser is None:
            _browser = BrowserSession().__enter__()
        result = _browser.get_streams(activity_id, keys)
        db.upsert_activity_streams_cache(activity_id, result)
        return result

    try:
        # ── 1. Resolve reference activity ───────────────────────────────────
        if args.activity:
            print(f"[1/6] Fetching activity {args.activity}…")
            detail = _api_detail(args.activity)
            activity = detail
            target_date = detail["start_date_local"][:10]
        else:
            target_date = args.date or datetime.date.today().isoformat()
            print(f"[1/6] Fetching today's ride for {target_date}…")
            activity = sc.get_today_ride(target_date)
            detail = _api_detail(activity["id"])

        activity_id = detail["id"]
        print(f"      Found: '{detail['name']}' ({detail['distance']/1000:.1f} km) on {target_date}")

        # ── 2. Fetch streams ─────────────────────────────────────────────────
        print("[2/6] Fetching activity detail and streams…")
        streams = _api_streams(
            activity_id,
            ["latlng", "altitude", "distance", "watts", "cadence", "heartrate"],
        )
        ref_latlng = streams.get("latlng", [])

        # ── 3. Build athlete list ────────────────────────────────────────────
        print("[3/6] Building athlete data…")
        primary = build_athlete_data(detail)
        if _detail_via_oauth:
            # Activity belongs to the authenticated user — enrich with OAuth profile.
            enrich_primary_avatar(primary)
        else:
            # Activity belongs to another athlete — detail already has their info.
            primary["avatar_url"] = detail["athlete"].get("profile_medium", "")
        primary["device_watts"] = detail.get("device_watts", False) or (
            "watts" in streams and len(streams["watts"]) > 0
        )
        primary["km_data"] = sc.summarize_streams(streams, primary["device_watts"])
        athletes = [primary]

        if args.riders:
            ids = [int(x.strip()) for x in args.riders.split(",") if x.strip()]
            for i, aid in enumerate(ids):
                cached = db.get_rider(aid)
                profile = None if cached else sc.get_athlete_profile(aid)

                if profile:
                    name = f"{profile.get('firstname', '')} {profile.get('lastname', '')}".strip()
                    avatar_url = profile.get("profile_medium", "")
                    avatar_path = ""
                elif cached:
                    name = (cached.get("fullname")
                            or f"{cached.get('firstname', '')} {cached.get('lastname', '')}".strip())
                    avatar_url = ""
                    avatar_path = cached.get("avatar_path", "")
                    print(f"      [info] Using cached data for {aid}")
                else:
                    # v3 API returned 403 — fall back to scraping the profile page.
                    if _browser is None:
                        _browser = BrowserSession().__enter__()
                    scraped = _browser.get_athlete_profile(aid)
                    if scraped:
                        name = f"{scraped.get('firstname', '')} {scraped.get('lastname', '')}".strip()
                        avatar_url = scraped.get("profile_medium", "")
                        avatar_path = ""
                        print(f"      [info] Scraped profile for {aid}: {name}")
                    else:
                        print(f"      [warn] Could not fetch athlete {aid}, skipping")
                        continue

                color = ATHLETE_PALETTE[(i + 1) % len(ATHLETE_PALETTE)]
                athlete: dict = {
                    "name": name or f"Rider {aid}",
                    "avatar_url": avatar_url,
                    "avatar_path": avatar_path,
                    "color": color,
                    "device_watts": False,
                    "km_data": {},
                    "latlng": [],
                }

                match = scraper.find_route_match_cached(activity_id, aid, target_date, threshold=args.min_similarity)
                if match is scraper._NEEDS_BROWSER:
                    if _browser is None:
                        _browser = BrowserSession().__enter__()
                    match = _browser.find_route_match(activity_id, ref_latlng, aid, target_date, threshold=args.min_similarity)
                if match and match["activity_id"] == activity_id:
                    # Rider's best match is the primary activity itself — they're the activity
                    # owner already shown as the primary athlete, so skip to avoid a duplicate.
                    print(f"      + {name} (id={aid}, skipped — same activity as primary)")
                    athletes.append(athlete)
                    continue
                if match:
                    print(f"      + {name} matched activity {match['activity_id']} "
                          f"(similarity={match['similarity']:.0%})")
                    try:
                        rider_streams = _api_streams(
                            match["activity_id"],
                            ["latlng", "distance", "watts", "cadence", "heartrate"],
                        )
                        rider_detail = _api_detail(match["activity_id"])
                        # Strava streams only contain recorded sensor data, never
                        # estimated watts, so presence of watts stream = power meter.
                        device_watts = rider_detail.get("device_watts", False) or (
                            "watts" in rider_streams and len(rider_streams["watts"]) > 0
                        )
                        athlete["device_watts"] = device_watts
                        athlete["latlng"] = rider_streams.get("latlng", [])
                        athlete["km_data"] = sc.summarize_streams_aligned(
                            ref_latlng,
                            streams["distance"],
                            rider_streams,
                            athlete["device_watts"],
                        )
                    except Exception as e:
                        print(f"      [warn] Could not fetch rider streams: {e}")
                else:
                    print(f"      + {name} (id={aid}, no matching route found)")

                athletes.append(athlete)
        else:
            print("      No --riders specified; use --fetch-riders to build your group list.")

        print(f"      Total athletes: {len(athletes)}")

        # ── 4-6. Render ──────────────────────────────────────────────────────
        print("[4/6] Rendering route map…")
        rider_overlays = [
            {"latlng": a["latlng"], "color": a["color"]}
            for a in athletes[1:]  # skip primary (index 0)
            if a.get("latlng")
        ]
        map_img = map_renderer.render_route(ref_latlng, riders=rider_overlays)

        print("[5/6] Rendering elevation profile…")
        elev_img = elevation_renderer.render_elevation(streams)

        print("[6/6] Composing final infographic…")
        chart_img = render_chart(athletes) if any(a.get("km_data") for a in athletes) else None
        output_img = layout_composer.compose(
            detail, map_img, elev_img, athletes,
            chart_img=chart_img,
            photo_placeholder=args.photo_placeholder,
            title=args.title or "",
        )

        out_path = args.output or f"group_ride_{target_date.replace('-', '')}.png"
        output_img.save(out_path, "PNG", optimize=True)
        print(f"\n✓  Saved: {Path(out_path).resolve()}")
        print(f"   Size: {output_img.width}×{output_img.height} px")

    finally:
        if _browser is not None:
            _browser.__exit__(None, None, None)


if __name__ == "__main__":
    main()
