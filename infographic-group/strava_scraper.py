"""
Strava scraper — Playwright-based athlete activity discovery + GPS similarity.

One-time setup:
    python strava_scraper.py --save-session
"""

import argparse
import json
import math
import re
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup

import db
import strava_client as sc

SESSION_FILE = Path.home() / ".claude" / "strava_playwright_session.json"

RIDE_TYPES = {"Ride", "VirtualRide", "GravelRide", "MountainBikeRide", "EBikeRide"}


# ── Browser helpers ───────────────────────────────────────────────────────────

def _launch_browser_for_login(playwright):
    """
    Launch a VISIBLE browser for interactive Strava login.
    Tries Windows Chrome/Edge first (bypasses Google OAuth bot detection).
    Falls back to Playwright bundled Chromium.
    """
    import os

    windows_exes = [
        r"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        r"/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        r"/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        r"/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    ]
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        wsl_path = "/mnt/" + local_app.replace("\\", "/").replace(":", "").lower()
        windows_exes.insert(0, wsl_path + "/Google/Chrome/Application/chrome.exe")

    stealth_args = ["--disable-blink-features=AutomationControlled", "--disable-infobars"]

    for exe in windows_exes:
        if os.path.exists(exe):
            try:
                return playwright.chromium.launch(
                    headless=False, executable_path=exe, args=stealth_args
                )
            except Exception:
                continue

    # Fallback: bundled Chromium (visible)
    return playwright.chromium.launch(headless=False, args=stealth_args)


def _launch_headless_browser(playwright):
    """
    Launch a headless browser for automated scraping.
    Always uses Playwright's bundled Chromium — Windows Chrome EXEs crash in
    headless mode under WSL2 (no remote-debugging-pipe support).
    """
    return playwright.chromium.launch(headless=True)


# ── Browser API session ───────────────────────────────────────────────────────

