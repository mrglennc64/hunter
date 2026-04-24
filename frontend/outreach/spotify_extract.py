"""
Spotify artist extractor for outreach list expansion.

Pulls artists from editorial/curated playlists, filters by follower count,
outputs CSV matching frontend/outreach/artists.csv schema.

Usage:
    pip install requests python-dotenv
    python spotify_extract.py

Config: edit PLAYLISTS list + FOLLOWER_MIN/MAX below.
Output: spotify_candidates.csv (same directory)
"""
import os
import csv
import json
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ── Load .env ───────────────────────────────────────────────
def load_env(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

ROOT = Path(__file__).resolve().parents[2]
load_env(ROOT / '.env')

CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
if not CLIENT_ID or not CLIENT_SECRET:
    raise SystemExit('Missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in .env')

# ── Config ──────────────────────────────────────────────────
FOLLOWER_MIN = 5_000
FOLLOWER_MAX = 250_000

# Playlists to mine. Find more: open playlist in Spotify, click "..." → Share → Copy Spotify URI,
# the ID is the last segment.
PLAYLISTS = [
    # (playlist_id, genre_hint, country_hint)
    ('37i9dQZF1DWWBHeXOYZf74', 'mixed', 'US'),         # Fresh Finds
    ('37i9dQZF1DX2RxBh64BHjQ', 'hip-hop', 'US'),       # Fresh Finds Hip-Hop
    ('37i9dQZF1DWXIiRI40uDAY', 'pop', 'US'),           # Fresh Finds Pop
    ('37i9dQZF1DWWwzidNQX6jx', 'electronic', 'US'),    # Fresh Finds Basement
    ('37i9dQZF1DWZe5W4fNbPFv', 'mixed', 'SE'),         # New Music Friday Sweden
    ('37i9dQZF1DX0YpTOdaLEn8', 'mixed', 'NO'),         # New Music Friday Norway
    ('37i9dQZF1DX2Nc3B70tvx0', 'mixed', 'DK'),         # New Music Friday Denmark
    ('37i9dQZF1DX4SBhb3fqCJd', 'mixed', 'UK'),         # Fresh Finds UK (if live)
    ('37i9dQZF1DWWjGdmeTyeJ6', 'mixed', 'US'),         # RADAR US (if live)
]
# NOTE: Some IDs may 404 if Spotify retired/renamed the playlist.
# Script will skip and continue — check output for which ones worked.

OUTPUT_CSV = Path(__file__).parent / 'spotify_candidates.csv'

# ── Auth ────────────────────────────────────────────────────
def get_token():
    creds = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()
    data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode()
    req = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=data,
        headers={'Authorization': f'Basic {creds}',
                 'Content-Type': 'application/x-www-form-urlencoded'}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())['access_token']

# ── API helper with retry ───────────────────────────────────
def api_get(url, token):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get('Retry-After', 5))
                print(f'  rate-limited, waiting {wait}s')
                time.sleep(wait)
            elif e.code == 404:
                return None
            elif e.code == 401:
                raise  # token expired — caller should refresh
            else:
                print(f'  HTTP {e.code} on {url[:80]}')
                return None
        except Exception as e:
            print(f'  err: {e}')
            time.sleep(1)
    return None

# ── Harvest ─────────────────────────────────────────────────
def collect_artist_ids_from_playlist(playlist_id, token):
    ids = set()
    url = f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks?limit=100'
    while url:
        data = api_get(url, token)
        if not data or 'items' not in data:
            return ids
        for item in data['items']:
            track = item.get('track') or {}
            for art in track.get('artists', []) or []:
                if art.get('id'):
                    ids.add(art['id'])
        url = data.get('next')
    return ids

def fetch_artists_batch(ids, token):
    """ /v1/artists accepts up to 50 IDs at a time """
    results = []
    ids = list(ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i+50]
        url = f'https://api.spotify.com/v1/artists?ids={",".join(chunk)}'
        data = api_get(url, token)
        if data and 'artists' in data:
            results.extend([a for a in data['artists'] if a])
        time.sleep(0.1)
    return results

# ── Main ────────────────────────────────────────────────────
def main():
    print('Authenticating...')
    token = get_token()
    print('Token OK.')

    all_ids = set()
    for pid, genre, country in PLAYLISTS:
        print(f'Playlist {pid} ({genre}/{country})...')
        ids = collect_artist_ids_from_playlist(pid, token)
        print(f'  +{len(ids)} artists')
        all_ids.update(ids)

    print(f'\nTotal unique artists: {len(all_ids)}')
    print('Fetching artist details (follower counts, genres)...')

    artists = fetch_artists_batch(all_ids, token)
    print(f'Retrieved {len(artists)} profiles.\n')

    kept = []
    for a in artists:
        followers = a.get('followers', {}).get('total', 0)
        if FOLLOWER_MIN <= followers <= FOLLOWER_MAX:
            kept.append(a)

    print(f'In follower range {FOLLOWER_MIN}-{FOLLOWER_MAX}: {len(kept)}')

    # Write CSV matching your artists.csv schema
    with OUTPUT_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'instagram', 'tiktok', 'spotify',
                    'genre', 'country', 'followers_est', 'distributor', 'verify'])
        for a in kept:
            name = a['name']
            spotify_url = a['external_urls'].get('spotify', '')
            genres = a.get('genres', [])
            genre = genres[0] if genres else 'unknown'
            followers = a['followers']['total']
            # Bucket follower count
            if followers < 25_000:
                bucket = '5k-25k'
            elif followers < 100_000:
                bucket = '25k-100k'
            elif followers < 250_000:
                bucket = '100k-250k'
            else:
                bucket = '250k+'
            w.writerow([name, '', '', spotify_url, genre, '', bucket, '', 'research'])

    print(f'\nWrote {len(kept)} candidates to {OUTPUT_CSV}')
    print('Next: open the CSV, dedupe against artists.csv, and run through Hunter for emails.')

if __name__ == '__main__':
    main()
