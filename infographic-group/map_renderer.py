from staticmap import StaticMap, Line
from PIL import Image


ROUTE_COLOR = "#CC0000"
# Semi-transparent red (~50% opacity) for co-rider tracks; OSM roads are amber/orange
# so orange conflicts — red contrasts cleanly against both roads and tile background
_RIDER_COLOR = (0xCC, 0x00, 0x00, 128)


def render_route(
    latlng: list[list[float]],
    riders: list[dict] | None = None,
    width: int = 1080,
    height: int = 500,
) -> Image.Image:
    """
    Render the reference route (full-opacity orange) plus optional rider overlays
    in semi-transparent orange, matching Strava's group activity style.

    riders: list of {"latlng": [[lat,lon],...]}  — color field ignored, all orange
    """
    if not latlng:
        return Image.new("RGB", (width, height), "#1a1a2e")

    m = StaticMap(width, height, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    ref_coords = [(pt[1], pt[0]) for pt in latlng]
    m.add_line(Line(ref_coords, ROUTE_COLOR, 4))

    for rider in (riders or []):
        r_latlng = rider.get("latlng", [])
        if not r_latlng:
            continue
        r_coords = [(pt[1], pt[0]) for pt in r_latlng]
        m.add_line(Line(r_coords, _RIDER_COLOR, 3))

    return m.render()
