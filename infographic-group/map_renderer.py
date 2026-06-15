from staticmap import StaticMap, Line
from PIL import Image


ROUTE_COLOR = "#8B2BE2"
_RIDER_COLOR = (0x8B, 0x2B, 0xE2, 128)


def render_route(
    latlng: list[list[float]],
    riders: list[dict] | None = None,
    width: int = 1080,
    height: int = 500,
) -> Image.Image:
    """
    riders: list of {"latlng": [[lat,lon],...]}
    """
    if not latlng:
        return Image.new("RGB", (width, height), "#1a1a2e")

    m = StaticMap(width, height, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    ref_coords = [(pt[1], pt[0]) for pt in latlng]

    for rider in (riders or []):
        r_latlng = rider.get("latlng", [])
        if not r_latlng:
            continue
        r_coords = [(pt[1], pt[0]) for pt in r_latlng]
        m.add_line(Line(r_coords, _RIDER_COLOR, 3))

    m.add_line(Line(ref_coords, ROUTE_COLOR, 4))

    return m.render()
