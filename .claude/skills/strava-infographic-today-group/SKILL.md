# strava-infographic-today-group

Generate a WhatsApp-ready group ride infographic from today's Strava activity.

## Workflow

### Step A — One-time setup: find your group riders
```bash
cd /mnt/c/development/strava
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
Saves `group_ride_YYYYMMDD.png` (1080×~1580 px) in `/mnt/c/development/strava/`.

## Steps Claude should follow
1. `cd /mnt/c/development/strava`
2. If the user provides rider names/IDs: run `python infographic.py --riders ID1,...`
3. Otherwise ask: "Do you have the Strava athlete IDs for today's group?"
4. Report the output path and offer to display the image

## Troubleshooting
- **"Strava token expired"** → Reconnect via the strava-mcp tool in Claude Code
- **"No ride activity found"** → No Ride on that date; check the date or Strava app
- **Riders show colored circles instead of photos** → Their Strava profile is private, or wrong ID
- **Missing map tiles** → Network issue fetching OSM tiles

## Dependencies
Install once:
```bash
cd /mnt/c/development/strava
python3 -m pip install -r requirements.txt --break-system-packages
```
