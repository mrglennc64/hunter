"""
YouTube Validator
- Confirms track has meaningful view count (high-traffic = more royalties)
- Adds youtube_views to each track record
- Tracks with high views but unclaimed on SX = highest priority targets
"""

import time
import os
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()


def get_youtube_client():
    return build("youtube", "v3", developerKey=os.getenv("YOUTUBE_API_KEY"))


def get_view_count(youtube, artist: str, track: str) -> int:
    try:
        query = f"{artist} {track} official"
        search_response = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=1,
            videoCategoryId="10",  # Music category
        ).execute()

        if not search_response["items"]:
            return 0

        video_id = search_response["items"][0]["id"]["videoId"]

        stats_response = youtube.videos().list(
            part="statistics",
            id=video_id,
        ).execute()

        if not stats_response["items"]:
            return 0

        return int(stats_response["items"][0]["statistics"].get("viewCount", 0))

    except Exception as e:
        print(f"  [YT ERROR] {artist} - {track}: {e}")
        return 0


def validate_with_youtube(tracks: list) -> list:
    """
    Adds youtube_views to each track.
    Filters out tracks with < 100k views (low value targets).
    """
    youtube = get_youtube_client()
    validated = []

    for i, t in enumerate(tracks):
        views = get_view_count(youtube, t["artist"], t["track"])
        t["youtube_views"] = views

        if views >= 100_000:
            validated.append(t)

        if i % 25 == 0:
            print(f"[YOUTUBE] Processed {i}/{len(tracks)} | Kept: {len(validated)}")

        time.sleep(0.5)

    print(f"[YOUTUBE] Done. {len(validated)} tracks with 100k+ views.")
    return validated


if __name__ == "__main__":
    sample = [
        {"artist": "Doechii", "track": "Anxiety"},
        {"artist": "42 Dugg", "track": "We Paid"},
    ]
    result = validate_with_youtube(sample)
    for r in result:
        print(r)
