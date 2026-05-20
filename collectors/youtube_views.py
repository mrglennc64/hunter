"""
YouTube View Count Fetcher
For each catalog lead with low/missing stream count, searches YouTube
for the official music video and pulls the view count.

No API key needed — scrapes YouTube search results.
"""

import re
import time
import json
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YT_API_URL = "https://www.googleapis.com/youtube/v3"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOG  = os.path.join(DATA_DIR, "unlock_catalog.json")


def parse_view_count(text: str) -> int:
    """Convert '1.2B views', '45M views', '3.4K views' to int."""
    text = text.lower().replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*([bmk]?)\s*view", text)
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2)
    if suffix == "b":
        return int(num * 1_000_000_000)
    if suffix == "m":
        return int(num * 1_000_000)
    if suffix == "k":
        return int(num * 1_000)
    return int(num)


def search_youtube_views_api(artist: str, track: str) -> int:
    """Use YouTube Data API v3 to search and get view count."""
    if not YT_API_KEY:
        return 0
    query = f"{artist} {track} official video"
    try:
        # Step 1: Search for video
        search_res = requests.get(f"{YT_API_URL}/search", params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 3,
            "key": YT_API_KEY,
        }, timeout=10)
        search_data = search_res.json()
        items = search_data.get("items", [])
        if not items:
            return 0

        video_id = items[0]["id"]["videoId"]
        title    = items[0]["snippet"]["title"]

        # Step 2: Get view count
        stats_res = requests.get(f"{YT_API_URL}/videos", params={
            "part": "statistics",
            "id": video_id,
            "key": YT_API_KEY,
        }, timeout=10)
        stats = stats_res.json().get("items", [{}])[0].get("statistics", {})
        views = int(stats.get("viewCount", 0))

        if views > 0:
            print(f"    [{views:,} views] {title[:60]}")
        return views

    except Exception as e:
        print(f"    [YT API ERROR] {e}")
        return 0


def search_youtube_views(artist: str, track: str) -> int:
    """Search YouTube for view count — API first, scrape fallback."""
    # Try official API first
    if YT_API_KEY:
        views = search_youtube_views_api(artist, track)
        if views > 0:
            return views

    # Fallback: scrape
    query = f"{artist} {track} official video"
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"

    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        match = re.search(r'var ytInitialData = ({.*?});</script>', res.text, re.DOTALL)
        if not match:
            return 0

        data = json.loads(match.group(1))
        contents = (
            data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
        )

        for section in contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                vr = item.get("videoRenderer", {})
                if not vr:
                    continue
                view_text = vr.get("viewCountText", {}).get("simpleText", "") or \
                            vr.get("viewCountText", {}).get("runs", [{}])[0].get("text", "")
                views = parse_view_count(view_text)
                title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
                if views > 0:
                    print(f"    [{views:,} views] {title[:60]}")
                    return views
        return 0

    except Exception as e:
        print(f"    [YT SCRAPE ERROR] {e}")
        return 0


def youtube_to_streams(views: int) -> int:
    """
    Rough conversion: YouTube views → Spotify-equivalent streams.
    YouTube pays ~$0.001/view, Spotify ~$0.004/stream.
    So 1 YT view ≈ 0.25 Spotify streams, but for royalty estimation
    we use views directly as a proxy for popularity.
    """
    return views  # Use view count directly as stream proxy


def update_catalog_streams(min_streams_threshold: int = 1000) -> int:
    """
    For all leads with streams below threshold, fetch YouTube view count
    and update the catalog. Also recalculates bounty.
    """
    with open(CATALOG) as f:
        catalog = json.load(f)

    updated = 0
    for aid, lead in catalog.items():
        streams = lead.get("streams", 0)
        try:
            streams = int(streams)
        except (ValueError, TypeError):
            streams = 0

        if streams >= min_streams_threshold:
            continue  # Already has good data

        artist = lead.get("artist", "")
        track  = lead.get("track", "")

        # Clean up garbled artist names
        artist_clean = re.sub(r'Featuring.*', '', artist).strip()
        artist_clean = re.sub(r'&.*', '', artist_clean).strip()

        print(f"[YT] {artist_clean} — {track}")
        views = search_youtube_views(artist_clean, track)

        if views > 0:
            lead["streams"] = views
            lead["streams_source"] = "youtube"

            # Recalculate bounty
            bounty_lo, bounty_hi = estimate_bounty(views)
            lead["bounty_low"]  = f"${bounty_lo:,.2f}"
            lead["bounty_high"] = f"${bounty_hi:,.2f}"

            print(f"  → {views:,} views | ${bounty_lo:,.0f} – ${bounty_hi:,.0f}")
            updated += 1
        else:
            # Fallback: Billboard charted = at least 5M streams floor
            lead["streams"] = 5_000_000
            lead["streams_source"] = "billboard_floor"
            bounty_lo, bounty_hi = estimate_bounty(5_000_000)
            lead["bounty_low"]  = f"${bounty_lo:,.2f}"
            lead["bounty_high"] = f"${bounty_hi:,.2f}"
            print(f"  → Billboard floor: 5M streams | ${bounty_lo:,.0f} – ${bounty_hi:,.0f}")
            updated += 1

        time.sleep(2)

    with open(CATALOG, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"\n[YT] Updated {updated} leads with YouTube view counts")
    return updated


def estimate_bounty(streams: int) -> tuple:
    """Estimate royalty range from stream count."""
    # SoundExchange pays ~$0.001–$0.0015 per stream for non-interactive
    lo = streams * 0.001
    hi = streams * 0.0015
    return lo, hi


if __name__ == "__main__":
    print("[YT] Fetching YouTube view counts for low-stream leads...")
    update_catalog_streams(min_streams_threshold=1000)
    print("[YT] Done. Run dashboard/generate.py to refresh dashboard.")
