"""
Atlanta Market Collector
Pulls artist/track targets from Atlanta-focused sources:
  1. Wikipedia: Category:Rappers_from_Atlanta  → artist names → MB tracks
  2. Spotify playlists (curated Atlanta/trap)  → artist + track + ISRC
  3. Complex: Best Rappers Right Now           → artist names → MB tracks
  4. YouTube playlist                          → artist + track

Usage:
    python collectors/atlanta_collector.py
    # Saves to data/atlanta_targets.csv — then feed into pipeline:
    cp data/atlanta_targets.csv data/master_targets.csv
    python run_pipeline.py --stage probe --batch 100
"""

import re
import time
import csv
import os
import json
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
MB_HEADERS = {
    "User-Agent": "TrapRoyaltiesAudit/1.0 (audit@traproyalties.com)",
    "Accept": "application/json",
}
MB_BASE = "https://musicbrainz.org/ws/2"
YT_KEY  = os.getenv("YOUTUBE_API_KEY", "")
YT_BASE = "https://www.googleapis.com/youtube/v3"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

SPOTIFY_PLAYLISTS = [
    ("0ETmHZfi4XOeqwjG8U5H4e", "atlanta-trap"),
    ("4WPn9lRyNgvOmhTrjEQljo", "atlanta-rap"),
]
YOUTUBE_PLAYLIST_ID = "PLAG4S36wGZnCZ6ZOBkP1eSuC9Wt_l61r4"


# ── Wikipedia: Rappers from Atlanta ──────────────────────────────────────────

def pull_wikipedia_atlanta() -> list:
    """Scrape all artist names from Wikipedia Category:Rappers_from_Atlanta."""
    print("[WIKI] Scraping Atlanta rappers...")
    artists = []
    url = "https://en.wikipedia.org/wiki/Category:Rappers_from_Atlanta"

    while url:
        try:
            res  = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "lxml")
            for a in soup.select("#mw-pages .mw-category-group li a"):
                name = a.get_text(strip=True)
                if name and not name.startswith("Category:"):
                    artists.append(name)
            # Next page
            next_a = soup.find("a", string=lambda t: t and "next page" in t.lower())
            url = ("https://en.wikipedia.org" + next_a["href"]) if next_a else None
            if url:
                time.sleep(1)
        except Exception as e:
            print(f"  [WIKI ERROR] {e}")
            break

    print(f"  → {len(artists)} Atlanta artists from Wikipedia")
    return artists


# ── Complex: Best Rappers Right Now ──────────────────────────────────────────

def pull_complex_rappers() -> list:
    """Scrape artist names from Complex best rappers article."""
    print("[COMPLEX] Scraping Complex best rappers...")
    artists = []
    url = "https://www.complex.com/music/a/dimassanfiorenzo/best-rappers-right-now"

    try:
        res  = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "lxml")

        # Complex ranked list articles use h2 for each entry
        for h in soup.select("h2, h3, .slide-title, [class*='RankTitle'], [class*='rank-title']"):
            text = h.get_text(strip=True)
            # Strip leading rank numbers: "1." / "No. 1" / "1 "
            text = re.sub(r'^\d+[\.\)]\s*', '', text).strip()
            text = re.sub(r'^No\.\s*\d+[:\s]*', '', text, flags=re.IGNORECASE).strip()
            skip = {"best", "rapper", "right now", "complex", "music", "read", "watch", ""}
            if text and 2 < len(text) < 50 and text.lower() not in skip:
                artists.append(text)

    except Exception as e:
        print(f"  [COMPLEX ERROR] {e}")

    # Deduplicate
    seen, unique = set(), []
    for a in artists:
        if a.lower() not in seen:
            seen.add(a.lower())
            unique.append(a)

    print(f"  → {len(unique)} artists from Complex")
    return unique


# ── MusicBrainz: artist name → recent recordings ─────────────────────────────

def artist_to_tracks(artist_name: str, limit: int = 4, chart: str = "atlanta") -> list:
    """Search MusicBrainz for recent recordings by an artist."""
    tracks = []
    try:
        res = requests.get(
            f"{MB_BASE}/recording",
            params={"query": f'artistname:"{artist_name}"', "limit": limit, "fmt": "json"},
            headers=MB_HEADERS,
            timeout=15,
        )
        for rec in res.json().get("recordings", []):
            title = rec.get("title", "")
            isrc  = rec["isrcs"][0] if rec.get("isrcs") else ""
            if title:
                tracks.append({
                    "artist": artist_name,
                    "track":  title,
                    "isrc":   isrc,
                    "source": "musicbrainz",
                    "chart":  chart,
                })
    except Exception:
        pass
    return tracks


def artists_to_tracks(artists: list, tracks_per: int = 4, chart: str = "atlanta") -> list:
    """Batch convert artist names → track list via MusicBrainz (1 req/sec)."""
    all_tracks = []
    for i, artist in enumerate(artists):
        all_tracks.extend(artist_to_tracks(artist, limit=tracks_per, chart=chart))
        if (i + 1) % 20 == 0:
            print(f"  [MB] {i+1}/{len(artists)} done...")
        time.sleep(1.1)
    return all_tracks


# ── Spotify Playlists ─────────────────────────────────────────────────────────

