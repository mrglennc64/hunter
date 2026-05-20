"""
Chartmetric Scorer (Free Tier)
- Authenticates with Chartmetric free API
- Looks up Spotify Popularity score per track
- Filters out anything below MIN_POPULARITY (default 60)
- Tracks below 60 are not generating enough royalty revenue to be worth pursuing

Free tier limits: ~100 requests/day — enough for daily batches of 50-100 tracks.

Sign up free at: https://chartmetric.com/
Get your API key from: https://api.chartmetric.com/apidoc/
"""

import time
import requests
import os
from dotenv import load_dotenv

load_dotenv()

CM_API_BASE = "https://api.chartmetric.com/api"
MIN_POPULARITY = 60  # Only pursue tracks generating real cash


def get_chartmetric_token() -> str | None:
    """Exchange refresh token for a short-lived access token."""
    refresh_token = os.getenv("CHARTMETRIC_REFRESH_TOKEN")
    if not refresh_token:
        print("[CM] No CHARTMETRIC_REFRESH_TOKEN in .env — skipping Chartmetric scoring.")
        return None
    try:
        res = requests.post(
            f"{CM_API_BASE}/token",
            json={"refreshtoken": refresh_token},
            timeout=10,
        )
        return res.json().get("token")
    except Exception as e:
        print(f"[CM] Auth error: {e}")
        return None


def search_track_cm(token: str, artist: str, track: str) -> dict | None:
    """Search Chartmetric for a track and return the top result."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(
            f"{CM_API_BASE}/search",
            params={"q": f"{artist} {track}", "type": "tracks", "limit": 1},
            headers=headers,
            timeout=10,
        )
        results = res.json().get("tracks", {}).get("data", [])
        return results[0] if results else None
    except Exception as e:
        print(f"  [CM ERROR] {artist} - {track}: {e}")
        return None


def get_spotify_popularity(token: str, cm_track_id: int) -> int:
    """Fetch Spotify popularity score (0–100) from Chartmetric track detail."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(
            f"{CM_API_BASE}/track/{cm_track_id}",
            headers=headers,
            timeout=10,
        )
        data = res.json().get("obj", {})
        return data.get("sp_popularity", 0) or 0
    except Exception as e:
        print(f"  [CM DETAIL ERROR] track_id={cm_track_id}: {e}")
        return 0


def score_with_chartmetric(tracks: list, min_popularity: int = MIN_POPULARITY) -> list:
    """
    Add spotify_popularity to each track via Chartmetric.
    Filter out tracks below min_popularity.
    Falls back gracefully if no API key configured.
    """
    token = get_chartmetric_token()

    if not token:
        # No Chartmetric key — pass all tracks through unfiltered
        print("[CM] Skipping popularity filter (no token). All tracks kept.")
        for t in tracks:
            t.setdefault("spotify_popularity", 0)
        return tracks

    scored = []
    dropped = 0

    for i, t in enumerate(tracks):
        artist = t.get("artist", "")
        track = t.get("track", "")

        result = search_track_cm(token, artist, track)

        if not result:
            # Can't score — keep it anyway (don't drop on uncertainty)
            t["spotify_popularity"] = 0
            scored.append(t)
            time.sleep(0.5)
            continue

        cm_id = result.get("id")
        popularity = get_spotify_popularity(token, cm_id) if cm_id else 0
        t["spotify_popularity"] = popularity

        if popularity >= min_popularity or popularity == 0:
            scored.append(t)
        else:
            dropped += 1
            print(f"  [DROP] {artist} - {track} (popularity {popularity} < {min_popularity})")

        if i % 20 == 0:
            print(f"[CM] {i}/{len(tracks)} scored | kept: {len(scored)} | dropped: {dropped}")

        time.sleep(0.4)  # respect free tier rate limit

    print(f"[CM] Done. {len(scored)} tracks kept (min popularity {min_popularity}) | {dropped} dropped.")
    return scored


if __name__ == "__main__":
    sample = [
        {"artist": "Doechii", "track": "Anxiety"},
        {"artist": "42 Dugg", "track": "We Paid"},
    ]
    results = score_with_chartmetric(sample)
    for r in results:
        print(r)
