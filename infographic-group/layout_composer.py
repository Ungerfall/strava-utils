import io
import math
import datetime
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from PIL import Image, ImageDraw, ImageFont

EMOJI_FONT_PATH = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

BG_DARK = (18, 18, 35)
BG_PANEL = (26, 26, 46)
BG_TILE = (32, 32, 56)
STRAVA_ORANGE = (252, 76, 2)
ORANGE_HEX = "#FC4C02"
TEXT_WHITE = (230, 230, 230)
TEXT_GREY = (160, 160, 160)
PLACEHOLDER_BORDER = (80, 80, 110)

CANVAS_W = 1080
HEADER_H = 110
STATS_H = 100
MAP_H = 500
ELEV_H = 180
RIDERS_H = 130
CHART_H = 560
PHOTO_H = 810  # 4:3 ratio at 1080 px wide

ATHLETE_COLORS_RGB = [
    (252, 76, 2),
    (30, 144, 255),
    (46, 204, 113),
    (255, 215, 0),
    (220, 80, 220),
    (0, 210, 210),
    (255, 107, 107),
    (163, 230, 53),
]


# ── Fonts ────────────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except Exception:
        return ImageFont.load_default()


# ── Matplotlib icon factory ───────────────────────────────────────────────────

def _make_icon(kind: str, size: int = 36, color: str = ORANGE_HEX) -> Image.Image:
    dpi = 100
    fs = (size * 2) / dpi
    fig, ax = plt.subplots(figsize=(fs, fs), facecolor="none")
    ax.set_facecolor("none")
    ax.set_xlim(0, 10); ax.set_ylim(0, 10)
    ax.axis("off")
    lw = 1.8

    if kind == "bike":
        # Wheels
        r_w = mpatches.Circle((2.2, 3.0), 2.0, fill=False, color=color, linewidth=lw)
        f_w = mpatches.Circle((7.8, 3.0), 2.0, fill=False, color=color, linewidth=lw)
        ax.add_patch(r_w); ax.add_patch(f_w)
        # Frame: rear-axle → BB → front-axle, seat-tube, top-tube, down-tube
        bb = (4.8, 3.0)
        seat_top = (3.6, 6.2)
        head_top = (7.0, 6.2)
        for seg in [
            (2.2, 3.0, bb[0], bb[1]),           # chain stay
            (bb[0], bb[1], seat_top[0], seat_top[1]),  # seat tube
            (seat_top[0], seat_top[1], head_top[0], head_top[1]),  # top tube
            (head_top[0], head_top[1], bb[0], bb[1]),  # down tube
            (2.2, 3.0, seat_top[0], seat_top[1]),       # seat stay
            (head_top[0], head_top[1], 7.8, 3.0),        # fork
        ]:
            ax.plot([seg[0], seg[2]], [seg[1], seg[3]], color=color, lw=lw, solid_capstyle="round")
        # Seat (horizontal bar above seat tube)
        ax.plot([3.0, 4.4], [6.5, 6.5], color=color, lw=lw + 0.5, solid_capstyle="round")
        # Handlebars (T at head tube top)
        ax.plot([6.5, 7.5], [6.7, 6.7], color=color, lw=lw + 0.3, solid_capstyle="round")
        ax.plot([7.0, 7.0], [6.2, 6.7], color=color, lw=lw, solid_capstyle="round")

    elif kind == "road":
        # Ruler: body + tick marks
        ruler = mpatches.FancyBboxPatch((0.8, 3.8), 8.4, 2.2,
                                         boxstyle="round,pad=0.25",
                                         fill=False, edgecolor=color, linewidth=lw)
        ax.add_patch(ruler)
        for i, x in enumerate([2.0, 3.3, 4.6, 5.9, 7.2]):
            tick_h = 1.1 if i % 2 == 0 else 0.65
            ax.plot([x, x], [6.0, 6.0 + tick_h], color=color, lw=lw - 0.4, solid_capstyle="round")

    elif kind == "clock":
        circle = mpatches.Circle((5, 5), 4, fill=False, color=color, linewidth=lw)
        ax.add_patch(circle)
        ax.plot([5, 5], [5, 8.5], color=color, lw=lw, solid_capstyle="round")   # minute (12)
        ax.plot([5, 7.5], [5, 6.2], color=color, lw=lw, solid_capstyle="round") # hour  (~2)

    elif kind == "mountain":
        xs = [1, 5, 9, 1]
        ys = [1, 8.5, 1, 1]
        ax.fill(xs, ys, color=color, alpha=0.85)
        ax.plot([3.5, 5.5], [5.2, 7.5], color="white", lw=lw - 0.5, alpha=0.5)  # snow line

    elif kind == "speed":
        arc = mpatches.Arc((5, 4), 7, 7, angle=0, theta1=0, theta2=180,
                            color=color, linewidth=lw)
        ax.add_patch(arc)
        angle = math.radians(130)
        ax.plot([5, 5 + 3.2 * math.cos(angle)], [4, 4 + 3.2 * math.sin(angle)],
                color=color, lw=lw + 0.3, solid_capstyle="round")
        ax.plot([5], [4], "o", color=color, markersize=4)
        # tick marks
        for deg in [0, 45, 90, 135, 180]:
            a = math.radians(deg)
            ax.plot([5 + 3.1 * math.cos(a), 5 + 3.7 * math.cos(a)],
                    [4 + 3.1 * math.sin(a), 4 + 3.7 * math.sin(a)],
                    color=color, lw=lw - 0.8, alpha=0.6)

    elif kind == "thermometer":
        # Tube
        rect = mpatches.FancyBboxPatch((3.8, 3.5), 2.4, 5.5,
                                        boxstyle="round,pad=0.3",
                                        fill=False, edgecolor=color, linewidth=lw)
        ax.add_patch(rect)
        # Bulb
        bulb = mpatches.Circle((5, 3.0), 1.8, fill=True, facecolor=color, edgecolor=color)
        ax.add_patch(bulb)
        # Mercury fill
        ax.fill_between([4.2, 5.8], [3.5, 3.5], [7.5, 7.5], color=color, alpha=0.6)

    elif kind == "camera":
        # Body
        body = mpatches.FancyBboxPatch((1, 2.5), 8, 5.5,
                                        boxstyle="round,pad=0.4",
                                        fill=False, edgecolor=color, linewidth=lw)
        ax.add_patch(body)
        # Lens
        lens = mpatches.Circle((5, 5.2), 1.8, fill=False, edgecolor=color, linewidth=lw)
        ax.add_patch(lens)
        lens2 = mpatches.Circle((5, 5.2), 0.8, fill=False, edgecolor=color, linewidth=lw - 0.6)
        ax.add_patch(lens2)
        # Viewfinder bump
        bump = mpatches.FancyBboxPatch((3.5, 7.7), 3, 1.2,
                                        boxstyle="round,pad=0.2",
                                        fill=False, edgecolor=color, linewidth=lw)
        ax.add_patch(bump)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True,
                bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA").resize((size, size), Image.LANCZOS).copy()


