"""Matplotlib chart and sparkline generation for the 3-page clinical PDF report."""

import base64
from collections.abc import Sequence
from decimal import Decimal
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

VERDICT_COLORS: dict[str, str] = {
    "improving": "#15803d",
    "worsening": "#be123c",
    "stalled": "#475569",
    "insufficient_data": "#64748b",
}


def render_sparkline_png_bytes(
    scores: Sequence[float | Decimal],
    *,
    verdict: str = "stalled",
) -> bytes:
    """Render a compact sparkline PNG showing one marker per visit score."""
    numeric_scores = [float(s) for s in scores]
    color = VERDICT_COLORS.get(verdict, "#475569")

    fig, ax = plt.subplots(figsize=(1.5, 0.42), dpi=120)
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")

    if numeric_scores:
        xs = list(range(len(numeric_scores)))
        ax.plot(
            xs,
            numeric_scores,
            color=color,
            linewidth=1.6,
            marker="o",
            markersize=3.8,
            markerfacecolor=color,
            markeredgecolor="#ffffff",
            markeredgewidth=0.6,
        )
        min_y = max(0.0, min(numeric_scores) - 8.0)
        max_y = min(100.0, max(numeric_scores) + 8.0)
        if max_y - min_y < 10.0:
            mid = (max_y + min_y) / 2.0
            min_y = max(0.0, mid - 6.0)
            max_y = min(100.0, mid + 6.0)
        ax.set_ylim(min_y, max_y)
        ax.set_xlim(-0.25, max(0.25, len(numeric_scores) - 0.75))
    else:
        ax.text(
            0.5,
            0.5,
            "No data",
            ha="center",
            va="center",
            fontsize=6,
            color="#94a3b8",
            transform=ax.transAxes,
        )

    ax.axis("off")
    plt.tight_layout(pad=0.05)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, dpi=120)
    plt.close(fig)
    return buf.getvalue()


def render_sparkline_png_base64(
    scores: Sequence[float | Decimal],
    *,
    verdict: str = "stalled",
) -> str:
    """Return a data:image/png;base64 URI for a concern sparkline."""
    png_bytes = render_sparkline_png_bytes(scores, verdict=verdict)
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_top_concern_chart_png_bytes(
    *,
    concern: str,
    label: str,
    dates: Sequence[str],
    scores: Sequence[float | Decimal],
    mdc: float,
    verdict: str,
) -> bytes:
    """Render a longitudinal trajectory chart for one of the top-3 prioritized concerns."""
    _ = concern
    numeric_scores = [float(s) for s in scores]
    color = VERDICT_COLORS.get(verdict, "#0284c7")

    fig, ax = plt.subplots(figsize=(4.4, 1.35), dpi=130)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#f8fafc")

    if numeric_scores:
        xs = list(range(len(numeric_scores)))
        base_val = numeric_scores[0]
        # Shaded baseline ± MDC band
        ax.axhspan(
            max(0.0, base_val - mdc),
            min(100.0, base_val + mdc),
            color="#cbd5e1",
            alpha=0.35,
            label=f"Baseline ± MDC ({mdc})",
        )
        ax.axhline(base_val, color="#94a3b8", linestyle="--", linewidth=0.8)

        ax.plot(
            xs,
            numeric_scores,
            color=color,
            linewidth=2.0,
            marker="o",
            markersize=5.0,
        )
        for x_idx, val in zip(xs, numeric_scores, strict=False):
            ax.annotate(
                f"{val:.1f}",
                (x_idx, val),
                textcoords="offset points",
                xytext=(0, 5),
                ha="center",
                fontsize=6.5,
                fontweight="bold",
                color="#0f172a",
            )

        ax.set_xticks(xs)
        ax.set_xticklabels(list(dates), fontsize=6.5, color="#334155")
        min_y = max(0.0, min(numeric_scores) - max(12.0, mdc * 2))
        max_y = min(100.0, max(numeric_scores) + max(14.0, mdc * 2))
        ax.set_ylim(min_y, max_y)
    else:
        ax.text(
            0.5,
            0.5,
            f"{label}: Insufficient longitudinal points",
            ha="center",
            va="center",
            fontsize=7,
            color="#64748b",
            transform=ax.transAxes,
        )

    ax.set_title(f"{label} Trajectory", fontsize=7.5, fontweight="bold", color="#0f172a", pad=3)
    ax.tick_params(axis="y", labelsize=6, colors="#475569")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#cbd5e1")

    plt.tight_layout(pad=0.3)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()


def render_top_concern_chart_png_base64(
    *,
    concern: str,
    label: str,
    dates: Sequence[str],
    scores: Sequence[float | Decimal],
    mdc: float,
    verdict: str,
) -> str:
    """Return a data:image/png;base64 URI for a top-3 concern trajectory chart."""
    png_bytes = render_top_concern_chart_png_bytes(
        concern=concern,
        label=label,
        dates=dates,
        scores=scores,
        mdc=mdc,
        verdict=verdict,
    )
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_mask_placeholder_png_bytes(concern: str, *, is_cached: bool = False) -> bytes:
    """Render a clean overlay/placeholder PNG when a concern mask image is needed."""
    fig, ax = plt.subplots(figsize=(1.1, 1.1), dpi=100)
    bg_color = "#eff6ff" if is_cached else "#f1f5f9"
    border_color = "#38bdf8" if is_cached else "#94a3b8"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    circle = plt.Circle((0.5, 0.54), 0.30, color=border_color, fill=False, linewidth=1.5, linestyle="--" if not is_cached else "-")
    ax.add_patch(circle)
    status_label = "MASK OK" if is_cached else "NO MASK"
    ax.text(
        0.5,
        0.54,
        status_label,
        ha="center",
        va="center",
        fontsize=6.5,
        fontweight="bold",
        color="#1e293b",
    )
    ax.text(
        0.5,
        0.12,
        concern[:12],
        ha="center",
        va="center",
        fontsize=5.5,
        color="#475569",
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    plt.tight_layout(pad=0.05)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    return buf.getvalue()


def render_mask_placeholder_png_base64(concern: str, *, is_cached: bool = False) -> str:
    """Return a base64 data URI for a cached or placeholder mask image."""
    png_bytes = render_mask_placeholder_png_bytes(concern, is_cached=is_cached)
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"