def pull_spotify_playlist(playlist_id: str, label: str) -> list:
    """Pull tracks from a Spotify playlist — spotipy first, embed fallback."""
    print(f"[SPOTIFY] Playlist: {label} ({playlist_id})...")
    sp_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
    sp_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")

    if sp_id and sp_secret:
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=sp_id, client_secret=sp_secret
            ))
            results = sp.playlist_tracks(playlist_id, limit=100)
            items   = results.get("items", [])
            while results.get("next"):
                results = sp.next(results)
                items.extend(results.get("items", []))

            tracks = []
            for item in items:
                t = item.get("track")
                if not t:
                    continue
                name   = t.get("name", "")
                artist = ", ".join(a["name"] for a in t.get("artists", []))
                isrc   = t.get("external_ids", {}).get("isrc", "")
                streams = t.get("popularity", 0) * 100_000  # rough proxy
                if name and artist:
                    tracks.append({
                        "artist":  artist,
                        "track":   name,
                        "isrc":    isrc,
                        "streams": streams,
                        "source":  "spotify_playlist",
                        "chart":   f"spotify-{label}",
                    })
            print(f"  → {len(tracks)} tracks")
            return tracks
        except Exception as e:
            print(f"  [SPOTIPY ERROR] {e} — trying embed fallback")

    # Embed fallback (no credentials needed)
    tracks = []
    try:
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        res   = requests.get(embed_url, headers={**HEADERS, "Accept": "text/html"}, timeout=15)
        match = re.search(r'"tracks":\{"items":\[(.*?)\]', res.text, re.DOTALL)
        if match:
            items = json.loads("[" + match.group(1) + "]")
            for item in items:
                t      = item.get("track", item)
                name   = t.get("name", "")
                artist = ", ".join(a.get("name", "") for a in t.get("artists", []))
                isrc   = t.get("external_ids", {}).get("isrc", "")
                if name and artist:
                    tracks.append({
                        "artist": artist,
                        "track":  name,
                        "isrc":   isrc,
                        "source": "spotify_embed",
                        "chart":  f"spotify-{label}",
                    })
    except Exception as e:
        print(f"  [EMBED ERROR] {e}")

    print(f"  → {len(tracks)} tracks (embed)")
    return tracks


# ── YouTube Playlist ──────────────────────────────────────────────────────────

def pull_youtube_playlist(playlist_id: str) -> list:
    """Pull tracks from YouTube playlist via Data API v3."""
    print(f"[YOUTUBE] Playlist: {playlist_id}...")
    tracks = []

    if not YT_KEY:
        print("  [YOUTUBE] No YOUTUBE_API_KEY — skipping")
        return []

    page_token = None
    while True:
        try:
            params = {
                "part":       "snippet",
                "playlistId": playlist_id,
                "maxResults": 50,
                "key":        YT_KEY,
            }
            if page_token:
                params["pageToken"] = page_token

            res  = requests.get(f"{YT_BASE}/playlistItems", params=params, timeout=15)
            data = res.json()

            for item in data.get("items", []):
                title   = item["snippet"]["title"]
                channel = item["snippet"].get("videoOwnerChannelTitle", "").replace(" - Topic", "").strip()

                if title in ("Private video", "Deleted video"):
                    continue

                if " - " in title:
                    parts  = title.split(" - ", 1)
                    artist = parts[0].strip()
                    track  = re.sub(r'\s*[\(\[].*?(official|video|audio|lyrics|visualizer).*', '', parts[1], flags=re.IGNORECASE).strip()
                    track  = re.sub(r'\s*[\(\[].*[\)\]]$', '', track).strip() or parts[1].strip()
                else:
                    artist = channel
                    track  = title

                if artist and track:
                    tracks.append({
                        "artist": artist,
                        "track":  track,
                        "isrc":   "",
                        "source": "youtube_playlist",
                        "chart":  "yt-atlanta-playlist",
                    })

            page_token = data.get("nextPageToken")
            if not page_token:
                break
            time.sleep(0.5)

        except Exception as e:
            print(f"  [YOUTUBE ERROR] {e}")
            break

    print(f"  → {len(tracks)} tracks")
    return tracks


# ── Main ─────────────────────────────────────────────────────────────────────

def pull_atlanta_leads() -> list:
    """Pull from all Atlanta-focused sources. Returns deduplicated track list."""
    all_tracks = []
    seen = set()

    def add(tracks: list):
        for t in tracks:
            if not t.get("artist") or not t.get("track"):
                continue
            key = f"{t['artist'].lower()}|{t['track'].lower()[:40]}"
            if key not in seen:
                seen.add(key)
                all_tracks.append(t)

    # 1. Spotify playlists — best quality (has ISRC + popularity)
    for pid, label in SPOTIFY_PLAYLISTS:
        add(pull_spotify_playlist(pid, label))
        time.sleep(1)

    # 2. YouTube playlist
    add(pull_youtube_playlist(YOUTUBE_PLAYLIST_ID))

    # 3. Wikipedia Atlanta rappers → MusicBrainz
    wiki_artists = pull_wikipedia_atlanta()
    if wiki_artists:
        print(f"[WIKI→MB] Fetching tracks for {len(wiki_artists)} Atlanta artists...")
        add(artists_to_tracks(wiki_artists, tracks_per=4, chart="atlanta-wiki"))

    # 4. Complex best rappers → MusicBrainz
    complex_artists = pull_complex_rappers()
    if complex_artists:
        print(f"[COMPLEX→MB] Fetching tracks for {len(complex_artists)} Complex artists...")
        add(artists_to_tracks(complex_artists, tracks_per=4, chart="complex-best"))

    print(f"\n[ATLANTA] {len(all_tracks)} unique leads total")
    return all_tracks


if __name__ == "__main__":
    leads = pull_atlanta_leads()

    out = os.path.join(DATA_DIR, "atlanta_targets.csv")
    if leads:
        fieldnames = ["artist", "track", "isrc", "streams", "source", "chart"]
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(leads)
        print(f"[ATLANTA] Saved → {out}")

    print("\nTop 30 leads:")
    for l in leads[:30]:
        print(f"  {l['artist']:<30} {l['track'][:45]:<45} [{l['source']}]")