# ── Avatar helpers ────────────────────────────────────────────────────────────

def _circle_crop(img: Image.Image, size: int, ring_color: tuple) -> Image.Image:
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    ring_w = max(3, size // 18)
    ImageDraw.Draw(out).ellipse((0, 0, size - 1, size - 1), outline=ring_color, width=ring_w)
    return out


def _fetch_avatar(url: str, size: int, local_path: str = "") -> Image.Image | None:
    if local_path:
        try:
            return Image.open(local_path)
        except Exception:
            pass
    if not url:
        return None
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content))
    except Exception:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m:02d}m"


def _parse_date(s: str) -> datetime.datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _paste_icon(canvas: Image.Image, icon: Image.Image, cx: int, cy: int) -> None:
    x = cx - icon.width // 2
    y = cy - icon.height // 2
    canvas.paste(icon, (x, y), mask=icon.split()[3])


def _centered_text(draw: ImageDraw.ImageDraw, cx: int, y: int, text: str,
                   font: ImageFont.FreeTypeFont, fill: tuple) -> None:
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=fill)


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FFFF or 0x2600 <= cp <= 0x27BF or
            0xFE00 <= cp <= 0xFE0F or 0x1F300 <= cp <= 0x1FAFF)


_EMOJI_NATIVE_SIZE = 109  # NotoColorEmoji only has one embedded bitmap size


def _render_emoji_segment(seg: str, target_h: int) -> Image.Image | None:
    """Render an emoji string at native size then scale to target_h."""
    try:
        e_font = ImageFont.truetype(EMOJI_FONT_PATH, _EMOJI_NATIVE_SIZE)
    except Exception:
        return None
    tmp = Image.new("RGBA", (len(seg) * _EMOJI_NATIVE_SIZE + 10, _EMOJI_NATIVE_SIZE + 20), (0, 0, 0, 0))
    bb = ImageDraw.Draw(tmp).textbbox((0, 0), seg, font=e_font, embedded_color=True)
    w, h = max(bb[2] - bb[0], 1), max(bb[3] - bb[1], 1)
    glyph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((-bb[0], -bb[1]), seg, font=e_font, embedded_color=True)
    scale = target_h / h
    new_w = max(int(w * scale), 1)
    return glyph.resize((new_w, target_h), Image.LANCZOS)


