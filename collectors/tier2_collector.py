"""
Tier 2 Urban Chart Collector
Pulls from Shazam, Spotify RapCaviar, and Apple Music Hip-Hop
These charts catch artists BEFORE they hit Billboard — prime black box targets.

No API keys needed.
"""

import re
import time
import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Shazam Chart ──────────────────────────────────────────────────────────────

def pull_shazam_hiphop(limit: int = 100) -> list:
    """Scrape Shazam Hip-Hop/Rap chart."""
    print("[SHAZAM] Fetching Hip-Hop/Rap chart...")
    url = "https://www.shazam.com/charts/genre/united-states/hip-hop-rap"
    tracks = []

    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "lxml")

        # Shazam embeds chart data in JSON script tag
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                # Navigate Shazam's data structure
                chart_data = (
                    data.get("props", {})
                        .get("pageProps", {})
                        .get("chartData", {})
                        .get("tracks", [])
                )
                for item in chart_data[:limit]:
                    title  = item.get("title", "")
                    artist = item.get("subtitle", "")
                    if title and artist:
                        tracks.append({
                            "artist": artist,
                            "track":  title,
                            "chart":  "shazam-hiphop-us",
                            "source": "shazam",
                        })
                if tracks:
                    break
            except Exception:
                continue

        # Fallback: try meta tags / visible text
        if not tracks:
            for row in soup.select("[class*='chart'] [class*='title'], [class*='track']"):
                text = row.get_text(strip=True)
                if text and len(text) > 3:
                    tracks.append({
                        "artist": "",
                        "track":  text,
                        "chart":  "shazam-hiphop-us",
                        "source": "shazam",
                    })
                if len(tracks) >= limit:
                    break

    except Exception as e:
        print(f"  [SHAZAM ERROR] {e}")

    print(f"  → {len(tracks)} tracks from Shazam")
    return tracks


# ── Spotify RapCaviar (via Spotify embed) ─────────────────────────────────────

def pull_spotify_rapcaviar(limit: int = 50) -> list:
    """Pull tracks from Spotify RapCaviar via embed endpoint."""
    print("[SPOTIFY] Fetching RapCaviar playlist...")
    playlist_id = "7vd4Jp0C1gNmtdGuZP2UtR"
    tracks = []

    # Use Spotify's embed API which returns JSON
    url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/playlist/{playlist_id}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        # Try embed page for track listing
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        res2 = requests.get(embed_url, headers={**HEADERS, "Accept": "text/html"}, timeout=15)

        # Extract from JSON in page
        match = re.search(r'"tracks":\{"items":\[(.*?)\]', res2.text, re.DOTALL)
        if match:
            items_raw = "[" + match.group(1) + "]"
            try:
                items = json.loads(items_raw)
                for item in items[:limit]:
                    t = item.get("track", item)
                    name = t.get("name", "")
                    artists = t.get("artists", [])
                    artist = ", ".join(a.get("name", "") for a in artists)
                    if name and artist:
                        tracks.append({
                            "artist": artist,
                            "track":  name,
                            "chart":  "spotify-rapcaviar",
                            "source": "spotify",
                        })
            except Exception:
                pass

        # Fallback: scrape Spotify Charts page
        if not tracks:
            charts_url = "https://charts.spotify.com/charts/view/regional-us-weekly/latest"
            res3 = requests.get(charts_url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res3.text, "lxml")
            for row in soup.select("[data-testid='charts-table'] tr, .chart-table-row"):
                artist_el = row.select_one(".artist-name, [data-testid='artist-name']")
                track_el  = row.select_one(".track-name, [data-testid='track-name']")
                if artist_el and track_el:
                    tracks.append({
                        "artist": artist_el.get_text(strip=True),
                        "track":  track_el.get_text(strip=True),
                        "chart":  "spotify-charts-us",
                        "source": "spotify",
                    })
                if len(tracks) >= limit:
                    break

    except Exception as e:
        print(f"  [SPOTIFY ERROR] {e}")

    print(f"  → {len(tracks)} tracks from RapCaviar")
    return tracks


# ── Apple Music Hip-Hop (via RSS feed) ────────────────────────────────────────

