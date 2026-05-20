"""
Sniper Filters
Scores each track for probability of being unclaimed on SoundExchange.
Higher score = probe this first.

Three target profiles from the PDF:
  1. "Signed but Missing"  — indie label, 2024-2025 release
  2. "Viral Orphan"        — one big hit, back-office hasn't caught up
  3. "Remix Hunt"          — remixing artist often unclaimed even when original is not
"""

MAJOR_LABELS = [
    "universal", "sony", "warner", "atlantic", "def jam",
    "interscope", "capitol", "rca", "republic", "columbia",
    "epic", "island", "motown", "cash money", "quality control",
    "wmg", "umg", "smeg",
]

TIER2_ARTISTS = [
    # High-volume artists known to have metadata gaps
    "bossman dlow", "42 dugg", "rylo rodriguez", "est gee",
    "real boston richey", "veeze", "anycia", "young dro", "zaytoven",
    "leon thomas", "doechii",
]


def is_indie(label: str) -> bool:
    label_lower = label.lower()
    return not any(ml in label_lower for ml in MAJOR_LABELS)


def is_recent(release_date: str) -> bool:
    try:
        year = int(str(release_date)[:4])
        return year >= 2023
    except (ValueError, TypeError):
        return False


def is_remix(track_title: str) -> bool:
    return "remix" in track_title.lower()


def is_tier2_artist(artist: str) -> bool:
    return artist.lower() in TIER2_ARTISTS


def sniper_score(row: dict) -> float:
    """
    Returns a priority score 0-100.
    Higher = more likely to be unclaimed = probe first.
    """
    score = 0.0
    label = str(row.get("label", ""))
    track = str(row.get("track", ""))
    artist = str(row.get("artist", ""))
    release = str(row.get("release_date", ""))

    # Indie label: biggest signal — major labels have rights teams, Indies don't
    if is_indie(label):
        score += 35

    # Recent release: registration paperwork often lags 6-18 months
    if is_recent(release):
        score += 20

    # Remix: original may be claimed, remixer usually isn't
    if is_remix(track):
        score += 25

    # Known Tier 2 artist: high volume, low admin infrastructure
    if is_tier2_artist(artist):
        score += 15

    # Unknown/empty label: highest gap probability
    if not label or label.lower() in ("unknown", "none", ""):
        score += 10

    return round(min(score, 100), 1)


def apply_sniper_scores(tracks: list) -> list:
    """Add sniper_score to each track and sort highest first."""
    for t in tracks:
        t["sniper_score"] = sniper_score(t)

    return sorted(tracks, key=lambda x: x["sniper_score"], reverse=True)


def has_valid_isrc(track: dict) -> bool:
    """Return True only if track has a real ISRC string (not empty/NaN)."""
    isrc = track.get("isrc", "")
    if isrc is None:
        return False
    isrc_str = str(isrc).strip()
    return isrc_str not in ("", "nan", "NaN", "None")


def filter_top_targets(tracks: list, limit: int = 50) -> list:
    """Return only the top N highest-priority targets that have a valid ISRC."""
    with_isrc = [t for t in tracks if has_valid_isrc(t)]
    no_isrc = len(tracks) - len(with_isrc)
    if no_isrc:
        print(f"[SNIPER] Dropped {no_isrc} targets with missing ISRC")
    scored = apply_sniper_scores(with_isrc)
    top = scored[:limit]
    print(f"[SNIPER] Top {len(top)} targets selected (score >= {top[-1]['sniper_score'] if top else 0})")
    return top
