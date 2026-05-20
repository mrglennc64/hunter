"""
Free ISRC Resolver — No Spotify, No API keys required.
Primary:  MusicBrainz API (free, 1 req/sec rate limit)
Fallback: Deezer API     (free, no auth needed)
"""

import time
import requests

MB_HEADERS = {
    "User-Agent": "MusicRightsAuditor/1.0 (contact@your-domain.com)"
}


def get_isrc_musicbrainz(artist: str, track: str) -> str | None:
    """Query MusicBrainz for ISRC. Rate limit: 1 req/sec — we sleep 2s to be safe."""
    try:
        url = (
            f"https://musicbrainz.org/ws/2/recording"
            f"?query=artist:\"{artist}\" AND recording:\"{track}\"&fmt=json"
        )
        response = requests.get(url, headers=MB_HEADERS, timeout=10)
        data = response.json()

        recordings = data.get("recordings", [])
        if recordings:
            isrcs = recordings[0].get("isrcs", [])
            return isrcs[0] if isrcs else None
    except Exception as e:
        print(f"  [MB ERROR] {artist} - {track}: {e}")
    return None


def get_isrc_deezer(artist: str, track: str) -> str | None:
    """Query Deezer as fallback. No auth needed."""
    try:
        search_url = f"https://api.deezer.com/search?q=track:\"{track}\" artist:\"{artist}\""
        res = requests.get(search_url, timeout=10).json()

        if res.get("data"):
            track_id = res["data"][0]["id"]
            detail = requests.get(
                f"https://api.deezer.com/track/{track_id}", timeout=10
            ).json()
            return detail.get("isrc")
    except Exception as e:
        print(f"  [DEEZER ERROR] {artist} - {track}: {e}")
    return None


def resolve_isrc(artist: str, track: str) -> tuple[str | None, str]:
    """
    Try MusicBrainz first, then Deezer.
    Returns (isrc, source) or (None, "miss").
    """
    isrc = get_isrc_musicbrainz(artist, track)
    if isrc:
        return isrc, "musicbrainz"

    # MusicBrainz rate limit — always sleep 2s after MB call
    time.sleep(2)

    isrc = get_isrc_deezer(artist, track)
    if isrc:
        return isrc, "deezer"

    return None, "miss"


def resolve_batch(tracks: list) -> list:
    """
    Resolve ISRCs for a list of {artist, track} dicts.
    Adds isrc and isrc_source fields. Skips tracks already having an ISRC.
    """
    resolved = []
    misses = 0

    for i, t in enumerate(tracks):
        # Skip if ISRC already populated (e.g. from a previous run)
        if t.get("isrc"):
            resolved.append(t)
            continue

        artist = t.get("artist", "")
        track = t.get("track", "")

        print(f"[ISRC] [{i+1}/{len(tracks)}] {artist} - {track}")

        isrc, source = resolve_isrc(artist, track)

        if isrc:
            print(f"  [FOUND] {isrc} via {source}")
            resolved.append({**t, "isrc": isrc, "isrc_source": source})
        else:
            print(f"  [MISS]")
            misses += 1
            # Keep the track in list even without ISRC — useful for manual follow-up
            resolved.append({**t, "isrc": None, "isrc_source": "miss"})

        # Respect MusicBrainz 1 req/sec — 2s covers both MB + Deezer calls
        time.sleep(2)

    hits = len([r for r in resolved if r.get("isrc")])
    print(f"[ISRC] Done. {hits} resolved / {misses} misses out of {len(tracks)}")
    return resolved


if __name__ == "__main__":
    sample = [
        {"artist": "BossMan Dlow", "track": "Mr Pot Scraper"},
        {"artist": "Doechii", "track": "Anxiety"},
        {"artist": "42 Dugg", "track": "We Paid"},
    ]
    results = resolve_batch(sample)
    for r in results:
        print(r)
