"""
YouTube Remix Collector
Uses YouTube Data API v3 to find remixes of seed artists,
then extracts featured/guest artists from video titles.

Why YouTube is better than MusicBrainz for remixes:
  - More current (2023-2025 remixes appear immediately)
  - View counts tell you which remixes are high value
  - Title parsing catches "feat.", "x", "&" collabs
  - Catches unofficial remixes that never got ISRC registered

Output: leads with artist=GUEST, track=REMIX_TITLE, streams=VIEW_COUNT
"""

import re
import time
import os
import requests
from dotenv import load_dotenv

load_dotenv()

YT_KEY     = os.getenv("YOUTUBE_API_KEY", "")
YT_BASE    = "https://www.googleapis.com/youtube/v3"
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")

# Seed artists — search for their remixes on YouTube
SEED_ARTISTS = [
    # Tier 1 — high stream remixes
    "Doja Cat", "Nicki Minaj", "Drake", "Cardi B", "Megan Thee Stallion",
    "SZA", "Future", "Travis Scott", "Lil Baby", "21 Savage",
    "Post Malone", "Kendrick Lamar", "Gunna", "Lil Uzi Vert",
    "Jack Harlow", "Doechii", "GloRilla", "Ice Spice", "Sexyy Red",
    "Tyla", "Bad Bunny", "Morgan Wallen",
    # Tier 2 — prime black box targets
    "Latto", "Toosii", "Morray", "DDG", "Fivio Foreign",
    "Lil Tjay", "Central Cee", "Headie One", "Summer Walker",
    "Ari Lennox", "Brent Faiyaz", "JID", "Cordae", "EARTHGANG",
    "Masego", "Giveon", "Don Toliver", "Pooh Shiesty",
    "Babyface Ray", "Veeze", "Sleepy Hallow", "Sheff G",
]

FEAT_PATTERNS = [
    r'feat(?:uring)?\.?\s+([^(\[\]|]+)',
    r'ft\.?\s+([^(\[\]|]+)',
    r'\(with\s+([^)]+)\)',
    r'\bx\s+([A-Z][^(x\[|]+)',
    r'&\s+([A-Z][^(&\[|]+)',
]

MIN_VIEWS = 500_000  # Only keep remixes with 500K+ views


def extract_featured(title: str) -> list:
    """Extract featured artist names from a YouTube video title."""
    features = []
    NON_ARTIST = {"remix", "instrumental", "edit", "radio", "version", "mix", "extended", "acoustic"}

    for pattern in FEAT_PATTERNS:
        matches = re.findall(pattern, title, re.IGNORECASE)
        for m in matches:
            for part in re.split(r'[,&]', m):
                clean = part.strip().strip('"').strip("'")
                clean = re.sub(r'\s*[\(\[].*', '', clean).strip()
                clean = re.sub(r'\s*(official|video|remix|audio|lyrics).*', '', clean, flags=re.IGNORECASE).strip()
                clean = clean.strip(')')  # strip orphaned closing paren
                clean = clean.strip()
                if 3 < len(clean) < 40 and clean not in features:
                    if any(kw in clean.lower() for kw in NON_ARTIST):
                        continue
                    features.append(clean)
    return features


def search_youtube_remixes(artist: str, max_results: int = 25) -> list:
    """Search YouTube for remixes featuring this artist."""
    if not YT_KEY:
        print("[YT REMIX] No YOUTUBE_API_KEY set")
        return []

    leads = []
    queries = [
        f'"{artist}" remix feat official',
        f'"{artist}" remix ft official video',
    ]

    seen_video_ids = set()

    for query in queries:
        try:
            # Search
            search_res = requests.get(f"{YT_BASE}/search", params={
                "part":       "snippet",
                "q":          query,
                "type":       "video",
                "maxResults": max_results,
                "key":        YT_KEY,
            }, timeout=15)
            search_data = search_res.json()
            items = search_data.get("items", [])

            if not items:
                continue

            # Get video IDs
            video_ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
            new_ids = [v for v in video_ids if v not in seen_video_ids]
            seen_video_ids.update(new_ids)

            if not new_ids:
                continue

            # Get view counts in batch
            stats_res = requests.get(f"{YT_BASE}/videos", params={
                "part": "statistics,snippet",
                "id":   ",".join(new_ids),
                "key":  YT_KEY,
            }, timeout=15)
            videos = stats_res.json().get("items", [])

            for video in videos:
                title  = video["snippet"]["title"]
                views  = int(video["statistics"].get("viewCount", 0))
                ch     = video["snippet"].get("channelTitle", "")

                if views < MIN_VIEWS:
                    continue

                # Check it's actually a remix/collab
                title_lower = title.lower()
                if not any(kw in title_lower for kw in ["remix", "feat", "ft.", " x ", " & ", "with "]):
                    continue

                # Extract featured artists
                features = extract_featured(title)

                if features:
                    for feat in features:
                        # Skip if feat artist is same as seed
                        if artist.lower() in feat.lower() or feat.lower() in artist.lower():
                            continue
                        leads.append({
                            "artist":      feat,
                            "track":       title,
                            "isrc":        "",
                            "main_artist": artist,
                            "streams":     views,
                            "source":      "youtube_remix",
                            "chart":       "yt-remix",
                        })
                else:
                    # No feat pattern but still a collab/remix — use channel as artist hint
                    leads.append({
                        "artist":      ch,
                        "track":       title,
                        "isrc":        "",
                        "main_artist": artist,
                        "streams":     views,
                        "source":      "youtube_remix",
                        "chart":       "yt-remix",
                    })

            time.sleep(0.5)

        except Exception as e:
            print(f"  [YT ERROR] {artist}: {e}")

    return leads


def pull_youtube_remix_leads(limit_per_artist: int = 25) -> list:
    """Main entry — search YouTube remixes for all seed artists."""
    if not YT_KEY:
        print("[YT REMIX] Set YOUTUBE_API_KEY in .env")
        return []

    all_leads = []
    seen = set()

    for artist in SEED_ARTISTS:
        print(f"[YT REMIX] Searching: {artist}")
        leads = search_youtube_remixes(artist, max_results=limit_per_artist)
        added = 0
        for lead in leads:
            key = f"{lead['artist'].lower()}|{lead['track'].lower()[:40]}"
            if key not in seen:
                seen.add(key)
                all_leads.append(lead)
                added += 1
        print(f"  → {added} remix leads ({lead['streams']:,} views min)" if leads else "  → 0")
        time.sleep(1)

    # Sort by view count descending
    all_leads.sort(key=lambda x: x.get("streams", 0), reverse=True)
    print(f"\n[YT REMIX] Total: {len(all_leads)} remix leads")
    return all_leads


if __name__ == "__main__":
    leads = pull_youtube_remix_leads()
    print("\nTop 10 by views:")
    for l in leads[:10]:
        print(f"  {l['artist']} — {l['track'][:50]} [{l['streams']:,} views]")
