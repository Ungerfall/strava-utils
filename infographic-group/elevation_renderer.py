import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from PIL import Image

BG = "#1a1a2e"
ORANGE = "#FC4C02"
LINE_COLOR = "#ffffff"
TEXT_COLOR = "#aaaaaa"


def render_elevation(streams: dict, canvas_width: int = 1080, canvas_height: int = 180) -> Image.Image:
    alt = streams.get("altitude", [])
    dist = streams.get("distance", [])

    dpi = 100
    fig, ax = plt.subplots(figsize=(canvas_width / dpi, canvas_height / dpi), facecolor=BG)
    ax.set_facecolor(BG)

    if not alt or not dist:
        ax.axis("off")
    else:
        dist_km = [d / 1000 for d in dist]

        # Smooth with a rolling average
        window = max(1, len(alt) // 100)
        alt_smooth = np.convolve(alt, np.ones(window) / window, mode="same")

        # Gradient fill: stack thin horizontal bands from bottom to line
        n_bands = 60
        alt_min = min(alt_smooth)
        for i in range(n_bands):
            frac = i / n_bands
            alpha = 0.08 + 0.55 * frac
            y_bot = alt_min + frac * (alt_smooth - alt_min)
            y_top = alt_min + (frac + 1 / n_bands) * (alt_smooth - alt_min)
            ax.fill_between(dist_km, y_bot, y_top, color=ORANGE, alpha=alpha, linewidth=0)

        # Top edge line
        ax.plot(dist_km, alt_smooth, color=LINE_COLOR, linewidth=1.2, alpha=0.9)

        ax.set_xlim(dist_km[0], dist_km[-1])
        alt_range = max(alt_smooth) - alt_min
        ax.set_ylim(alt_min - alt_range * 0.05, max(alt_smooth) + alt_range * 0.15)

        ax.tick_params(axis="both", colors=TEXT_COLOR, labelsize=8)
        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f km"))
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.0fm"))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=4, integer=True))

        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(length=0)
        ax.grid(axis="y", color="#2d2d4e", linewidth=0.5, linestyle="--", alpha=0.5)

    plt.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).copy()
