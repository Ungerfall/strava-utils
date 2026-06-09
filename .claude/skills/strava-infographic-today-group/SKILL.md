---
name: strava-infographic-today-group
description: Generate a WhatsApp-ready group ride infographic from today's Strava activity
argument-hint: "[id1,id2,id3,...] [YYYY-MM-DD]"
arguments: [riders, date]
---

# strava-infographic-today-group

Generate a WhatsApp-ready group ride infographic from today's Strava activity.

**Invocation:** `/strava-infographic-today-group $ARGUMENTS`
- `$riders` (first arg) — comma-separated Strava athlete IDs for today's group, e.g. `12345678,23456789,34567890`
- `$date` (second arg, optional) — ride date as `YYYY-MM-DD`; defaults to today when omitted

## Workflow

### Step A — One-time setup: find your group riders
```bash
cd /mnt/c/development/strava-utils/infographic-group
python infographic.py --fetch-riders
```
This scans kudos on your last 20 activities and prints a frequency-sorted list of names.
Because Strava removed their social API, athlete IDs are **not** included.

To get an athlete's Strava ID:
1. Open their profile at `strava.com/athletes/XXXXXXXX`
2. The number in the URL is their ID

### Step B — Generate the infographic
```bash
python infographic.py --riders ID1,ID2,ID3,ID4,ID5 [--date YYYY-MM-DD]
```
Replace `ID1,...` with the Strava athlete IDs of today's group members (up to 5).

Example with today's default group:
```bash
python infographic.py --riders 12345678,23456789,34567890,45678901,56789012
```

### Solo mode (no group)
```bash
python infographic.py
```
Generates an infographic for just the authenticated athlete.

## Arguments
| Flag | Description |
|------|-------------|
| `--fetch-riders` | Scan recent kudos and list frequent contacts |
| `--riders ID1,ID2,...` | Comma-separated Strava athlete IDs for the group |
| `--date YYYY-MM-DD` | Override the date (default: today) |
| `--output PATH` | Custom output file path |

## Output
Defaults to `group_ride_YYYYMMDD.png` (1080×~1580 px) in the working dir (`infographic-group/`).
Keep finished infographics in the repo's `output/` dir by passing `--output ../output/group_ride_YYYYMMDD.png`.

## Steps Claude should follow
1. `cd /mnt/c/development/strava-utils/infographic-group` (the script reads `riders.json` relative to this dir)
2. Build the command from the invocation arguments:
   - If `$riders` is non-empty: `python infographic.py --riders $riders`
   - If `$riders` is empty: run solo mode `python infographic.py`, but first ask "Do you have the Strava athlete IDs for today's group?" unless the user clearly wants solo mode
   - If `$date` is non-empty: append `--date $date`
   - Save to the repo output dir: append `--output ../output/group_ride_$date.png` (use today's date in `YYYYMMDD` form when `$date` is omitted)
3. Run the resulting command
4. Report the output path (under `/mnt/c/development/strava-utils/output/`) and offer to display the image

**Examples** (run from `/mnt/c/development/strava-utils/infographic-group`)
- `/strava-infographic-today-group 12345678,23456789,34567890` → `python infographic.py --riders 12345678,23456789,34567890 --output ../output/group_ride_20260609.png`
- `/strava-infographic-today-group 12345678,23456789 2026-06-09` → `python infographic.py --riders 12345678,23456789 --date 2026-06-09 --output ../output/group_ride_20260609.png`
- `/strava-infographic-today-group` → solo mode (`python infographic.py`)

## Troubleshooting
- **"Strava token expired"** → Reconnect via the strava-mcp tool in Claude Code
- **"No ride activity found"** → No Ride on that date; check the date or Strava app
- **Riders show colored circles instead of photos** → Their Strava profile is private, or wrong ID
- **Missing map tiles** → Network issue fetching OSM tiles

## Dependencies
Install once:
```bash
cd /mnt/c/development/strava-utils/infographic-group
python3 -m pip install -r requirements.txt --break-system-packages
```