def _draw_text_mixed(canvas: Image.Image, x: int, y: int, text: str,
                     font: ImageFont.FreeTypeFont, fill: tuple) -> None:
    """Draw text, routing emoji chars to NotoColorEmoji and the rest to the given font."""
    segments: list[tuple[str, bool]] = []
    cur, cur_e = "", False
    for ch in text:
        is_e = _is_emoji(ch)
        if cur and is_e != cur_e:
            segments.append((cur, cur_e))
            cur = ""
        cur_e = is_e
        cur += ch
    if cur:
        segments.append((cur, cur_e))

    draw = ImageDraw.Draw(canvas)
    cx = x
    for seg, is_e in segments:
        if is_e:
            bb_ref = draw.textbbox((0, 0), "A", font=font)
            target_h = bb_ref[3] - bb_ref[1]
            glyph = _render_emoji_segment(seg, target_h)
            if glyph:
                canvas.paste(glyph.convert("RGB"), (cx, y), mask=glyph.split()[3])
                cx += glyph.width + 2
            else:
                draw.text((cx, y), seg, font=font, fill=fill)
                bb = draw.textbbox((0, 0), seg, font=font)
                cx += bb[2] - bb[0]
        else:
            draw.text((cx, y), seg, font=font, fill=fill)
            bb = draw.textbbox((0, 0), seg, font=font)
            cx += bb[2] - bb[0]