def pull_apple_music_hiphop(limit: int = 100) -> list:
    """Pull Apple Music Hip-Hop/R&B charts via RSS feed — multiple genre feeds."""
    print("[APPLE] Fetching Apple Music Hip-Hop/R&B charts...")
    tracks = []
    seen = set()

    # Genre IDs: 18=Hip-Hop/Rap, 15=R&B/Soul, 53=Urban Contemporary
    genre_feeds = [
        ("https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/songs.json", "hip-hop"),
        ("https://rss.applemarketingtools.com/api/v2/us/music/coming-soon/100/songs.json", "coming-soon"),
        ("https://rss.applemarketingtools.com/api/v2/us/music/top-songs/100/songs.json", "top-songs"),
    ]

    for url, chart_name in genre_feeds:
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            data = res.json()
            results = data.get("feed", {}).get("results", [])

            for item in results:
                name   = item.get("name", "")
                artist = item.get("artistName", "")
                genre  = item.get("genres", [{}])[0].get("name", "") if item.get("genres") else ""

                if not name or not artist:
                    continue

                # For most-played: filter hip-hop/r&b only
                if chart_name == "hip-hop":
                    if not any(g in genre.lower() for g in ["hip-hop", "r&b", "rap", "urban"]):
                        continue

                key = f"{artist.lower()}|{name.lower()}"
                if key not in seen:
                    seen.add(key)
                    tracks.append({
                        "artist": artist,
                        "track":  name,
                        "chart":  f"apple-{chart_name}-us",
                        "source": "apple_music",
                    })

            time.sleep(1)
        except Exception as e:
            print(f"  [APPLE ERROR] {chart_name}: {e}")

    print(f"  → {len(tracks)} tracks from Apple Music")
    return tracks


# ── Audiomack Trending (free, no key) ─────────────────────────────────────────

def pull_audiomack_trending(limit: int = 50) -> list:
    """Pull trending hip-hop from Audiomack web page."""
    print("[AUDIOMACK] Fetching trending Hip-Hop...")
    tracks = []
    url = "https://audiomack.com/trending-now/song/rap"

    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "lxml")

        # Try JSON embedded in page
        match = re.search(r'"music":\[(.*?)\]', res.text, re.DOTALL)
        if match:
            try:
                items = json.loads("[" + match.group(1) + "]")
                for item in items[:limit]:
                    artist = item.get("artist", "")
                    title  = item.get("title", "")
                    if artist and title:
                        tracks.append({
                            "artist": artist,
                            "track":  title,
                            "chart":  "audiomack-trending-rap",
                            "source": "audiomack",
                        })
            except Exception:
                pass

        # Fallback: scrape visible song cards
        if not tracks:
            for card in soup.select(".song-card, .music-card, article, [class*='track']"):
                artist_el = card.select_one("[class*='artist'], .artist")
                title_el  = card.select_one("[class*='title'], .title, h3, h4")
                if artist_el and title_el:
                    tracks.append({
                        "artist": artist_el.get_text(strip=True),
                        "track":  title_el.get_text(strip=True),
                        "chart":  "audiomack-trending-rap",
                        "source": "audiomack",
                    })
                if len(tracks) >= limit:
                    break

    except Exception as e:
        print(f"  [AUDIOMACK ERROR] {e}")

    print(f"  → {len(tracks)} tracks from Audiomack")
    return tracks


# ── The Source HH-101 ─────────────────────────────────────────────────────────

def pull_the_source(limit: int = 60) -> list:
    """
    Scrape The Source HH-101 section — covers emerging/tier 2 hip-hop artists
    before they hit Billboard. Extracts artist names from article headlines.
    """
    print("[SOURCE] Fetching The Source HH-101...")
    tracks = []
    seen_artists = set()

    # Scrape multiple pages
    for page in range(1, 4):
        url = f"https://thesource.com/category/hh-101/page/{page}/" if page > 1 else "https://thesource.com/category/hh-101/"
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, "lxml")

            for article in soup.select("article, .post, .entry"):
                title_el = article.select_one("h2, h3, .entry-title, .post-title")
                if not title_el:
                    continue
                headline = title_el.get_text(strip=True)

                # Extract artist + track from headlines like:
                # "Latto Drops New Single 'Big Energy'"
                # "Toosii Releases 'Thank You For Believing'"
                # "Morray - 'Quicksand' Official Video"
                artist, track = parse_source_headline(headline)
                if artist and artist.lower() not in seen_artists:
                    seen_artists.add(artist.lower())
                    tracks.append({
                        "artist": artist,
                        "track":  track or headline[:50],
                        "chart":  "the-source-hh101",
                        "source": "the_source",
                    })

            time.sleep(1.5)
        except Exception as e:
            print(f"  [SOURCE ERROR] page {page}: {e}")
            break

        if len(tracks) >= limit:
            break

    print(f"  → {len(tracks)} artists from The Source")
    return tracks


