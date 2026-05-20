"""
Release Date Resolver + Black Box Eligibility Checker
Fetches release dates via MusicBrainz/Deezer and calculates SoundExchange eligibility.

SoundExchange Black Box Rules:
  - Royalties held in suspense for 3 years from accrual date
  - File LOD within 3-year window = full recovery
  - Tracks still actively streaming = new royalties accruing right now
  - MMA (2018) covers ALL recordings regardless of age

Eligibility buckets:
  FULL     — released within 3 years (2023-present) — full lookback available
  PARTIAL  — released 2019-2022 — some accruals may have lapsed, recent streams still valid
  CHECK    — released before 2019 — depends on whether still streaming actively
  UNKNOWN  — no release date found

Usage:
    python collectors/get_release_dates.py data/female_rappers_2024_present.csv
    python collectors/get_release_dates.py data/gospel_soul_targets.csv
    python collectors/get_release_dates.py data/atl_remix_targets_2025.csv
"""

import sys, os, csv, time, requests
from datetime import date, datetime

CUTOFF_FULL    = date(2023, 1, 1)   # within 3-year window
CUTOFF_PARTIAL = date(2019, 1, 1)   # partial recovery possible

MB_HEADERS = {"User-Agent": "MusicRightsAuditor/1.0 (contact@traproyalties.com)"}

TODAY = date.today()


def get_date_musicbrainz(artist: str, track: str, isrc: str = "") -> str | None:
    try:
        if isrc and isrc.lower() not in ("nan", "", "none"):
            url = f"https://musicbrainz.org/ws/2/isrc/{isrc}?fmt=json&inc=releases"
            res = requests.get(url, headers=MB_HEADERS, timeout=10).json()
            recordings = res.get("recordings", [])
            for rec in recordings:
                for rel in rec.get("releases", []):
                    d = rel.get("date", "")
                    if len(d) >= 4:
                        return d
        # Fallback: title search
        url = (f"https://musicbrainz.org/ws/2/recording"
               f"?query=artist:\"{artist}\" AND recording:\"{track}\"&fmt=json&limit=1")
        res = requests.get(url, headers=MB_HEADERS, timeout=10).json()
        recs = res.get("recordings", [])
        if recs:
            releases = recs[0].get("releases", [])
            if releases:
                d = releases[0].get("date", "")
                if len(d) >= 4:
                    return d
    except Exception as e:
        print(f"  [MB DATE ERROR] {e}")
    return None


def get_date_deezer(artist: str, track: str) -> str | None:
    try:
        url = f"https://api.deezer.com/search?q=track:\"{track}\" artist:\"{artist}\""
        res = requests.get(url, timeout=10).json()
        if res.get("data"):
            track_id = res["data"][0]["id"]
            detail = requests.get(f"https://api.deezer.com/track/{track_id}", timeout=10).json()
            album_id = detail.get("album", {}).get("id")
            if album_id:
                album = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=10).json()
                return album.get("release_date", "")
    except Exception as e:
        print(f"  [DEEZER DATE ERROR] {e}")
    return None


def parse_date(d: str) -> date | None:
    if not d:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(d[:len(fmt.replace("%Y","0000").replace("%m","00").replace("%d","00"))], fmt).date()
        except:
            pass
    try:
        return date(int(d[:4]), 1, 1)
    except:
        return None


def eligibility(release_date: date | None) -> str:
    if not release_date:
        return "UNKNOWN"
    if release_date >= CUTOFF_FULL:
        years = (TODAY - release_date).days / 365.25
        return f"FULL ({years:.1f}yr old)"
    elif release_date >= CUTOFF_PARTIAL:
        return f"PARTIAL ({release_date.year})"
    else:
        return f"CHECK — streaming? ({release_date.year})"


input_path = sys.argv[1] if len(sys.argv) > 1 else "data/female_rappers_2024_present.csv"

with open(input_path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) if rows else []

for col in ["release_date", "eligibility"]:
    if col not in fieldnames:
        fieldnames.append(col)

total = len(rows)
found = 0

for i, row in enumerate(rows):
    artist = row.get("artist", "").strip()
    track  = row.get("track",  "").strip()
    isrc   = row.get("isrc",   "").strip()

    if row.get("release_date", "").strip():
        print(f"[{i+1}/{total}] SKIP (has date): {artist} - {track} -> {row['release_date']}")
        continue

    print(f"[{i+1}/{total}] {artist} - {track}")

    d = get_date_musicbrainz(artist, track, isrc)
    time.sleep(1.5)

    if not d:
        d = get_date_deezer(artist, track)
        time.sleep(1)

    parsed = parse_date(d)
    elig   = eligibility(parsed)

    row["release_date"] = d or ""
    row["eligibility"]  = elig

    if d:
        found += 1
        print(f"  DATE: {d} | {elig}")
    else:
        row["eligibility"] = "UNKNOWN"
        print(f"  MISS")

    time.sleep(1)

with open(input_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(f"\nDone: {found} dates found / {total - found} unknown")
print(f"Saved: {input_path}")
print(f"Now regenerate template: python probe/make_sheets_template.py {input_path}")