def _dashed_rect(draw: ImageDraw.ImageDraw, x0, y0, x1, y1, color, dash=18, gap=10):
    for (ax, ay), (bx, by) in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),
                                 ((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]:
        length = math.hypot(bx - ax, by - ay)
        if not length: continue
        dx, dy = (bx - ax) / length, (by - ay) / length
        pos, on = 0, True
        while pos < length:
            end = min(pos + (dash if on else gap), length)
            if on:
                draw.line([(ax + dx*pos, ay + dy*pos), (ax + dx*end, ay + dy*end)],
                          fill=color, width=2)
            pos, on = end, not on


# ── Main compose ─────────────────────────────────────────────────────────────

def compose(activity: dict, map_img: Image.Image,
            elev_img: Image.Image, athletes: list[dict],
            chart_img: Image.Image | None = None,
            photo_placeholder: bool = False,
            title: str = "") -> Image.Image:

    n_riders = len(athletes)
    n_rows = 2 if n_riders > 5 else 1
    actual_riders_h = RIDERS_H * n_rows
    actual_header_h = HEADER_H + 34 if title else HEADER_H

    total_h = actual_header_h + STATS_H + MAP_H + ELEV_H + actual_riders_h
    if chart_img is not None:
        total_h += CHART_H
    if photo_placeholder:
        total_h += PHOTO_H
    canvas = Image.new("RGB", (CANVAS_W, total_h), BG_DARK)
    draw = ImageDraw.Draw(canvas)

    # Pre-render icons once
    icons = {k: _make_icon(k, 36) for k in ("bike", "road", "clock", "mountain", "speed",
                                              "thermometer", "camera")}

    # ── Header ───────────────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (CANVAS_W, actual_header_h)], fill=BG_PANEL)
    draw.rectangle([(0, 0), (CANVAS_W, 5)], fill=STRAVA_ORANGE)

    bike = _make_icon("bike", 56)
    _paste_icon(canvas, bike, 54, actual_header_h // 2 + 2)

    start_dt = _parse_date(activity.get("start_date_local", ""))
    date_str = start_dt.strftime("%A, %d %b %Y") if start_dt else "Today"

    if title:
        label_font = _font(20)
        title_font = _font(30, bold=True)
        date_font = _font(19)
        draw.text((100, 10), "GROUP RIDE", font=label_font, fill=STRAVA_ORANGE)
        _draw_text_mixed(canvas, 100, 36, title, title_font, TEXT_WHITE)
        draw.text((100, 74), date_str, font=date_font, fill=TEXT_GREY)
    else:
        title_font = _font(36, bold=True)
        date_font = _font(22)
        draw.text((100, 14), "GROUP RIDE", font=title_font, fill=STRAVA_ORANGE)
        draw.text((100, 58), date_str, font=date_font, fill=TEXT_WHITE)

    # ── Stats strip ──────────────────────────────────────────────────────────
    sy = actual_header_h
    draw.rectangle([(0, sy), (CANVAS_W, sy + STATS_H)], fill=BG_DARK)

    dist_km = activity.get("distance", 0) / 1000
    duration = activity.get("moving_time", 0)
    elev = activity.get("total_elevation_gain", 0)
    avg_speed = activity.get("average_speed", 0) * 3.6
    temp = activity.get("average_temp")

    tiles = [
        ("road",        f"{dist_km:.1f} km",          "Distance"),
        ("clock",       _format_duration(duration),    "Duration"),
        ("mountain",    f"{elev:.0f} m",               "Elevation"),
        ("speed",       f"{avg_speed:.1f} km/h",       "Avg Speed"),
    ]
    if temp:
        tiles.append(("thermometer", f"{temp:.0f} °C", "Temp"))

    n = len(tiles)
    tile_w = CANVAS_W // n
    val_font = _font(24, bold=True)
    lbl_font = _font(15)

    for i, (icon_key, value, label) in enumerate(tiles):
        cx = tile_w * i + tile_w // 2
        # subtle tile separator
        if i > 0:
            draw.line([(tile_w * i, sy + 12), (tile_w * i, sy + STATS_H - 12)],
                      fill=(50, 50, 72), width=1)
        _paste_icon(canvas, icons[icon_key], cx, sy + 22)
        _centered_text(draw, cx, sy + 46, value, val_font, TEXT_WHITE)
        _centered_text(draw, cx, sy + 76, label, lbl_font, TEXT_GREY)

    # ── Route map ────────────────────────────────────────────────────────────
    my = actual_header_h + STATS_H
    map_resized = map_img.resize((CANVAS_W, MAP_H), Image.LANCZOS).convert("RGB")
    canvas.paste(map_resized, (0, my))

    # ── Elevation profile ────────────────────────────────────────────────────
    ey = my + MAP_H
    elev_resized = elev_img.resize((CANVAS_W, ELEV_H), Image.LANCZOS).convert("RGB")
    canvas.paste(elev_resized, (0, ey))

    # ── Riders ───────────────────────────────────────────────────────────────
    ry = ey + ELEV_H
    draw.rectangle([(0, ry), (CANVAS_W, ry + actual_riders_h)], fill=BG_PANEL)

    av_size = 70
    name_font = _font(17, bold=True)

    per_row = math.ceil(n_riders / n_rows) if n_rows > 1 else n_riders
    rows = [athletes[i:i + per_row] for i in range(0, n_riders, per_row)]

    for row_idx, row_athletes in enumerate(rows):
        row_y = ry + row_idx * RIDERS_H
        slot_w = CANVAS_W // len(row_athletes)
        for col_idx, athlete in enumerate(row_athletes):
            i = row_idx * per_row + col_idx
            cx = slot_w * col_idx + slot_w // 2
            color_rgb = ATHLETE_COLORS_RGB[i % len(ATHLETE_COLORS_RGB)]
            av_y = row_y + 10

            av_raw = _fetch_avatar(athlete.get("avatar_url", ""), av_size, athlete.get("avatar_path", ""))
            if av_raw:
                av_circle = _circle_crop(av_raw, av_size, color_rgb)
                canvas.paste(av_circle, (cx - av_size // 2, av_y), mask=av_circle.split()[3])
            else:
                draw.ellipse([(cx - av_size//2, av_y),
                              (cx + av_size//2, av_y + av_size)], fill=color_rgb)

            name = athlete.get("name", "")[:14]
            _centered_text(draw, cx, av_y + av_size + 4, name, name_font, TEXT_WHITE)

    # ── Performance charts ────────────────────────────────────────────────────
    if chart_img is not None:
        cy = ry + actual_riders_h
        chart_resized = chart_img.resize((CANVAS_W, CHART_H), Image.LANCZOS).convert("RGB")
        canvas.paste(chart_resized, (0, cy))
        py = cy + CHART_H
    else:
        py = ry + actual_riders_h

    # ── Photo placeholder (opt-in) ────────────────────────────────────────────
    if photo_placeholder:
        draw.rectangle([(0, py), (CANVAS_W, py + PHOTO_H)], fill=BG_DARK)
        margin = 20
        _dashed_rect(draw, margin, py + margin, CANVAS_W - margin, py + PHOTO_H - margin,
                     PLACEHOLDER_BORDER)

        cam_big = _make_icon("camera", 52)
        _paste_icon(canvas, cam_big, CANVAS_W // 2 - 80, py + PHOTO_H // 2)

        ph_font = _font(24)
        ph_sub_font = _font(16)
        draw.text((CANVAS_W // 2 - 50, py + PHOTO_H // 2 - 22),
                  "Add group photo here", font=ph_font, fill=PLACEHOLDER_BORDER)
        from math import gcd
        _g = gcd(CANVAS_W, PHOTO_H)
        ratio_label = f"{CANVAS_W} × {PHOTO_H} px  ({CANVAS_W // _g}:{PHOTO_H // _g})"
        draw.text((CANVAS_W // 2 - 50, py + PHOTO_H // 2 + 12),
                  ratio_label, font=ph_sub_font, fill=PLACEHOLDER_BORDER)

    return canvas
