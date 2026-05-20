"""
Billboard Hip-Hop Chart Scraper (Free - No API key)
Two modes:
  1. Weekly charts  — hot-rap-songs, hot-r-and-b-hip-hop-songs, etc.
  2. Year-End charts — Billboard Year-End Hot 100 (2024 + 2025 = ~200 songs)

2024/2025 is the gold mine:
  - Early 2024  → "Holding Account" at max value, artist frustrated
  - Late 2024   → Peak viral / DIY-to-signed transition, old ISRCs unclaimed
  - Mid 2025    → "New Money," artist is currently hot, wants every dime
  - 2021/2022   → Avoid, money already flushed by collection societies
"""

import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "BountyHunterAudit/1.0 (contact@your-domain.com)"
}

WEEKLY_CHARTS = [
    # Hip-Hop / R&B — core
    "hot-rap-songs",
    "hot-r-and-b-hip-hop-songs",
    "rhythmic-airplay-songs",
    "rap-song-sales",
    "r-b-hip-hop-airplay",
    "adult-r-and-b-airplay",
    "mainstream-r-and-b-hip-hop-airplay",
    "streaming-songs",
    # Tier 2 / emerging urban
    "rap-caviar",              # Spotify editorial — heavy indie/unsigned
    "independent-albums",     # indie label acts
    "heatseekers-songs",      # breaking artists before top 100
    "bubbling-under-hot-100", # just below Hot 100 — prime tier 2
    "emerging-artists",       # Billboard emerging
    "r-b-hip-hop-best-sellers",
]

YEAR_END_CHARTS = [
    ("hot-100-songs",             [2022, 2023, 2024, 2025]),
    ("hot-rap-songs",             [2022, 2023, 2024, 2025]),
    ("hot-r-and-b-hip-hop-songs", [2022, 2023, 2024, 2025]),
    ("heatseekers-songs",         [2023, 2024, 2025]),
    ("emerging-artists",          [2023, 2024, 2025]),
    ("bubbling-under-hot-100",    [2023, 2024, 2025]),
]

# Keep backward-compat alias
HIPHOP_WEEKLY_CHARTS = WEEKLY_CHARTS


# ── Year-End scraper ──────────────────────────────────────────────────────────

def get_year_end_targets(year: int | str, chart_slug: str = "hot-100-songs") -> list:
    """
    Scrape Billboard Year-End chart for a specific year and genre.
    """
    print(f"[BILLBOARD] Scraping Year-End {year}/{chart_slug}...")
    url = f"https://www.billboard.com/charts/year-end/{year}/{chart_slug}/"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"  [SKIP] Year-End {year}: {e}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    targets = []

    songs = soup.select("li ul li h3")
    artists = soup.select("li ul li h3 + span")

    for i in range(min(len(songs), len(artists))):
        title = songs[i].get_text(strip=True)
        artist = artists[i].get_text(strip=True)
        if title and artist:
            targets.append({
                "artist": artist,
                "track": title,
                "chart": f"year-end-{year}",
                "year": str(year),
                "source": "billboard_yearend",
            })

    print(f"  → {len(targets)} tracks from Year-End {year}")
    return targets


def get_gold_mine_targets() -> list:
    """
    Pull all year-end chart lists across multiple genres and years (2022-2025).
    Targets ~800-1000 unique tracks.
    """
    seen = set()
    deduped = []

    for chart_slug, years in YEAR_END_CHARTS:
        for year in years:
            tracks = get_year_end_targets(year, chart_slug=chart_slug)
            for t in tracks:
                key = f"{t['artist'].lower()}|{t['track'].lower()}"
                if key not in seen:
                    seen.add(key)
                    deduped.append(t)
            time.sleep(2)

    print(f"[BILLBOARD] Year-End gold mine: {len(deduped)} unique tracks")
    return deduped


# ── Weekly chart scraper ──────────────────────────────────────────────────────

def scrape_weekly_chart(chart_name: str, limit: int = 50) -> list:
    url = f"https://www.billboard.com/charts/{chart_name}/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"  [SKIP] {chart_name}: {e}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    tracks = []

    titles = soup.select("li ul li h3")
    artists = soup.select("li ul li h3 + span")

    for i in range(min(len(titles), len(artists), limit)):
        title = titles[i].get_text(strip=True)
        artist = artists[i].get_text(strip=True)
        if title and artist:
            tracks.append({
                "artist": artist,
                "track": title,
                "chart": chart_name,
                "source": "billboard_weekly",
            })

    return tracks


def pull_billboard_weekly(limit: int = 50) -> list:
    """
    Pull current weekly charts across all genres.
    limit=50  → per-chart cap in start mode
    limit=100 → per-chart cap in full mode
    """
    all_tracks = []
    seen = set()

    for chart_name in WEEKLY_CHARTS:
        print(f"[BILLBOARD] Weekly: {chart_name} (top {limit})")
        tracks = scrape_weekly_chart(chart_name, limit=limit)

        for t in tracks:
            key = f"{t['artist'].lower()}|{t['track'].lower()}"
            if key not in seen:
                seen.add(key)
                all_tracks.append(t)

        time.sleep(2)

    print(f"[BILLBOARD] Weekly done. {len(all_tracks)} unique tracks.")
    return all_tracks


# ── Combined pull ─────────────────────────────────────────────────────────────

def pull_all(weekly_limit: int = 50) -> list:
    """
    Pull year-end gold mine (2024+2025) + current weekly charts.
    Default starting batch = 50 weekly + ~200 year-end = ~250 total.
    """
    year_end = get_gold_mine_targets()
    time.sleep(2)
    weekly = pull_billboard_weekly(limit=weekly_limit)

    combined = year_end + weekly

    # Final dedup
    seen = set()
    deduped = []
    for t in combined:
        key = f"{t['artist'].lower()}|{t['track'].lower()}"
        if key not in seen:
            seen.add(key)
            deduped.append(t)

    print(f"[BILLBOARD] Total unique tracks: {len(deduped)}")
    return deduped


if __name__ == "__main__":
    tracks = pull_all(weekly_limit=50)
    print(f"\nSample:")
    for t in tracks[:5]:
        print(t)
