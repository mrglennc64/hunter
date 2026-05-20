"""
Manual Probe-Ready CSV Generator
Creates a spreadsheet with direct SoundExchange links for fast manual checking.
No dependencies — stdlib only.

Usage:
    python probe/make_probe_ready.py data/atl_remix_targets_2025.csv
    python probe/make_probe_ready.py data/female_rappers_2024_present.csv
"""

import sys, os, csv, re
from urllib.parse import quote_plus

input_path = sys.argv[1] if len(sys.argv) > 1 else "data/atl_remix_targets_2025.csv"
base = os.path.splitext(os.path.basename(input_path))[0]
output_path = os.path.join(os.path.dirname(input_path), f"{base}_probe_ready.csv")

REMIX_PAT = re.compile(r"remix|live|version|ft\.|feat\.|featuring", re.IGNORECASE)

def sx_isrc_link(isrc):
    if isrc and isrc.lower() not in ("nan", "", "none"):
        return f"https://isrc.soundexchange.com/#/search?searchType=code&query={isrc.strip()}"
    return ""

def sx_name_link(artist, track):
    clean = re.split(r"\(|ft\.|feat\.|[Ff]eaturing", track)[0].strip()
    artist_clean = re.split(r"ft\.|feat\.|[Ff]eaturing|,|&", artist)[0].strip()
    q = quote_plus(f"{artist_clean} {clean}")
    return f"https://isrc.soundexchange.com/#/search?searchType=name&query={q}"

def yt_link(artist, track):
    return f"https://www.youtube.com/results?search_query={quote_plus(artist + ' ' + track)}"

def mb_link(artist, track, isrc):
    """MusicBrainz — direct ISRC lookup if available, else title+artist search."""
    if isrc and isrc.lower() not in ("nan", "", "none"):
        return f"https://musicbrainz.org/isrc/{isrc.strip()}"
    clean = re.split(r"\(|ft\.|feat\.|[Ff]eaturing", track)[0].strip()
    artist_clean = re.split(r"ft\.|feat\.|[Ff]eaturing|,|&", artist)[0].strip()
    q = quote_plus(f"{artist_clean} {clean}")
    return f"https://musicbrainz.org/search?query={q}&type=recording"

def songview_link(artist, track):
    """BMI Songview — searches both ASCAP + BMI simultaneously."""
    clean = re.split(r"\(|ft\.|feat\.|[Ff]eaturing", track)[0].strip()
    return f"https://repertoire.bmi.com/search?title={quote_plus(clean)}&searchIn=songview"

rows = []
with open(input_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    orig_fields = reader.fieldnames or []
    # Normalize column names
    norm = {c: c.strip().lower().replace(" ", "_") for c in orig_fields}
    for row in reader:
        r = {norm[k]: (v or "").strip() for k, v in row.items()}
        # Handle Song → track alias
        if "song" in r and "track" not in r:
            r["track"] = r.pop("song")
        artist = r.get("artist", "")
        track  = r.get("track",  "")
        isrc   = r.get("isrc",   "")
        if not artist:
            continue
        score = 40 if REMIX_PAT.search(track) else 0
        r["sniper_score"]        = score
        r["sx_isrc_link"]        = sx_isrc_link(isrc)
        r["sx_name_link"]        = sx_name_link(artist, track)
        r["musicbrainz_link"]    = mb_link(artist, track, isrc)
        r["songview_link"]       = songview_link(artist, track)
        r["youtube_link"]        = yt_link(artist, track)
        r["manual_check_notes"]  = ""
        r["estimated_recovery"]  = ""
        rows.append(r)

# Sort remixes first
rows.sort(key=lambda r: -r["sniper_score"])

out_fields = ["artist", "track", "isrc", "sniper_score",
              "sx_isrc_link", "sx_name_link",
              "musicbrainz_link", "songview_link",
              "youtube_link", "manual_check_notes", "estimated_recovery"]
# append any original extra fields
for f in [norm[c] for c in orig_fields]:
    if f not in out_fields and f not in ("song",):
        out_fields.append(f)

with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

remix_count = sum(1 for r in rows if r["sniper_score"] > 0)
print(f"Probe file created: {output_path}")
print(f"  {len(rows)} tracks | {remix_count} remixes/features prioritized (score=40)")
print("Open in Google Sheets - sort by sniper_score - click sx_isrc_link one by one")
print("Only mark JACKPOT after seeing 0 results on BOTH isrc link AND name link")
