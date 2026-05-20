"""
ROI Chart Generator
Produces a high-res JPG bar chart for each lead.
Used as the "Value Proof" attachment in outreach emails.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import matplotlib
matplotlib.use("Agg")   # Non-interactive backend (works on VPS with no display)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from outreach.bounty_calculator import calculate_bounty, parse_streams

CHARTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

# TrapRoyalties brand colors
COLOR_FEE  = "#FF4444"   # Red  — audit fee
COLOR_LOW  = "#00C851"   # Green — conservative recovery
COLOR_HIGH = "#007E33"   # Dark green — high-end recovery
BG_COLOR   = "#0f172a"   # Dark navy background
TEXT_COLOR = "#F8FAFC"


def generate_roi_chart(
    artist: str,
    track: str,
    streams_input,
    audit_fee: float = 150.0,
    output_dir: str = None,
) -> str:
    """
    Generate a branded ROI bar chart JPG.

    Returns the file path to the saved chart.
    """
    output_dir = output_dir or CHARTS_DIR
    bounty = calculate_bounty(streams_input, artist, track)

    low  = bounty["low"]
    high = bounty["high"]

    labels = ["Audit Fee", "Est. Min. Recovery", "Est. Max. Recovery"]
    values = [audit_fee, low, high]
    colors = [COLOR_FEE, COLOR_LOW, COLOR_HIGH]

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    bars = ax.bar(labels, values, color=colors, edgecolor="#334155", linewidth=1.2,
                  width=0.5)

    # Title
    ax.set_title(
        f"CONFIDENTIAL RECOVERY AUDIT\n{artist.upper()} — {track}",
        fontsize=15,
        fontweight="bold",
        color=TEXT_COLOR,
        pad=18,
    )

    ax.set_ylabel("Estimated Value (USD)", fontsize=12, color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=11)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Grid
    ax.yaxis.grid(True, linestyle="--", alpha=0.25, color=TEXT_COLOR)
    ax.set_axisbelow(True)

    # Remove top/right spines
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color("#334155")

    # Value labels on bars
    for bar, val in zip(bars, values):
        ax.annotate(
            f"${val:,.2f}",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color=TEXT_COLOR,
        )

    # ROI note
    if low > 0:
        roi_x = round((low / audit_fee) * 100)
        fig.text(
            0.5, 0.01,
            f"Estimated ROI: {roi_x}x  |  {bounty['priority']}  |  "
            f"{bounty['raw_streams']:,} streams",
            ha="center",
            fontsize=9,
            color="#94A3B8",
        )

    plt.tight_layout(rect=[0, 0.04, 1, 1])

    safe_name = f"{artist.replace(' ', '_')}_{track.replace(' ', '_')[:20]}_ROI.jpg"
    out_path = os.path.join(output_dir, safe_name)
    plt.savefig(out_path, dpi=120, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close()

    print(f"[CHART] Saved → {out_path}")
    return out_path


def batch_charts_from_leads(leads_path: str, stream_col: str = "streams"):
    """
    Read leads.csv and generate a chart for every JACKPOT / GUEST_UNCLAIMED row.
    """
    import csv

    with open(leads_path, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    charts = []
    for lead in leads:
        if lead.get("status") not in ("JACKPOT", "GUEST_UNCLAIMED"):
            continue
        artist  = lead.get("artist", "Unknown")
        track   = lead.get("track", "Unknown")
        streams = lead.get(stream_col, 0) or 0
        path = generate_roi_chart(artist, track, streams)
        charts.append(path)

    print(f"[CHART] {len(charts)} charts generated → {CHARTS_DIR}")
    return charts


if __name__ == "__main__":
    # Test with known leads
    test_leads = [
        ("Doja Cat",     "Agora Hills",     "48M"),
        ("Tyla",         "Water",           "120M"),
        ("Sexyy Red",    "Rich Baby Daddy", "35M"),
        ("Beyonce",      "Texas Hold Em",   "200M"),
    ]
    for artist, track, streams in test_leads:
        generate_roi_chart(artist, track, streams)