# ── Warm Music Urban Chart ────────────────────────────────────────────────────

def pull_warmmusic_urban(limit: int = 100) -> list:
    """
    Scrape Warm Music urban chart — indie/tier 2 urban artists.
    """
    print("[WARM] Fetching Warm Music Urban chart...")
    tracks = []
    url = "https://www.warmmusic.net/charts/urban"

    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, "lxml")

        # Try common chart row selectors
        for row in soup.select("tr, .chart-row, .track-row, .song-row, li"):
            cells = row.select("td, .artist, .title, .song, .track")
            if len(cells) >= 2:
                artist = cells[0].get_text(strip=True)
                track  = cells[1].get_text(strip=True)
                if artist and track and len(artist) > 1 and len(track) > 1:
                    tracks.append({
                        "artist": artist,
                        "track":  track,
                        "chart":  "warmmusic-urban",
                        "source": "warmmusic",
                    })
            if len(tracks) >= limit:
                break

        # Fallback: grab all text that looks like artist - track
        if not tracks:
            for el in soup.select("h2, h3, h4, .title, .name, p"):
                text = el.get_text(strip=True)
                if " - " in text and len(text) < 100:
                    parts = text.split(" - ", 1)
                    tracks.append({
                        "artist": parts[0].strip(),
                        "track":  parts[1].strip(),
                        "chart":  "warmmusic-urban",
                        "source": "warmmusic",
                    })
                if len(tracks) >= limit:
                    break

    except Exception as e:
        print(f"  [WARM ERROR] {e}")

    print(f"  → {len(tracks)} tracks from Warm Music")
    return tracks


def parse_source_headline(headline: str) -> tuple:
    """
    Extract (artist, track) from The Source article headline.
    Returns ("", "") if can't parse.
    """
    # Pattern: "Artist Name - 'Track Title'" or "Artist Name Drops 'Track'"
    patterns = [
        r"^([A-Z][A-Za-z\s'.]+?)\s*[-–]\s*['\"](.+?)['\"]",
        r"^([A-Z][A-Za-z\s'.]+?)\s+(?:drops|releases|shares|debuts|unveils|delivers)\s+['\"](.+?)['\"]",
        r"^([A-Z][A-Za-z\s'.]+?)\s+(?:drops|releases|shares|debuts)\s+new",
        r"^([A-Z][A-Za-z\s'.]+?)\s+['\"](.+?)['\"]",
    ]
    for p in patterns:
        m = re.match(p, headline, re.IGNORECASE)
        if m:
            artist = m.group(1).strip()
            track  = m.group(2).strip() if m.lastindex >= 2 else ""
            # Sanity check — artist shouldn't be too long
            if len(artist.split()) <= 4:
                return artist, track
    return "", ""


# ── Main ──────────────────────────────────────────────────────────────────────

def pull_tier2_leads(limit: int = 100) -> list:
    """Pull from all tier 2 sources and deduplicate."""
    all_tracks = []
    seen = set()

    sources = [
        pull_shazam_hiphop,
        pull_spotify_rapcaviar,
        pull_apple_music_hiphop,
        pull_audiomack_trending,
        pull_the_source,
        pull_warmmusic_urban,
    ]

    for fn in sources:
        tracks = fn()
        for t in tracks:
            if not t.get("artist") or not t.get("track"):
                continue
            key = f"{t['artist'].lower()}|{t['track'].lower()}"
            if key not in seen:
                seen.add(key)
                all_tracks.append(t)
        time.sleep(2)

    print(f"\n[TIER2] Total unique tier 2 leads: {len(all_tracks)}")
    return all_tracks


if __name__ == "__main__":
    leads = pull_tier2_leads()
    print(f"\nSample:")
    for l in leads[:10]:
        print(f"  {l['artist']} — {l['track']} [{l['source']}]")