class BrowserSession:
    """
    Context manager that opens a single headless Chromium window with the
    saved Strava session. Used as a fallback when the OAuth token cannot
    access an activity (e.g. it belongs to another athlete).

    Activity detail is scraped from the HTML page (the v3 detail endpoint
    requires OAuth even with session cookies). Streams are fetched via
    page.evaluate(fetch()) from within the activity page context — the v3
    streams endpoint does accept session cookies.
    """

    def __init__(self):
        self._pw_cm = self._pw = self._browser = self._context = self._page = None
        self._last_activity_id: int | None = None

    def __enter__(self) -> "BrowserSession":
        if not SESSION_FILE.exists():
            raise RuntimeError(
                f"No Playwright session at {SESSION_FILE}.\n"
                "Run: python3 strava_scraper.py --save-session"
            )
        from playwright.sync_api import sync_playwright
        self._pw_cm = sync_playwright()
        self._pw = self._pw_cm.__enter__()
        self._browser = _launch_headless_browser(self._pw)
        self._context = self._browser.new_context(storage_state=str(SESSION_FILE))
        self._page = self._context.new_page()
        return self

    def _ensure_on_activity_page(self, activity_id: int) -> None:
        if self._last_activity_id != activity_id:
            self._page.goto(
                f"https://www.strava.com/activities/{activity_id}",
                wait_until="domcontentloaded",
            )
            self._last_activity_id = activity_id

    def get_activity_detail(self, activity_id: int) -> dict:
        """Navigate to the activity page and parse the embedded metadata."""
        self._ensure_on_activity_page(activity_id)
        return _scrape_activity_detail_from_page(self._page, activity_id)

    def get_streams(self, activity_id: int, keys: list[str]) -> dict:
        """Fetch streams via the v3 API from the activity page's cookie context."""
        self._ensure_on_activity_page(activity_id)
        keys_str = ",".join(keys)
        raw = self._page.evaluate(
            """async (args) => {
                const [aid, keys] = args;
                const url = `/api/v3/activities/${aid}/streams?keys=${keys}&key_by_type=true`;
                const r = await fetch(url, {credentials: 'include'});
                if (!r.ok) throw new Error('HTTP ' + r.status + ': streams for ' + aid);
                return r.json();
            }""",
            [activity_id, keys_str],
        )
        return {k: v["data"] for k, v in raw.items() if isinstance(v, dict) and "data" in v}

    def get_athlete_profile(self, athlete_id: int) -> dict | None:
        """Scrape athlete profile page and return basic profile dict."""
        page = self._context.new_page()
        try:
            page.goto(f"https://www.strava.com/athletes/{athlete_id}",
                      wait_until="domcontentloaded")
            return _parse_athlete_profile(page.content(), athlete_id)
        except Exception as e:
            print(f"  [scraper] Could not scrape athlete {athlete_id}: {e}")
            return None
        finally:
            page.close()

    def get_activities_on_date(self, athlete_id: int, date_str: str) -> list[int]:
        """Scrape athlete profile for ride activity IDs on date_str."""
        from playwright.sync_api import TimeoutError as PWTimeout

        cached = db.get_scraped_activities(athlete_id, date_str)
        if cached:
            print(f"  [scraper] Using cached activities for athlete {athlete_id} on {date_str}")
            return [r["activity_id"] for r in cached]

        print(f"  [scraper] Scraping strava.com/athletes/{athlete_id} …")
        page = self._context.new_page()
        try:
            page.goto(f"https://www.strava.com/athletes/{athlete_id}",
                      wait_until="domcontentloaded")
            try:
                page.wait_for_selector(
                    'div[data-react-class="AthleteProfileHeaderMediaGrid"]', timeout=10000
                )
            except PWTimeout:
                pass
            html = page.content()
        except Exception as e:
            print(f"  [scraper] Playwright error: {e}")
            return []
        finally:
            page.close()

        ids = _parse_activity_ids(html, date_str, athlete_id)
        print(f"  [scraper] Found {len(ids)} ride(s) on {date_str} for athlete {athlete_id}")
        for aid in ids:
            db.insert_scraped_activity(athlete_id, date_str, aid, "Ride")
        return ids

    def find_route_match(
        self,
        ref_activity_id: int,
        ref_latlng: list,
        rider_id: int,
        date_str: str,
        threshold: float = 0.50,
    ) -> dict | None:
        """Find a rider's activity that GPS-overlaps ref_latlng by >= threshold."""
        ids = self.get_activities_on_date(rider_id, date_str)
        if not ids:
            return None

        for activity_id in ids:
            cached_score = db.get_similarity(ref_activity_id, activity_id)
            if cached_score is not None:
                print(f"  [scraper] Cached similarity {cached_score:.2f} for activity {activity_id}")
                score = cached_score
            else:
                try:
                    rider_streams = sc.get_streams(activity_id, ["latlng"])
                except Exception:
                    try:
                        rider_streams = self.get_streams(activity_id, ["latlng"])
                    except Exception as e:
                        print(f"  [scraper] Cannot fetch streams for {activity_id}: {e}")
                        continue
                rider_latlng = rider_streams.get("latlng", [])
                if not rider_latlng:
                    continue
                score = gps_similarity(ref_latlng, rider_latlng)
                db.upsert_similarity(ref_activity_id, activity_id, score)
                print(f"  [scraper] Similarity {score:.2f} for activity {activity_id}")

            if score >= threshold:
                return {"activity_id": activity_id, "similarity": score}

        return None

    def __exit__(self, *args) -> None:
        if self._browser:
            self._browser.close()
        if self._pw_cm:
            self._pw_cm.__exit__(*args)


# ── Cache-only route matching ─────────────────────────────────────────────────

_NEEDS_BROWSER = object()


def find_route_match_cached(
    ref_activity_id: int,
    rider_id: int,
    date_str: str,
    threshold: float = 0.50,
):
    """
    Resolve a route match purely from DB cache.

    Returns:
      dict   — match found: {"activity_id": X, "similarity": Y}
      None   — fully resolved from cache, no match above threshold
      _NEEDS_BROWSER — cache incomplete; caller must fall back to BrowserSession
    """
    cached_acts = db.get_scraped_activities(rider_id, date_str)
    if not cached_acts:
        return _NEEDS_BROWSER

    for row in cached_acts:
        activity_id = row["activity_id"]
        score = db.get_similarity(ref_activity_id, activity_id)
        if score is None:
            return _NEEDS_BROWSER
        if score >= threshold:
            print(f"  [scraper] Cached similarity {score:.2f} for activity {activity_id}")
            return {"activity_id": activity_id, "similarity": score}

    return None


