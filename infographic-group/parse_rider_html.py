#!/usr/bin/env python3
"""Parse Chrome-saved Strava athlete profile pages and update riders.json.

For each riders/{id}/ folder containing a saved .html file:
  - Extracts full name, location, member-since from the static HTML
  - Finds the profile photo URL from AvatarWrapper data-react-props
  - Downloads the photo to riders/{id}/avatar.jpg
  - Merges the data into riders.json

Usage:
    python3 parse_rider_html.py
"""

import json
import re
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

RIDERS_JSON = Path("riders.json")
RIDERS_DIR = Path("riders")


def parse_html(html_path: Path, athlete_id: int) -> dict:
    with open(html_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    info = {"id": athlete_id}

    # Full name from h1
    h1 = soup.find("h1", class_="athlete-name")
    if h1:
        info["fullname"] = h1.get_text(strip=True)
        member_since = h1.get("title", "")
        if member_since:
            info["member_since"] = member_since.replace("Member Since: ", "")

    # Location
    loc_div = soup.find("div", class_="location")
    if loc_div:
        text = loc_div.get_text(strip=True)
        if text:
            info["location"] = text

    # Profile photo — find AvatarWrapper with size=xlarge for this athlete
    photo_url = None
    for el in soup.find_all(attrs={"data-react-class": "AvatarWrapper"}):
        props_str = el.get("data-react-props", "")
        try:
            props = json.loads(props_str)
        except json.JSONDecodeError:
            continue
        if props.get("type") != "athlete":
            continue
        href = props.get("href", "")
        src = props.get("src", "")
        if not src:
            continue
        # Prefer xlarge; accept any size tied to this athlete's ID
        if str(athlete_id) in href or str(athlete_id) in src:
            if props.get("size") == "xlarge":
                photo_url = src
                break
            elif photo_url is None:
                photo_url = src

    if photo_url:
        info["avatar_url"] = photo_url

    return info


def download_avatar(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"  [warn] Could not download {url}: {e}")
        return False


def load_riders() -> list:
    if RIDERS_JSON.exists():
        return json.loads(RIDERS_JSON.read_text(encoding="utf-8"))
    return []


def save_riders(riders: list) -> None:
    RIDERS_JSON.write_text(
        json.dumps(riders, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def find_rider(riders: list, athlete_id: int) -> dict | None:
    for r in riders:
        if r.get("id") == athlete_id:
            return r
    return None


def main():
    if not RIDERS_DIR.exists():
        print("No riders/ directory found.")
        return

    riders = load_riders()
    updated = 0

    for id_dir in sorted(RIDERS_DIR.iterdir()):
        if not id_dir.is_dir():
            continue
        try:
            athlete_id = int(id_dir.name)
        except ValueError:
            continue

        html_files = list(id_dir.glob("*.html"))
        if not html_files:
            print(f"[{athlete_id}] No HTML file found, skipping.")
            continue

        html_path = html_files[0]
        print(f"[{athlete_id}] Parsing {html_path.name} …")

        info = parse_html(html_path, athlete_id)
        print(f"  name: {info.get('fullname')}  location: {info.get('location')}")

        # Download avatar
        if "avatar_url" in info:
            avatar_path = id_dir / "avatar.jpg"
            if download_avatar(info["avatar_url"], avatar_path):
                info["avatar_path"] = str(avatar_path)
                print(f"  avatar: {avatar_path}")
            del info["avatar_url"]

        # Merge into riders list
        existing = find_rider(riders, athlete_id)
        if existing is None:
            riders.append(info)
            print(f"  → Added new entry.")
        else:
            existing.update(info)
            print(f"  → Updated existing entry.")

        updated += 1

    save_riders(riders)
    print(f"\nDone. {updated} rider(s) processed → riders.json updated.")


if __name__ == "__main__":
    main()
