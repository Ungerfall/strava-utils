import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator
from PIL import Image

ATHLETE_PALETTE = ["#FC4C02", "#1E90FF", "#2ECC71", "#FFD700"]
PANEL_BG = "#1a1a2e"
GRID_COLOR = "#2d2d4e"
TEXT_COLOR = "#e0e0e0"
LABEL_COLOR = "#aaaaaa"


def _km_ticks(n_km: int) -> list[int]:
    step = max(1, n_km // 12)
    return list(range(step, n_km + 1, step))


def render_chart(athletes: list[dict], canvas_width: int = 1080, canvas_height: int = 560) -> Image.Image:
    """
    athletes: list of dicts with keys:
      - name: str
      - color: str
      - km_data: {metric: [val_per_km]}  metrics: watts, cadence, heartrate
      - device_watts: bool
    Returns a PIL Image.
    """
    dpi = 100
    fig_w = canvas_width / dpi
    fig_h = canvas_height / dpi

    has_power = any(a.get("device_watts") and "watts" in a.get("km_data", {}) for a in athletes)
    panels = []
    if has_power:
        panels.append(("watts", "Power (W)", "#FC4C02"))
    panels.append(("cadence", "Cadence (rpm)", "#1E90FF"))
    panels.append(("heartrate", "Heart Rate (bpm)", "#E74C3C"))

    n_panels = len(panels)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=PANEL_BG)
    gs = gridspec.GridSpec(n_panels, 1, figure=fig, hspace=0.12,
                           top=0.97, bottom=0.08, left=0.06, right=0.98)

    n_km = max(
        (len(v) for a in athletes for v in a.get("km_data", {}).values()),
        default=0
    )
    x = list(range(1, n_km + 1))

    for idx, (metric, ylabel, _panel_color) in enumerate(panels):
        ax = fig.add_subplot(gs[idx])
        ax.set_facecolor(PANEL_BG)
        ax.tick_params(colors=TEXT_COLOR, labelsize=7)
        ax.yaxis.label.set_color(LABEL_COLOR)
        ax.set_ylabel(ylabel, fontsize=8, color=LABEL_COLOR)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID_COLOR)
        ax.grid(True, color=GRID_COLOR, linewidth=0.5, linestyle="--", alpha=0.6)

        drawn = False
        for athlete in athletes:
            km_data = athlete.get("km_data", {})
            color = athlete["color"]
            vals = km_data.get(metric)
            if not vals:
                if metric == "watts" and not athlete.get("device_watts"):
                    # draw flat dashed line to indicate no power meter
                    ax.axhline(0, color=color, linewidth=1, linestyle=":", alpha=0.4)
                continue
            # fill None gaps with linear interpolation for display
            clean = _interpolate_nones(vals)
            ax.plot(x[:len(clean)], clean, color=color, linewidth=2, solid_capstyle="round")
            drawn = True

        if not drawn and metric == "watts":
            ax.set_ylim(0, 1)
            ax.text(0.5, 0.5, "No power meter data", transform=ax.transAxes,
                    ha="center", va="center", color=LABEL_COLOR, fontsize=9)

        ax.set_xlim(0.5, n_km + 0.5)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=12))

        if idx < n_panels - 1:
            ax.set_xticklabels([])
        else:
            ax.set_xlabel("Distance (km)", fontsize=8, color=LABEL_COLOR)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=PANEL_BG)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).copy()


def _interpolate_nones(values: list) -> list:
    result = list(values)
    for i, v in enumerate(result):
        if v is None:
            prev = next((result[j] for j in range(i - 1, -1, -1) if result[j] is not None), None)
            nxt = next((result[j] for j in range(i + 1, len(result)) if result[j] is not None), None)
            if prev is not None and nxt is not None:
                result[i] = (prev + nxt) / 2
            elif prev is not None:
                result[i] = prev
            elif nxt is not None:
                result[i] = nxt
            else:
                result[i] = 0
    return result