def _scrape_activity_detail_from_page(page, activity_id: int) -> dict:
    """
    Parse a Strava activity page (already loaded in `page`) and return a dict
    that matches the shape of the v3 activity detail response used by infographic.py.
    """
    content = page.content()
    soup = BeautifulSoup(content, "html.parser")

    # ── Owner info from ADPKudosAndComments ──────────────────────────────────
    owner_name = ""
    owner_avatar = ""
    owner_id = 0
    activity_name = ""
    el = soup.find("div", attrs={"data-react-class": "ADPKudosAndComments"})
    if el and el.get("data-react-props"):
        try:
            props = json.loads(unescape(el["data-react-props"]))
            owner_name = props.get("ownerName", "")
            owner_avatar = props.get("ownerAvatarUrl", "")
            owner_id = int(props.get("ownerAthleteId", 0))
            activity_name = props.get("activityName", "")
        except (json.JSONDecodeError, ValueError):
            pass

    # ── Activity metadata from pageProps script ──────────────────────────────
    m = re.search(r"var pageProps = (\{[^;]+\});", content)
    page_props: dict = {}
    if m:
        try:
            page_props = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    if not activity_name:
        title = page.title()
        activity_name = title.split(" | ")[0] if " | " in title else title

    # ── Date: try JSON "start_date" first, then JS startDateLocal unix ts ───
    start_date = ""
    m_date = re.search(r'"start_date"\s*:\s*"([^"]+)"', content)
    if m_date:
        start_date = m_date.group(1)
    if not start_date:
        m_ts = re.search(r'startDateLocal\s*:\s*(\d{10})', content)
        if m_ts:
            import datetime as _dt
            start_date = _dt.datetime.fromtimestamp(int(m_ts.group(1)), tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Stats from inline-stats section ─────────────────────────────────────
    stats_text = ""
    stats_el = soup.select_one(".inline-stats, [data-testid=\"activity-stats\"]")
    if stats_el:
        stats_text = stats_el.get_text(" ")

    # Stats text has whitespace/newlines between numbers and labels.
    distance_m = 0.0
    m_dist = re.search(r"([\d,\.]+)\s+km\s+Distance", stats_text, re.DOTALL)
    if m_dist:
        distance_m = float(m_dist.group(1).replace(",", "")) * 1000

    moving_time_s = 0
    m_time = re.search(r"(\d+):(\d+):(\d+)\s+Moving Time", stats_text, re.DOTALL)
    if m_time:
        h, mn, s = int(m_time.group(1)), int(m_time.group(2)), int(m_time.group(3))
        moving_time_s = h * 3600 + mn * 60 + s

    elevation_m = 0.0
    m_elev = re.search(r"([\d,]+)\s+m\s+Elevation", stats_text, re.DOTALL)
    if m_elev:
        elevation_m = float(m_elev.group(1).replace(",", ""))

    device_watts = "Avg Power" in stats_text and "Estimated" not in stats_text

    # average_speed in m/s (Strava API convention); computed from distance/time.
    average_speed = (distance_m / moving_time_s) if moving_time_s > 0 else 0.0

    firstname = owner_name.split()[0] if owner_name else ""
    return {
        "id": activity_id,
        "name": activity_name,
        "distance": distance_m,
        "moving_time": moving_time_s,
        "total_elevation_gain": elevation_m,
        "average_speed": average_speed,
        "start_date": start_date,
        "start_date_local": start_date,
        "device_watts": device_watts,
        "athlete": {
            "id": owner_id,
            "firstname": firstname,
            "lastname": " ".join(owner_name.split()[1:]) if owner_name else "",
            "profile_medium": owner_avatar,
        },
    }


def session_available() -> bool:
    return SESSION_FILE.exists()


# ── Session management ────────────────────────────────────────────────────────

def save_session() -> None:
    """Open a visible browser, wait for the user to log in, then save session state."""
    from playwright.sync_api import sync_playwright, Error as PWError

    print()
    print("=" * 60)
    print("  Strava session setup")
    print("=" * 60)
    print()
    print("A browser window will open at strava.com/login.")
    print()
    print("  *** IMPORTANT: do NOT click 'Continue with Google' ***")
    print("  Google blocks sign-in from automated browsers.")
    print()
    print("  Instead, click 'Log In with Email' and enter your")
    print("  Strava email + password (set one at strava.com/settings")
    print("  → My Account → Change Password if you have none yet).")
    print()
    print("The session is saved automatically when you reach the dashboard.")
    print("Waiting up to 3 minutes…")
    print()

    with sync_playwright() as p:
        browser = _launch_browser_for_login(p)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.strava.com/login")
        try:
            # Wait until Strava redirects to the post-login dashboard.
            page.wait_for_url("**/dashboard**", timeout=180_000)
        except PWError as e:
            if "closed" in str(e).lower():
                print()
                print("[error] Browser was closed before reaching the dashboard.")
                print("        If Google rejected your sign-in, use 'Log In with Email' instead.")
                return
            raise
        # Let cookies settle after redirect.
        page.wait_for_timeout(2_000)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))
        browser.close()
    print(f"Session saved to {SESSION_FILE}")


