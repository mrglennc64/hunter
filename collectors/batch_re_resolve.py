"""
Batch Re-Resolver — YouTube Music + Deezer ISRC Recovery Pass
==============================================================
Goes back through raw_collected.csv and tries to save ISRCs that
MusicBrainz + Deezer (first pass) missed.

Two-stage approach:
  1. ytmusicapi  — unofficial YouTube Music API, zero credentials needed
  2. Deezer      — re-tried with cleaned/simplified queries

Install:
    pip install ytmusicapi

Usage:
    python collectors/batch_re_resolve.py                  # all misses
    python collectors/batch_re_resolve.py --limit 100      # first 100
    python collectors/batch_re_resolve.py --csv data/raw_collected.csv
"""

import os
import csv
import time
import argparse
import re
import requests

DATA_DIR      = os.path.join(os.path.dirname(__file__), "..", "data")
DEFAULT_INPUT = os.path.join(DATA_DIR, "raw_collected.csv")
OUTPUT_FILE   = os.path.join(DATA_DIR, "re_resolved.csv")


# ── Text cleaning ──────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip remix / feat noise from title or artist for a cleaner search."""
    text = re.sub(r'\s*[\(\[].*?[\)\]]', '', text)          # (anything) [anything]
    text = re.sub(r'\s*feat(?:uring)?\.?\s+.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*ft\.?\s+.*',             '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*-\s*remix.*',            '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*official.*',             '', text, flags=re.IGNORECASE)
    return text.strip()


def _artist_first(artist: str) -> str:
    """Return just the primary artist (before & / feat / x)."""
    artist = re.split(r'\s*[,&]\s*|\s+feat\.?\s+|\s+ft\.?\s+|\s+x\s+', artist, maxsplit=1)[0]
    return artist.strip()


# ── Stage 1: YouTube Music ─────────────────────────────────────────────────────

def _get_yt() -> object | None:
    try:
        from ytmusicapi import YTMusic
        return YTMusic()
    except ImportError:
        print("[YTM] Install ytmusicapi:  pip install ytmusicapi")
        return None


def _extract_isrc_from_song(details: dict) -> str | None:
    """
    Walk common ytmusicapi response paths looking for an ISRC string.
    Paths vary by track — we check several locations.
    """
    # Path 1: microformat renderer
    mf = details.get("microformat", {}).get("microformatDataRenderer", {})
    for key in ("externalId", "isrc", "musicVideoType"):
        val = mf.get(key, "")
        if val and re.match(r'^[A-Z]{2}[A-Z0-9]{3}\d{7}$', str(val)):
            return val

    # Path 2: videoDetails musicVideoType sometimes encodes ISRC
    vd = details.get("videoDetails", {})
    for key in ("isrc", "externalVideoId"):
        val = vd.get(key, "")
        if val and re.match(r'^[A-Z]{2}[A-Z0-9]{3}\d{7}$', str(val)):
            return val

    # Path 3: deep scan of entire response for anything matching ISRC format
    raw = str(details)
    matches = re.findall(r'\b([A-Z]{2}[A-Z0-9]{3}\d{7})\b', raw)
    if matches:
        return matches[0]

    return None


def resolve_isrc_ytmusic(yt, artist: str, track: str) -> str | None:
    """
    Search YouTube Music for the track. Try to pull ISRC from metadata.
    Falls back to a cleaned query if the first search returns nothing.
    """
    queries = [
        f"{artist} {track}",
        f"{_artist_first(artist)} {_clean(track)}",
        f"{_clean(artist)} {_clean(track)}",
    ]

    for q in queries:
        try:
            results = yt.search(q, filter="songs")
            if not results:
                continue

            for result in results[:3]:
                video_id = result.get("videoId")
                if not video_id:
                    continue

                details = yt.get_song(video_id)
                isrc = _extract_isrc_from_song(details)
                if isrc:
                    return isrc

            time.sleep(0.4)

        except Exception as e:
            print(f"  [YTM ERR] {e}")
            time.sleep(1)

    return None


# ── Stage 2: Deezer (aggressive retry) ────────────────────────────────────────

