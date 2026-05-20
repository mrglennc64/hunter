"""
Spotify Enricher
- Matches artist/track to Spotify
- Pulls ISRC (the key identifier for SoundExchange)
- Filters to hip-hop only by genre
- Adds popularity score and label info
"""

import time
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

HIPHOP_GENRES = [
    "hip hop", "rap", "trap", "drill", "crunk", "bounce",
    "gangster rap", "southern hip hop", "east coast hip hop",
    "west coast rap", "chicago drill", "brooklyn drill",
    "memphis rap", "detroit trap", "atlanta rap", "new york rap",
    "conscious hip hop", "underground hip hop", "mumble rap",
]

HIPHOP_SUBGENRES_DIRECT = [
    "trap", "drill", "atlanta rap", "chicago drill",
    "memphis rap", "detroit trap", "brooklyn drill",
    "west coast rap", "gangster rap", "conscious hip hop",
    "southern hip hop", "crunk", "new york rap",
    "underground hip hop", "miami bass", "hyphy",
]


def get_spotify_client():
    return spotipy.Spotify(auth_manager=SpotifyClientCredentials(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    ))


def is_hiphop(genres: list) -> bool:
    genre_str = " ".join(genres).lower()
    return any(g in genre_str for g in HIPHOP_GENRES)


def enrich_with_isrc(tracks: list) -> list:
    """
    Takes raw track list (artist, track) and enriches with:
    - ISRC (for SoundExchange probe)
    - Spotify popularity
    - Label
    - Genre confirmation (hip-hop filter)
    """
    sp = get_spotify_client()
    enriched = []
    skipped = 0

    for i, t in enumerate(tracks):
        try:
            query = f"artist:{t['artist']} track:{t['track']}"
            results = sp.search(q=query, type="track", limit=1)
            items = results["tracks"]["items"]

            if not items:
                skipped += 1
                continue

            track_data = items[0]
            artist_id = track_data["artists"][0]["id"]
            artist_data = sp.artist(artist_id)
            genres = artist_data.get("genres", [])

            if not is_hiphop(genres):
                skipped += 1
                continue

            isrc = track_data["external_ids"].get("isrc")
            if not isrc:
                skipped += 1
                continue

            enriched.append({
                **t,
                "isrc": isrc,
                "spotify_id": track_data["id"],
                "popularity": track_data["popularity"],
                "release_date": track_data["album"]["release_date"],
                "label": track_data["album"].get("label", "Unknown"),
                "genres": ", ".join(genres),
                "source": t.get("source", "billboard"),
            })

            if i % 50 == 0:
                print(f"[SPOTIFY] Processed {i}/{len(tracks)} | Enriched: {len(enriched)} | Skipped: {skipped}")

            time.sleep(0.2)

        except Exception as e:
            print(f"  [ERROR] {t.get('artist')} - {t.get('track')}: {e}")
            time.sleep(1)

    print(f"[SPOTIFY] Done. {len(enriched)} hip-hop tracks with ISRCs.")
    return enriched


def pull_spotify_hiphop_direct(total=500) -> list:
    """
    Pull hip-hop tracks directly from Spotify genre search.
    Catches artists Billboard might miss (underground/regional).
    """
    sp = get_spotify_client()
    tracks = []
    seen_isrc = set()

    for genre in HIPHOP_SUBGENRES_DIRECT:
        offset = 0
        print(f"[SPOTIFY DIRECT] Pulling genre: {genre}")

        while len(tracks) < total:
            try:
                results = sp.search(
                    q=f"genre:{genre}",
                    type="track",
                    limit=50,
                    offset=offset
                )
                items = results["tracks"]["items"]
                if not items:
                    break

                for item in items:
                    isrc = item["external_ids"].get("isrc")
                    if not isrc or isrc in seen_isrc:
                        continue
                    seen_isrc.add(isrc)
                    tracks.append({
                        "artist": item["artists"][0]["name"],
                        "track": item["name"],
                        "isrc": isrc,
                        "spotify_id": item["id"],
                        "popularity": item["popularity"],
                        "release_date": item["album"]["release_date"],
                        "label": item["album"].get("label", "Unknown"),
                        "genres": genre,
                        "source": "spotify_direct",
                    })

                offset += 50
                time.sleep(0.3)

            except Exception as e:
                print(f"  [ERROR] {genre} offset {offset}: {e}")
                break

    print(f"[SPOTIFY DIRECT] Done. {len(tracks)} tracks.")
    return tracks


if __name__ == "__main__":
    tracks = pull_spotify_hiphop_direct(total=200)
    for t in tracks[:3]:
        print(t)
