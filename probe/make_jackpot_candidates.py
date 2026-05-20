"""
Jackpot Candidates Filter
Pulls all UNKNOWN/unresolved tracks from all target CSVs into one file.
These are tracks with no ISRC in MusicBrainz/Deezer = highest SoundExchange jackpot probability.

Usage:
    python probe/make_jackpot_candidates.py
"""

import csv, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from probe.make_probe_ready import sx_isrc_link, sx_name_link, mb_link, songview_link, yt_link

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

SOURCE_FILES = [
    ("female_rappers_2024_present.csv",  "Female Rappers"),
    ("atl_remix_targets_2025.csv",       "ATL Remix"),
    ("gospel_soul_targets.csv",          "Gospel/Soul"),
]

OUT_FIELDS = [
    "artist", "track", "isrc", "list", "release_date", "eligibility",
    "sx_isrc_link", "sx_name_link", "musicbrainz_link", "songview_link", "youtube_link",
    "manual_check_notes", "estimated_recovery",
]

candidates = []

for fname, label in SOURCE_FILES:
    path = os.path.join(DATA_DIR, fname)
    if not os.path.exists(path):
        print(f"  [SKIP] {fname} not found")
        continue
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            isrc  = row.get("isrc", "").strip()
            elig  = row.get("eligibility", "").strip()
            src   = row.get("isrc_source", "").strip()
            artist = row.get("artist", "").strip()
            track  = row.get("track", "").strip()

            # Skip old songs unlikely to have active accruals
            if elig.startswith("CHECK"):
                continue
            # Keep only: no ISRC resolved (miss/blank) OR UNKNOWN date but known ISRC
            is_miss = src in ("miss", "") or not isrc
            if not is_miss:
                continue

            candidates.append({
                "artist":              artist,
                "track":               track,
                "isrc":                isrc,
                "list":                label,
                "release_date":        row.get("release_date", ""),
                "eligibility":         elig or "UNKNOWN",
                "sx_isrc_link":        sx_isrc_link(isrc),
                "sx_name_link":        sx_name_link(artist, track),
                "musicbrainz_link":    mb_link(artist, track, isrc),
                "songview_link":       songview_link(artist, track),
                "youtube_link":        yt_link(artist, track),
                "manual_check_notes":  "",
                "estimated_recovery":  "",
            })

# Sort: FULL eligible first, then PARTIAL, then UNKNOWN
def sort_key(r):
    e = r["eligibility"]
    if e.startswith("FULL"):    return 0
    if e.startswith("PARTIAL"): return 1
    return 2

candidates.sort(key=sort_key)

out_path = os.path.join(DATA_DIR, "jackpot_candidates.csv")
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=OUT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(candidates)

full    = sum(1 for r in candidates if r["eligibility"].startswith("FULL"))
partial = sum(1 for r in candidates if r["eligibility"].startswith("PARTIAL"))
unknown = sum(1 for r in candidates if r["eligibility"].startswith("UNKNOWN"))

print(f"Jackpot candidates: {len(candidates)} total")
print(f"  FULL eligible (2023+): {full}")
print(f"  PARTIAL (2019-2022):   {partial}")
print(f"  UNKNOWN date:          {unknown}")
print(f"Saved: {out_path}")
