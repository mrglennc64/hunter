# Outreach Pipeline

End-to-end flow for building a qualified artist + publisher outreach list.

## Files

| File | Purpose |
|------|---------|
| `publishers.csv` | 146 real publishers (Nordic/UK/US/EU), size 1-50 staff |
| `artists.csv` | 327 real indie artists across 6 genres, 5k-250k followers |
| `publishers_verified.csv` | Empty template — move rows here after you verify LinkedIn/email |
| `artists_verified.csv` | Empty template — move rows here after verify/Hunter enrichment |
| `spotify_extract.py` | Mines Spotify editorial playlists → `spotify_candidates.csv` |
| `chartmetric_enrich.py` | Enriches Spotify candidates with IG/TikTok/country/label |

## Full pipeline (combined strategy)

```
Spotify editorial playlists
         │
         ▼
  spotify_extract.py  ──→  spotify_candidates.csv (name, spotify URL, followers)
         │
         ▼
  chartmetric_enrich.py  ──→  artists_enriched.csv (+ IG, TikTok, country, label)
         │
         ▼
  Merge into artists.csv, dedupe
         │
         ▼
  Hunter.io Domain Search  ──→  Fills email column
         │
         ▼
  artists_verified.csv (outreach-ready)
```

## Step 1 — Spotify extraction (free)

```bash
# one-time setup
pip install python-dotenv  # actually not needed, script uses stdlib only

# run
cd frontend/outreach
python spotify_extract.py
```

Output: `spotify_candidates.csv` — ~2000-3000 artists filtered to your follower range.

**To add more playlists**: edit `PLAYLISTS` list at top of script. Find playlist IDs by opening the playlist in Spotify → `...` → Share → Copy Spotify URI → the ID is the last segment (e.g. `37i9dQZF1DWWBHeXOYZf74`).

**Good playlists to add:**
- Any "Fresh Finds {Genre}" (Pop, Hip-Hop, Electronic, R&B)
- "New Music Friday {Country}" for each target market
- "RADAR {Country}" — Spotify's emerging artist program
- Genre-specific curator lists: "Alternative Sleaze", "Night Drive", "Bedroom Pop"

## Step 2A — Chartmetric enrichment via API (paid tier)

Requires **Chartmetric Artist tier** ($140/mo) for API access.

1. chartmetric.com → Account → Developers → API → copy **Refresh Token**
2. Add to `.env` at repo root:
   ```
   CHARTMETRIC_REFRESH_TOKEN=<your_token>
   ```
3. Run:
   ```bash
   python chartmetric_enrich.py
   ```
4. Output: `artists_enriched.csv` with IG/TikTok/country/label filled in

## Step 2B — Chartmetric manual workflow (free tier)

Free tier has 100 lookups/day but no API access. Use the web UI:

1. **chartmetric.com → Discovery → Artists**
2. Filter: Followers 5,000-250,000, select genres (Hip-Hop, Pop, Electronic, R&B, Trap, EDM)
3. Filter by country (Sweden, UK, US, Germany, etc. — run separate queries)
4. **Export CSV** — free tier limits export size
5. Spreadsheet has: artist, IG, TikTok, Spotify, followers, country, label
6. Paste into `artists.csv` format, set `verify=enriched`

**Alternative free sources for the same data:**
- **MusicBrainz** (free, API-accessible) — has artist name + country + social links (via relationships)
- **Spotify Artist profile** shows IG/Twitter when artist added them — scrape the artist page `open.spotify.com/artist/<id>` (gray area but allowed for outreach)
- **Genius** (free API) — artist pages include social links

## Step 3 — Merge and dedupe

```bash
# After getting enriched data, merge with existing artists.csv:
cat artists.csv artists_enriched.csv | awk -F',' '!seen[$1]++' > artists_merged.csv
```

Or in Excel: concat → Remove Duplicates by `name`.

## Step 4 — Hunter.io email enrichment

1. Extract website/domain column from `publishers.csv` (publishers have websites)
2. Hunter → Domain Search → paste domain list
3. Hunter returns emails with confidence scores
4. Paste `email` back into your CSV
5. Move verified rows to `publishers_verified.csv`

**For artists** (no personal domain): use Hunter's Email Finder with `name + label_domain` instead — works when the artist is signed to a label with a public domain.

## Recommended weekly cadence

| Week | Task | Output |
|------|------|--------|
| 1 | Run `spotify_extract.py` across 20 playlists | ~2000 candidates |
| 1 | Chartmetric web UI enrichment (free tier, 100/day × 7 days) | 700 enriched |
| 2 | Hunter.io email enrichment on enriched list | Emails for 400+ |
| 2 | Manual verify LinkedIn URLs on `publishers.csv` top 50 | 50 verified publishers |
| 3 | First outreach batch | — |

## Security

- `.env` is gitignored — never commit credentials
- Spotify creds in this session should be rotated at dashboard.spotify.com once testing is done
- Chartmetric refresh token rotates every 90 days — check if auth starts failing
