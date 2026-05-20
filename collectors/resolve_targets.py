"""
Resolve ISRCs for all target CSVs via MusicBrainz + Deezer.
Updates the CSV in place — skips rows that already have an ISRC.

Usage:
    python collectors/resolve_targets.py data/female_rappers_2024_present.csv
    python collectors/resolve_targets.py data/gospel_soul_targets.csv
    python collectors/resolve_targets.py data/atl_remix_targets_2025.csv
"""

import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from collectors.isrc_resolver import resolve_isrc
import time

input_path = sys.argv[1] if len(sys.argv) > 1 else "data/female_rappers_2024_present.csv"

with open(input_path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys()) if rows else []

if "isrc_source" not in fieldnames:
    fieldnames.append("isrc_source")

total   = len(rows)
hits    = 0
misses  = 0
skipped = 0

for i, row in enumerate(rows):
    artist = row.get("artist", "").strip()
    track  = row.get("track",  "").strip()
    isrc   = row.get("isrc",   "").strip()

    if isrc and isrc.lower() not in ("nan", "", "none"):
        skipped += 1
        print(f"[{i+1}/{total}] SKIP (has ISRC): {artist} - {track} -> {isrc}")
        continue

    print(f"[{i+1}/{total}] {artist} - {track}")
    resolved_isrc, source = resolve_isrc(artist, track)

    if resolved_isrc:
        row["isrc"]        = resolved_isrc
        row["isrc_source"] = source
        hits += 1
        print(f"  FOUND: {resolved_isrc} via {source}")
    else:
        row["isrc_source"] = "miss"
        misses += 1
        print(f"  MISS")

    time.sleep(2)

# Write back
with open(input_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(f"\nDone: {hits} resolved / {misses} misses / {skipped} already had ISRC")
print(f"Saved: {input_path}")
print(f"Now run: python probe/make_probe_ready.py {input_path}")