# ── HTML parsing (pure — no network) ─────────────────────────────────────────

def _parse_activity_ids(html: str, date_str: str, athlete_id: int | None = None) -> list[int]:
    """
    Parse a Strava athlete profile page and return ride activity IDs for the given date.
    date_str: 'YYYY-MM-DD'
    athlete_id: used to filter group-activity entries to the correct athlete.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Primary: AthleteProfileHeaderMediaGrid (week-at-a-glance media grid)
    el = soup.find("div", attrs={"data-react-class": "AthleteProfileHeaderMediaGrid"})
    if el and el.get("data-react-props"):
        try:
            props = json.loads(unescape(el["data-react-props"]))
            ids = _filter_media_grid_items(props.get("items", []), date_str)
            if ids:
                return ids
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: Microfrontend profile feed (handles both old and new layouts)
    for el in soup.find_all("div", attrs={"data-react-class": "Microfrontend"}):
        raw = el.get("data-react-props", "")
        if "strava_feed" not in raw and '"feedType":"profile"' not in raw:
            continue
        try:
            props = json.loads(unescape(raw))
            # preFetchedEntries is inside appContext in newer Strava layouts
            entries = (
                props.get("preFetchedEntries")
                or props.get("appContext", {}).get("preFetchedEntries")
                or []
            )
            ids = _filter_feed_entries(entries, date_str, athlete_id)
            if ids:
                return ids
        except (json.JSONDecodeError, KeyError):
            pass

    return []


def _filter_media_grid_items(items: list[dict], date_str: str) -> list[int]:
    """Extract ride IDs from AthleteProfileHeaderMediaGrid items."""
    result = []
    for item in items:
        activity_sub = item.get("activity") or {}
        activity_type = (
            item.get("type") or item.get("activity_type")
            or activity_sub.get("type") or activity_sub.get("activity_type", "")
        )
        start = (
            item.get("start_date") or item.get("start_date_local")
            or activity_sub.get("start_date") or activity_sub.get("start_date_local", "")
        )
        activity_id = item.get("activity_id") or item.get("id") or activity_sub.get("id")
        if (
            activity_type in RIDE_TYPES
            and isinstance(start, str)
            and start[:10] == date_str
            and activity_id
        ):
            result.append(int(activity_id))
    return result


# Keep old name as alias so existing tests don't break
_filter_ride_ids = _filter_media_grid_items


def _filter_feed_entries(
    entries: list[dict], date_str: str, athlete_id: int | None = None
) -> list[int]:
    """
    Extract ride IDs from Microfrontend preFetchedEntries.
    Handles both single-athlete (entity=Activity) and group (entity=GroupActivity) entries.
    """
    import datetime

    result = []
    for entry in entries:
        entity = entry.get("entity", "")

        if entity == "Activity":
            act = entry.get("activity", {})
            atype = act.get("type", "")
            if atype not in RIDE_TYPES:
                continue
            # Date via cursorData.updated_at (Unix timestamp) — start_date absent in feed
            cursor = entry.get("cursorData", {})
            ts = cursor.get("updated_at")
            if ts:
                entry_date = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                if entry_date != date_str:
                    continue
            aid = act.get("id")
            if aid:
                result.append(int(aid))

        elif entity == "GroupActivity":
            row = entry.get("rowData", {})
            # Date via start_date_local or updated_at on the group record
            start = row.get("start_date_local") or row.get("updated_at", "")
            if start[:10] != date_str:
                continue
            for act_entry in row.get("activities", []):
                # Filter to the target athlete when scraping their profile
                if athlete_id and act_entry.get("athlete_id") != athlete_id:
                    continue
                atype = act_entry.get("activity_class_name", "")
                if atype not in RIDE_TYPES:
                    continue
                aid = act_entry.get("activity_id") or act_entry.get("entity_id")
                if aid:
                    result.append(int(aid))

    return list(dict.fromkeys(result))  # deduplicate, preserve order


# ── Scrape athlete profiles ───────────────────────────────────────────────────

def _parse_athlete_profile(html: str, athlete_id: int) -> dict | None:
    """
    Parse a Strava athlete profile page and return a profile dict matching
    the shape of the v3 /athletes/{id} response used by infographic.py.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Full name from <h1>
    h1 = soup.find("h1")
    full_name = h1.get_text(strip=True) if h1 else ""
    parts = full_name.split() if full_name else []
    firstname = parts[0] if parts else ""
    lastname = " ".join(parts[1:]) if len(parts) > 1 else ""

    # Avatar URL: the "xlarge" AvatarWrapper belongs to the profile being viewed
    avatar_url = ""
    for tag in soup.find_all("div", attrs={"data-react-class": "AvatarWrapper"}):
        try:
            props = json.loads(unescape(tag.get("data-react-props", "{}")))
        except json.JSONDecodeError:
            continue
        if props.get("size") == "xlarge" and props.get("type") == "athlete":
            avatar_url = props.get("src", "")
            # Prefer medium size if available
            avatar_url = avatar_url.replace("/large.jpg", "/medium.jpg")
            break

    if not firstname:
        return None
    return {
        "id": athlete_id,
        "firstname": firstname,
        "lastname": lastname,
        "profile_medium": avatar_url,
    }


