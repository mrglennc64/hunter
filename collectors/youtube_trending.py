"""
YouTube Music Trending Scraper (Free - No API key)
Scrapes the YouTube Music "Trending" charts daily.

Why: Songs hit YouTube trending BEFORE their paperwork is filed.
     By the time the ISRC lands in SoundExchange, the money is already
     stacking — but nobody has claimed it yet.

Targets:
  - US Hip-Hop/Rap trending (category 104 in YouTube Music)
  - Filters to hip-hop by title/artist keyword matching
  - Returns same {artist, track} format as billboard_collector
"""

import time
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

HIPHOP_KEYWORDS = [
    "rap", "drill", "trap", "hip", "hop", "bars", "freestyle",
    "lil", "young", "big", "dro", "dlow", "dugg", "gee",
]

# YouTube Music trending URLs (no login required)
YT_MUSIC_TRENDING_URLS = [
    # US Hip-Hop & Rap trending videos
    "https://charts.youtube.com/charts/TopSongs/us",
]

# Fallback: YouTube standard trending (Music category)
YT_TRENDING_RSS = "https://www.youtube.com/feeds/videos.xml?chart=0&category_id=10&gl=US&hl=en"


def scrape_youtube_charts(limit: int = 50) -> list:
    """
    Scrape YouTube Music Top Songs chart (US).
    Returns list of {artist, track, source} dicts.
    """
    print("[YT TRENDING] Scraping YouTube Music US chart...")
    tracks = []

    try:
        res = requests.get(
            "https://charts.youtube.com/charts/TopSongs/us",
            headers=HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(res.text, "lxml")

        # YouTube Charts uses ytmc-chart-row-item elements
        rows = soup.select("ytmc-chart-row-item")
        if not rows:
            # Try alternate selectors
            rows = soup.select("[class*='chart-row']")

        for row in rows[:limit]:
            title_el = row.select_one("[class*='title'], h3, .title")
            artist_el = row.select_one("[class*='artist'], [class*='subtitle'], span")

            title = title_el.get_text(strip=True) if title_el else ""
            artist = artist_el.get_text(strip=True) if artist_el else ""

            if title and artist:
                tracks.append({
                    "artist": artist,
                    "track": title,
                    "source": "youtube_trending",
                    "chart": "yt-us-top-songs",
                })

    except Exception as e:
        print(f"  [YT CHART ERROR] {e}")

    # Fallback to RSS feed if chart page fails
    if not tracks:
        tracks = scrape_youtube_rss_fallback(limit)

    print(f"[YT TRENDING] {len(tracks)} tracks scraped.")
    return tracks


def scrape_youtube_rss_fallback(limit: int = 50) -> list:
    """
    Fallback: YouTube trending RSS feed (Music category, US).
    Parses video titles to extract artist - track format.
    """
    print("[YT TRENDING] Using RSS fallback...")
    tracks = []

    try:
        res = requests.get(YT_TRENDING_RSS, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "xml")

        entries = soup.find_all("entry")
        for entry in entries[:limit]:
            title = entry.find("title")
            if not title:
                continue

            raw = title.get_text(strip=True)

            # Most music videos follow "Artist - Track (Official Video)" pattern
            if " - " in raw:
                parts = raw.split(" - ", 1)
                artist = parts[0].strip()
                track = re.sub(r'\s*\(.*?\)', '', parts[1]).strip()  # remove "(Official...)"
            else:
                continue  # skip non-music format titles

            # Hip-hop keyword filter on artist or track name
            combined = f"{artist} {track}".lower()
            if not any(kw in combined for kw in HIPHOP_KEYWORDS):
                continue

            tracks.append({
                "artist": artist,
                "track": track,
                "source": "youtube_rss",
                "chart": "yt-trending-music",
            })

    except Exception as e:
        print(f"  [YT RSS ERROR] {e}")

    print(f"[YT TRENDING] RSS fallback: {len(tracks)} hip-hop tracks.")
    return tracks


def pull_youtube_trending(limit: int = 50) -> list:
    """Main entry point. Returns up to `limit` trending hip-hop tracks."""
    tracks = scrape_youtube_charts(limit=limit)

    # Deduplicate
    seen = set()
    deduped = []
    for t in tracks:
        key = f"{t['artist'].lower()}|{t['track'].lower()}"
        if key not in seen:
            seen.add(key)
            deduped.append(t)

    return deduped[:limit]


if __name__ == "__main__":
    tracks = pull_youtube_trending(limit=25)
    print(f"\n{len(tracks)} tracks:")
    for t in tracks[:10]:
        print(f"  {t['artist']} — {t['track']}")
