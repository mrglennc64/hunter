"""
Chartmetric enrichment — fills IG/TikTok/country/label for Spotify candidates.

Input: spotify_candidates.csv (output of spotify_extract.py)
Output: artists_enriched.csv (same schema as artists.csv, ready to merge)

Requires: CHARTMETRIC_REFRESH_TOKEN in .env (get from chartmetric.com → Account → API)
Paid tier required for API access. For free-tier users, see chartmetric_manual.md.

Usage:
    python chartmetric_enrich.py
"""
import os
import csv
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import re
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

REFRESH_TOKEN = os.environ.get('CHARTMETRIC_REFRESH_TOKEN')
if not REFRESH_TOKEN:
    raise SystemExit(
        'Missing CHARTMETRIC_REFRESH_TOKEN in .env\n'
        'Get it from chartmetric.com → Account → Developers → API → Refresh Token\n'
        '(Requires Artist tier or higher — $140/mo)\n'
        'If on free tier, use chartmetric_manual.md workflow instead.'
    )

SCRIPT_DIR = Path(__file__).parent
INPUT_CSV = SCRIPT_DIR / 'spotify_candidates.csv'
OUTPUT_CSV = SCRIPT_DIR / 'artists_enriched.csv'

API_BASE = 'https://api.chartmetric.com/api'

# ── Auth ────────────────────────────────────────────────────
_token_cache = {'token': None, 'exp': 0}

def get_token():
    if _token_cache['token'] and time.time() < _token_cache['exp']:
        return _token_cache['token']
    data = json.dumps({'refreshtoken': REFRESH_TOKEN}).encode()
    req = urllib.request.Request(
        f'{API_BASE}/token',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as r:
        body = json.loads(r.read())
    _token_cache['token'] = body['token']
    _token_cache['exp'] = time.time() + body.get('expires_in', 3600) - 60
    return _token_cache['token']

# ── API helper ──────────────────────────────────────────────
def api_get(path, params=None):
    token = get_token()
    url = f'{API_BASE}{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get('Retry-After', 10))
                print(f'  rate-limited, waiting {wait}s')
                time.sleep(wait)
            elif e.code == 404:
                return None
            elif e.code == 401:
                _token_cache['token'] = None  # force refresh
                token = get_token()
            else:
                print(f'  HTTP {e.code} on {path}')
                return None
        except Exception as e:
            print(f'  err: {e}')
            time.sleep(1)
    return None

# ── Chartmetric queries ─────────────────────────────────────
def cm_lookup_by_spotify(spotify_id):
    """Map Spotify artist ID → Chartmetric artist object (includes cmid + urls)"""
    data = api_get('/artist', {'type': 'spotify', 'id': spotify_id})
    if not data or 'obj' not in data:
        return None
    return data['obj']

def cm_get_urls(cmid):
    """Social URLs for a Chartmetric artist"""
    data = api_get(f'/artist/{cmid}/urls')
    if not data or 'obj' not in data:
        return {}
    return data['obj']

def cm_get_artist_detail(cmid):
    """Full artist detail (country, label, verified status)"""
    data = api_get(f'/artist/{cmid}')
    if not data or 'obj' not in data:
        return {}
    return data['obj']

# ── Extract social handle from URL ──────────────────────────
def extract_handle(url, platform):
    if not url:
        return ''
    patterns = {
        'instagram': r'instagram\.com/([^/?#]+)',
        'tiktok': r'tiktok\.com/@([^/?#]+)',
    }
    m = re.search(patterns.get(platform, ''), url)
    return '@' + m.group(1) if m else url

def extract_spotify_id(spotify_url):
    m = re.search(r'artist/([a-zA-Z0-9]+)', spotify_url)
    return m.group(1) if m else None

# ── Main ────────────────────────────────────────────────────
def main():
    if not INPUT_CSV.exists():
        raise SystemExit(f'Input not found: {INPUT_CSV}\nRun spotify_extract.py first.')

    print('Testing Chartmetric auth...')
    get_token()
    print('Auth OK.\n')

    rows_in = list(csv.DictReader(INPUT_CSV.open(encoding='utf-8')))
    print(f'Input rows: {len(rows_in)}')

    rows_out = []
    for i, row in enumerate(rows_in, 1):
        name = row.get('name', '')
        spotify_url = row.get('spotify', '')
        sid = extract_spotify_id(spotify_url)
        if not sid:
            continue

        print(f'[{i}/{len(rows_in)}] {name}...')
        artist = cm_lookup_by_spotify(sid)
        if not artist:
            print('  not found on Chartmetric')
            rows_out.append({**row, 'verify': 'no-cm-match'})
            continue

        cmid = artist.get('id') or artist.get('cmid')
        urls = cm_get_urls(cmid) if cmid else {}
        detail = cm_get_artist_detail(cmid) if cmid else {}

        ig = extract_handle(urls.get('instagram', ''), 'instagram')
        tt = extract_handle(urls.get('tiktok', ''), 'tiktok')
        country = detail.get('code2') or detail.get('hometown_country') or ''
        labels = detail.get('current_label') or detail.get('label')
        if isinstance(labels, list):
            label = labels[0].get('name', '') if labels else ''
        elif isinstance(labels, dict):
            label = labels.get('name', '')
        else:
            label = labels or ''

        genres = detail.get('genres') or []
        if isinstance(genres, list) and genres:
            genre = genres[0].get('name', '') if isinstance(genres[0], dict) else genres[0]
        else:
            genre = row.get('genre', '')

        rows_out.append({
            'name': name,
            'instagram': ig,
            'tiktok': tt,
            'spotify': spotify_url,
            'genre': genre,
            'country': country,
            'followers_est': row.get('followers_est', ''),
            'distributor': label or 'unknown',
            'verify': 'enriched' if (ig or tt) else 'partial',
        })
        time.sleep(0.5)  # be polite

    # Write output
    with OUTPUT_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=[
            'name', 'instagram', 'tiktok', 'spotify',
            'genre', 'country', 'followers_est', 'distributor', 'verify'
        ])
        w.writeheader()
        w.writerows(rows_out)

    enriched = sum(1 for r in rows_out if r['verify'] == 'enriched')
    print(f'\nWrote {len(rows_out)} rows to {OUTPUT_CSV}')
    print(f'  {enriched} fully enriched (IG/TikTok found)')
    print(f'  {len(rows_out) - enriched} partial — verify manually or via Hunter')

if __name__ == '__main__':
    main()
