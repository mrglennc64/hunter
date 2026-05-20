"""
Bounty Calculator
Converts stream counts into dollar estimates using SoundExchange statutory rates.
Rate: $0.0012 (conservative) to $0.0018 (high-end) per stream.
"""

import re


RATE_LOW  = 0.0012   # Conservative SoundExchange performance rate
RATE_HIGH = 0.0018   # High-end estimate


def parse_streams(streams_str: str) -> int:
    """
    Convert '12.4M', '500K', '1,200,000' or raw int to integer.
    Returns 0 if unparseable.
    """
    if not streams_str:
        return 0

    s = str(streams_str).upper().replace(",", "").replace(" ", "").strip()

    multiplier = 1
    if "B" in s:
        multiplier = 1_000_000_000
        s = s.replace("B", "")
    elif "M" in s:
        multiplier = 1_000_000
        s = s.replace("M", "")
    elif "K" in s:
        multiplier = 1_000
        s = s.replace("K", "")

    try:
        return int(float(s) * multiplier)
    except ValueError:
        return 0


def calculate_bounty(streams_input, artist: str = "", track: str = "") -> dict:
    """
    Calculate bounty value from stream count.

    Args:
        streams_input: int, or string like '12.4M' / '500K'
        artist: artist name (for display)
        track:  track title (for display)

    Returns dict with:
        raw_streams, low, high, low_fmt, high_fmt, priority
    """
    if isinstance(streams_input, (int, float)):
        raw = int(streams_input)
    else:
        raw = parse_streams(streams_input)

    low  = raw * RATE_LOW
    high = raw * RATE_HIGH

    # Priority tier based on estimated value
    if high >= 10_000:
        priority = "TIER 1 — WHALE"
    elif high >= 2_000:
        priority = "TIER 2 — SOLID"
    elif high >= 500:
        priority = "TIER 3 — SMALL"
    else:
        priority = "TIER 4 — MICRO"

    return {
        "artist":      artist,
        "track":       track,
        "raw_streams": raw,
        "low":         round(low, 2),
        "high":        round(high, 2),
        "low_fmt":     f"${low:,.2f}",
        "high_fmt":    f"${high:,.2f}",
        "priority":    priority,
    }


def enrich_leads_with_bounty(leads: list, stream_col: str = "streams") -> list:
    """
    Take a list of lead dicts (from leads.csv) and add bounty estimates.
    Only enriches JACKPOT and GUEST_UNCLAIMED rows.
    """
    enriched = []
    for lead in leads:
        status = lead.get("status", "")
        if status in ("JACKPOT", "GUEST_UNCLAIMED"):
            streams = lead.get(stream_col, 0) or 0
            bounty = calculate_bounty(
                streams,
                artist=lead.get("artist", ""),
                track=lead.get("track", ""),
            )
            lead["bounty_low"]  = bounty["low_fmt"]
            lead["bounty_high"] = bounty["high_fmt"]
            lead["priority"]    = bounty["priority"]
        enriched.append(lead)
    return enriched


if __name__ == "__main__":
    # Quick test
    tests = [
        ("Doja Cat",         "Agora Hills",        "48M"),
        ("Tyla",             "Water",              "120M"),
        ("Sexyy Red",        "Rich Baby Daddy",    "35M"),
        ("Kane Brown",       "Miles On It",        "22M"),
        ("Jessie Murph",     "Wild Ones",          "8M"),
    ]

    print(f"\n{'Artist':<25} {'Track':<30} {'Streams':>10}  {'Low':>12}  {'High':>12}  Priority")
    print("-" * 105)
    for artist, track, streams in tests:
        b = calculate_bounty(streams, artist, track)
        print(f"{artist:<25} {track:<30} {b['raw_streams']:>10,}  {b['low_fmt']:>12}  {b['high_fmt']:>12}  {b['priority']}")
