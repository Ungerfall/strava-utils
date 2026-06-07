from staticmap import StaticMap, Line
from PIL import Image
import io


STRAVA_ORANGE = "#FC4C02"


def render_route(latlng: list[list[float]], width: int = 1080, height: int = 500) -> Image.Image:
    """Render a route polyline on an OSM map tile and return a PIL Image."""
    if not latlng:
        return Image.new("RGB", (width, height), "#1a1a2e")

    m = StaticMap(width, height, url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    # staticmap expects (lon, lat) pairs
    coords = [(pt[1], pt[0]) for pt in latlng]
    line = Line(coords, STRAVA_ORANGE, 4)
    m.add_line(line)

    img_bytes = m.render()
    return img_bytes
