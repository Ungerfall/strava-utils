---
name: strava-infographic-today-group
description: Generate a WhatsApp-ready group ride infographic from today's Strava activity
argument-hint: "[--activity ID] [--riders id1,id2,...] [--photo]"
arguments: [activity, riders, photo]
---

# strava-infographic-today-group

Generate a WhatsApp-ready group ride infographic from a Strava ride activity.

**Invocation:** `/strava-infographic-today-group $ARGUMENTS`
- `--activity $activity` (optional) — Strava activity ID to use as the reference route entry point; date is inferred from the activity
- `--riders $riders` (optional) — comma-separated Strava athlete IDs for the group, e.g. `12345678,23456789,34567890`
- `--photo $photo` (optional) — pass `--photo-placeholder` to add a dashed group photo section at the bottom

## One-time setup

### 1 — Install dependencies
```bash
cd /mnt/c/development/strava-utils/infographic-group
python3 -m pip install -r requirements.txt --break-system-packages
playwright install chromium
```

### 2 — Save Strava session (enables auto rider-matching)
```bash
python3 strava_scraper.py --save-session
```
A browser window opens (Windows Chrome or Edge via WSL2 interop).
Log in to Strava normally — the session is saved automatically once you reach the dashboard.
The session is saved to `~/.claude/strava_playwright_session.json` and reused on every run.

> **WSL2 note:** The script tries Windows Chrome at
> `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe` first.
> Make sure Chrome is installed on Windows. If Google OAuth blocks the browser ("this app may
> not be secure"), use Strava's email/password login instead of "Continue with Google".

### 3 — Find rider IDs
```bash
python3 infographic.py --fetch-riders
```
Then open each rider's profile at `strava.com/athletes/XXXXXXXX` — the number in the URL is their ID.

## Workflow

### Generate the infographic
```bash
python3 infographic.py --riders ID1,ID2,ID3 [--date YYYY-MM-DD] [--photo-placeholder]
```

Use `--activity` to pin a specific activity instead of looking up today's ride:
```bash
python3 infographic.py --activity 18804775758 --riders ID1,ID2,ID3
```

## Arguments
| Flag | Description |
|------|-------------|
| `--activity ID` | Any athlete's activity ID as the entry point — not just yours. Date is inferred from the activity. Falls back to browser session if not accessible via OAuth. |
| `--fetch-riders` | Print instructions for finding rider IDs |
| `--riders ID1,ID2,...` | Comma-separated Strava athlete IDs for the group (up to 5) |
| `--photo-placeholder` | Add a dashed group photo placeholder section at the bottom |
| `--output PATH` | Custom output file path |

## How rider matching works

When `--riders` is given, the scraper automatically:
1. Navigates to each rider's Strava profile (using the saved session)
2. Finds their activities on the same date
3. Computes GPS overlap (50% threshold) to confirm they did the same route
4. Fetches their cadence/power/HR streams if the route matches
5. Caches results in `strava_cache.db` so re-runs are instant

If no session file exists, riders are still shown with their profile photos but without performance charts.

## Output
Defaults to `group_ride_YYYYMMDD.png` (1080 px wide, height varies by content) in the working dir.
Keep finished infographics in `output/` by passing `--output ../output/group_ride_YYYYMMDD.png`.

## Steps Claude should follow
1. `cd /mnt/c/development/strava-utils/infographic-group`
2. Build the command:
   - If `$activity` is non-empty: include `--activity $activity`; derive the output date from the activity (fetch if needed) or use today's date as fallback
   - If `$riders` is non-empty: include `--riders $riders`
   - If `$riders` is empty: run without `--riders`, but first ask "Do you have the Strava athlete IDs?" unless clearly solo mode
   - If `$ARGUMENTS` contains `--photo`: append `--photo-placeholder`
   - Save to the repo output dir: append `--output ../output/group_ride_YYYYMMDD_ACTIVITYID.png` using the activity date (or today when no activity given) and the activity ID (omit `_ACTIVITYID` when no activity given)
3. Run the resulting command
4. Report the output path

**Examples** (run from `/mnt/c/development/strava-utils/infographic-group`)
- `/strava-infographic-today-group --activity 18804775758 --riders 12345678,23456789` → `python3 infographic.py --activity 18804775758 --riders 12345678,23456789 --output ../output/group_ride_20260612_18804775758.png`
- `/strava-infographic-today-group --riders 12345678,23456789,34567890` → `python3 infographic.py --riders 12345678,23456789,34567890 --output ../output/group_ride_20260613.png`
- `/strava-infographic-today-group --activity 18804775758 --riders 12345678 --photo yes` → `python3 infographic.py --activity 18804775758 --riders 12345678 --photo-placeholder --output ../output/group_ride_20260612_18804775758.png`
- `/strava-infographic-today-group` → solo mode (`python3 infographic.py --output ../output/group_ride_20260613.png`)

## Troubleshooting
- **"Strava token expired"** → Reconnect via the strava-mcp tool in Claude Code
- **"No ride activity found"** → No Ride on that date; check the date or Strava app
- **Riders show colored circles instead of photos** → Their Strava profile is private, or wrong ID
- **Missing map tiles** → Network issue fetching OSM tiles
- **No performance charts** → No cadence/HR data in streams, or no route match found for riders
- **Session expired** → Re-run `python3 strava_scraper.py --save-session`

## Running tests
```bash
cd /mnt/c/development/strava-utils/infographic-group
python3 -m pytest tests/ -v
```