def scrape_athlete_profile(athlete_id: int) -> dict | None:
    """Scrape an athlete's Strava profile page and return basic profile info."""
    if not SESSION_FILE.exists():
        return None

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = _launch_headless_browser(p)
            context = browser.new_context(storage_state=str(SESSION_FILE))
            page = context.new_page()
            page.goto(f"https://www.strava.com/athletes/{athlete_id}",
                      wait_until="domcontentloaded")
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  [scraper] Could not scrape athlete {athlete_id}: {e}")
        return None

    return _parse_athlete_profile(html, athlete_id)


# ── Scrape athlete activities ─────────────────────────────────────────────────

def get_activities_on_date(athlete_id: int, date_str: str) -> list[int]:
    """Return ride activity IDs for athlete on date_str, using DB cache when available."""
    cached = db.get_scraped_activities(athlete_id, date_str)
    if cached:
        print(f"  [scraper] Using cached activities for athlete {athlete_id} on {date_str}")
        return [r["activity_id"] for r in cached]

    if not SESSION_FILE.exists():
        print(
            f"  [scraper] No session file at {SESSION_FILE}. "
            "Run `python strava_scraper.py --save-session` to enable scraping."
        )
        return []

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print(f"  [scraper] Scraping strava.com/athletes/{athlete_id} …")
    try:
        with sync_playwright() as p:
            browser = _launch_headless_browser(p)
            context = browser.new_context(storage_state=str(SESSION_FILE))
            page = context.new_page()
            page.goto(f"https://www.strava.com/athletes/{athlete_id}", wait_until="domcontentloaded")
            try:
                page.wait_for_selector(
                    'div[data-react-class="AthleteProfileHeaderMediaGrid"]', timeout=10000
                )
            except PWTimeout:
                print("  [scraper] Timed out waiting for activity grid; trying with available HTML")
            html = page.content()
            browser.close()
    except Exception as e:
        print(f"  [scraper] Playwright error: {e}")
        return []

    ids = _parse_activity_ids(html, date_str, athlete_id)
    print(f"  [scraper] Found {len(ids)} ride(s) on {date_str} for athlete {athlete_id}")
    for aid in ids:
        db.insert_scraped_activity(athlete_id, date_str, aid, "Ride")
    return ids


