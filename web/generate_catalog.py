"""
Generate data/unlock_catalog.json from data/leads.csv.

Run after each probe to add new JACKPOT/GUEST_UNCLAIMED leads to the
checkout catalog. Safe to re-run — skips existing entries.

Usage:
    python web/generate_catalog.py
"""

import os, sys, json, csv, hashlib, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from outreach.bounty_calculator import calculate_bounty

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
LEADS_FILE = os.path.join(DATA_DIR, "leads.csv")
TARGETS_FILE = os.path.join(DATA_DIR, "master_targets.csv")
CATALOG    = os.path.join(DATA_DIR, "unlock_catalog.json")


def _audit_id(artist: str, isrc: str) -> str:
    raw = f"{artist}{isrc}"
    return "TR-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _load_streams_lookup() -> dict:
    """Build ISRC → stream count map from master_targets.csv if available."""
    lookup = {}
    if not os.path.exists(TARGETS_FILE):
        return lookup
    with open(TARGETS_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            isrc = row.get("isrc", "").strip()
            if not isrc:
                continue
            # Try multiple possible column names
            for col in ("streams", "spotify_streams", "deezer_streams", "plays"):
                val = row.get(col, "")
                if val:
                    try:
                        lookup[isrc] = int(float(str(val).replace(",", "")))
                    except ValueError:
                        pass
                    break
    return lookup


def generate_catalog():
    if not os.path.exists(LEADS_FILE):
        print("[CATALOG] leads.csv not found — run the probe first")
        return {}

    existing = {}
    if os.path.exists(CATALOG):
        with open(CATALOG) as f:
            existing = json.load(f)

    streams_lookup = _load_streams_lookup()
    added = 0

    with open(LEADS_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") not in ("JACKPOT", "GUEST_UNCLAIMED"):
                continue

            artist  = row.get("artist", "Unknown").strip()
            track   = row.get("track",  "Unknown").strip()
            isrc    = row.get("isrc",   "").strip()

            aid = _audit_id(artist, isrc)
            if aid in existing:
                continue

            # Best stream count available
            streams = (
                streams_lookup.get(isrc)
                or _parse_int(row.get("streams"))
                or _parse_int(row.get("sniper_score"))
                or 0
            )

            bounty = calculate_bounty(streams, artist, track)

            existing[aid] = {
                "artist":      artist,
                "track":       track,
                "isrc":        isrc,
                "streams":     bounty["raw_streams"],
                "bounty_low":  bounty["low_fmt"],
                "bounty_high": bounty["high_fmt"],
                "priority":    bounty["priority"].replace("\u2014", "-"),
                "status":      row.get("status", "JACKPOT"),
            }
            added += 1
            print(f"  [+] {aid}  {artist} - {track}  ({bounty['priority']})")

    with open(CATALOG, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"\n[CATALOG] {added} new | {len(existing)} total | {CATALOG}")
    return existing


def _parse_int(val) -> int:
    if not val:
        return 0
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return 0


if __name__ == "__main__":
    generate_catalog()