def resolve_isrc_deezer_retry(artist: str, track: str) -> str | None:
    """
    Re-try Deezer with progressively simplified queries.
    First pass already tried exact artist+track — here we strip noise.
    """
    queries = [
        (f'artist:"{_artist_first(artist)}" track:"{_clean(track)}"', "structured-clean"),
        (f'"{_artist_first(artist)}" "{_clean(track)}"',              "phrase-clean"),
        (f'{_artist_first(artist)} {_clean(track)}',                  "loose"),
    ]

    for q, label in queries:
        try:
            res = requests.get(
                f"https://api.deezer.com/search?q={requests.utils.quote(q)}",
                timeout=10,
            ).json()

            if res.get("data"):
                track_id = res["data"][0]["id"]
                detail = requests.get(
                    f"https://api.deezer.com/track/{track_id}", timeout=10
                ).json()
                isrc = detail.get("isrc")
                if isrc:
                    return isrc

            time.sleep(0.5)

        except Exception as e:
            print(f"  [DEEZER ERR] {label}: {e}")

    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def re_resolve(input_csv: str = DEFAULT_INPUT, limit: int = 0) -> list:
    """
    Read input_csv, find rows missing ISRC, run two-stage recovery.
    Writes all rows (updated) to re_resolved.csv.
    Returns list of recovered rows.
    """
    if not os.path.exists(input_csv):
        print(f"[RE-RESOLVE] File not found: {input_csv}")
        return []

    yt = _get_yt()    # None if ytmusicapi not installed — Deezer still runs

    with open(input_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys()) if rows else []
    for col in ("isrc", "isrc_source"):
        if col not in fieldnames:
            fieldnames.append(col)

    missing = [
        r for r in rows
        if not r.get("isrc") or str(r.get("isrc", "")).strip() in ("", "nan", "NaN", "None")
    ]
    if limit:
        missing = missing[:limit]

    print(f"[RE-RESOLVE] {len(missing)} tracks missing ISRC")
    print(f"[RE-RESOLVE] Stages: {'YTMusic + ' if yt else ''}Deezer retry")
    print()

    recovered  = []
    still_miss = 0

    for i, row in enumerate(missing, 1):
        artist = row.get("artist", "").strip()
        track  = row.get("track",  "").strip()

        if not artist or not track:
            still_miss += 1
            continue

        print(f"  [{i}/{len(missing)}] {artist} — {track[:50]}")

        isrc   = None
        source = None

        # Stage 1 — YouTube Music
        if yt:
            isrc = resolve_isrc_ytmusic(yt, artist, track)
            if isrc:
                source = "ytmusic"

        # Stage 2 — Deezer retry (only if YTM missed)
        if not isrc:
            isrc = resolve_isrc_deezer_retry(artist, track)
            if isrc:
                source = "deezer-retry"

        if isrc:
            row["isrc"]        = isrc
            row["isrc_source"] = source
            recovered.append(row)
            print(f"    [FOUND] {isrc} via {source}")
        else:
            row["isrc_source"] = "miss"
            still_miss += 1
            print(f"    [MISS]")

        time.sleep(0.3)

    # Merge recovered ISRCs back into the full rows list
    recovered_index = {
        f"{r['artist'].lower()}|{r['track'].lower()}": r
        for r in recovered
    }
    for row in rows:
        key = f"{row.get('artist','').lower()}|{row.get('track','').lower()}"
        if key in recovered_index:
            row["isrc"]        = recovered_index[key]["isrc"]
            row["isrc_source"] = recovered_index[key]["isrc_source"]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    pct = round(len(recovered) / len(missing) * 100) if missing else 0
    print(f"\n[RE-RESOLVE] Recovered {len(recovered)} / {len(missing)} ({pct}%)")
    print(f"[RE-RESOLVE] Saved → {OUTPUT_FILE}")
    print(f"\n  Next steps:")
    print(f"    python run_pipeline.py --stage enrich   # re_resolved.csv → enriched")
    print(f"    python run_pipeline.py --stage score")
    print(f"    python run_pipeline.py --stage probe --batch 100")
    return recovered


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YTMusic + Deezer ISRC recovery")
    parser.add_argument("--csv",   default=DEFAULT_INPUT, help="Input CSV")
    parser.add_argument("--limit", type=int, default=0,   help="Max misses to attempt")
    args = parser.parse_args()

    recovered = re_resolve(input_csv=args.csv, limit=args.limit)
    if recovered:
        print(f"\nTop recovered ISRCs:")
        for r in recovered[:20]:
            print(f"  {r['isrc']}  {r['artist']} — {r['track'][:50]}")