# ── GPS similarity ────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _build_bucket_index(track: list, bucket_deg: float = 0.001) -> dict:
    """Map (bucket_lat, bucket_lon) → list of (lat, lon) points."""
    index: dict = {}
    for lat, lon in track:
        key = (int(lat / bucket_deg), int(lon / bucket_deg))
        index.setdefault(key, []).append((lat, lon))
    return index


def _fraction_within(source: list, target_index: dict, threshold_m: float, bucket_deg: float = 0.001) -> float:
    if not source:
        return 0.0
    matches = 0
    for lat, lon in source:
        blat = int(lat / bucket_deg)
        blon = int(lon / bucket_deg)
        found = False
        for dlat in (-1, 0, 1):
            for dlon in (-1, 0, 1):
                for tlat, tlon in target_index.get((blat + dlat, blon + dlon), []):
                    if _haversine_m(lat, lon, tlat, tlon) <= threshold_m:
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            matches += 1
    return matches / len(source)


def gps_similarity(
    track_a: list, track_b: list, threshold_m: float = 25.0, sample_step: int = 10
) -> float:
    """
    Bidirectional GPS overlap: fraction of sampled points from each track
    that fall within threshold_m of any point in the other track.
    Returns max(fwd, rev) in [0, 1].
    """
    if not track_a or not track_b:
        return 0.0

    sampled_a = track_a[::sample_step] or track_a[:1]
    sampled_b = track_b[::sample_step] or track_b[:1]

    index_b = _build_bucket_index(track_b)
    index_a = _build_bucket_index(track_a)

    fwd = _fraction_within(sampled_a, index_b, threshold_m)
    rev = _fraction_within(sampled_b, index_a, threshold_m)
    return max(fwd, rev)


# ── Route matching ────────────────────────────────────────────────────────────

def find_route_match(
    ref_activity_id: int,
    ref_latlng: list,
    rider_id: int,
    date_str: str,
    threshold: float = 0.50,
) -> dict | None:
    """
    Find a rider's activity on date_str whose GPS track overlaps ref_latlng by >= threshold.
    Returns {"activity_id": int, "similarity": float} or None.
    """
    ids = get_activities_on_date(rider_id, date_str)
    if not ids:
        return None

    for activity_id in ids:
        cached_score = db.get_similarity(ref_activity_id, activity_id)
        if cached_score is not None:
            print(f"  [scraper] Cached similarity {cached_score:.2f} for activity {activity_id}")
            score = cached_score
        else:
            try:
                streams = sc.get_streams(activity_id, ["latlng"])
            except Exception as e:
                print(f"  [scraper] Cannot fetch streams for {activity_id}: {e}")
                continue
            rider_latlng = streams.get("latlng", [])
            if not rider_latlng:
                continue
            score = gps_similarity(ref_latlng, rider_latlng)
            db.upsert_similarity(ref_activity_id, activity_id, score)
            print(f"  [scraper] Similarity {score:.2f} for activity {activity_id}")

        if score >= threshold:
            return {"activity_id": activity_id, "similarity": score}

    return None


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-session", action="store_true",
                        help="Open browser for Strava login and save session")
    args = parser.parse_args()

    if args.save_session:
        save_session()
    else:
        parser.print_help()
