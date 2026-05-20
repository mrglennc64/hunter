"""
Remix Lead Collector — MusicBrainz + YouTube Title Parser
Targets featured artists on remixes who are almost never registered with SoundExchange.

Strategy:
  1. Search MusicBrainz for remixes of seed artists (high-stream acts)
  2. Parse YouTube-style "feat." patterns from titles to extract guest names
  3. Return {artist: GUEST, track: ORIGINAL_REMIX} pairs as leads

Why remixes hit harder than originals:
  - Guest artist appears on the ISRC but never filed their own LOD
  - Remix often uses original ISRC → royalties pile in "black box"
  - Labels file for main artist, never for the feature
  - 2022-2025 remix era = massive unclaimed stack
"""

import time
import re
import requests

MB_BASE = "https://musicbrainz.org/ws/2"
MB_HEADERS = {
    "User-Agent": "TrapRoyaltiesAudit/1.0 (audit@traproyalties.com)",
    "Accept": "application/json",
}

# High-stream seed artists whose remixes generate the most royalties
SEED_ARTISTS = [
    # Tier 1 — for remix guest extraction
    "Doja Cat", "Nicki Minaj", "Drake", "Cardi B", "Megan Thee Stallion",
    "SZA", "Beyonce", "Future", "Travis Scott", "Lil Baby",
    "21 Savage", "Post Malone", "Kendrick Lamar", "Tyler The Creator",
    "Roddy Ricch", "Gunna", "Young Thug", "Lil Uzi Vert",
    "Dababy", "Polo G", "Jack Harlow", "Doechii", "GloRilla",
    "Ice Spice", "Sexyy Red", "Flo Milli", "Coi Leray",
    "A Boogie Wit Da Hoodie", "Lil Durk", "NBA YoungBoy",
    "Tyla", "Victoria Monet", "Armani White", "Kodak Black",
    # Tier 2 — urban mid-tier, prime black box targets
    "Latto", "Lakeyah", "Monaleo", "Erica Banks", "BIA",
    "Rexx Life Raj", "Mozzy", "Yhung T.O.", "SOB x RBE",
    "Saucy Santana", "Morray", "Toosii", "Rylo Rodriguez",
    "DDG", "SoFaygo", "Sleepy Hallow", "Sheff G",
    "Clavish", "Central Cee", "Headie One", "Digga D",
    "Lil Tjay", "Fivio Foreign", "Kay Flock", "Sha Ek",
    "Babyface Ray", "Veeze", "Boldy James", "Stove God Cooks",
    "Ransom", "Rome Streetz", "Flee Lord", "Ransom",
    "Mariah the Scientist", "Summer Walker", "Ari Lennox",
    "Masego", "Joyce Wrice", "Cleo Sol", "Ama Lou",
    "Brent Faiyaz", "Destin Conrad", "Giveon", "Emotional Oranges",
    "Smino", "Saba", "Noname", "Mick Jenkins",
    "Cordae", "JID", "Reason", "EARTHGANG",
]

FEAT_PATTERNS = [
    r'feat(?:uring)?\.?\s+([^(\[\]]+)',
    r'ft\.?\s+([^(\[\]]+)',
    r'\(with\s+([^)]+)\)',
    r'&\s+([A-Z][^(&\[]+)',
    r'x\s+([A-Z][^(x\[]+)',
]


def extract_featured_artists(title: str) -> list:
    """Pull featured artist names out of a remix/collab title."""
    features = []
    title_lower = title.lower()

    # Only process if it looks like a remix/collab
    if not any(kw in title_lower for kw in ["remix", "feat", "ft.", " & ", " x ", "with "]):
        return []

    NON_ARTIST = {"remix", "instrumental", "edit", "radio", "version", "mix", "extended", "acoustic"}

    for pattern in FEAT_PATTERNS:
        matches = re.findall(pattern, title, re.IGNORECASE)
        for m in matches:
            # Clean up multiple artists separated by & or ,
            for artist in re.split(r'[,&]', m):
                clean = artist.strip().strip('"').strip("'")
                clean = re.sub(r'\s*\(.*', '', clean).strip()
                clean = clean.strip(')')  # strip orphaned closing paren
                clean = clean.strip()
                if len(clean) > 2 and clean not in features:
                    # Skip if it's a production term, not a name
                    if any(kw in clean.lower() for kw in NON_ARTIST):
                        continue
                    features.append(clean)

    return features


def search_remixes_for_artist(artist: str, limit: int = 25) -> list:
    """Search MusicBrainz for remix recordings featuring this artist."""
    leads = []

    # Search for recordings with "remix" in title credited to this artist
    params = {
        "query": f'recording:remix AND artistname:"{artist}"',
        "limit": limit,
        "fmt": "json",
    }
    try:
        res = requests.get(f"{MB_BASE}/recording", params=params,
                           headers=MB_HEADERS, timeout=15)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"  [MB ERROR] {artist}: {e}")
        return []

    for rec in data.get("recordings", []):
        title = rec.get("title", "")
        if not title:
            continue

        # Get artist credits
        credits = rec.get("artist-credit", [])
        main_artist = ""
        for c in credits:
            if isinstance(c, dict) and c.get("artist"):
                main_artist = c["artist"].get("name", "")
                break

        # Extract ISRC if available
        isrc = ""
        if rec.get("isrcs"):
            isrc = rec["isrcs"][0]

        # Check if it's a collab/remix with a guest
        feat_artists = extract_featured_artists(title)

        if feat_artists:
            for feat in feat_artists:
                # The GUEST artist is the lead — they're likely unregistered
                leads.append({
                    "artist": feat,
                    "track": title,
                    "isrc": isrc,
                    "main_artist": main_artist or artist,
                    "source": "remix_collector",
                    "chart": "mb-remix",
                })
        else:
            # Even without feat. pattern, collab tracks are valuable
            if "&" in main_artist or "feat" in title.lower():
                leads.append({
                    "artist": main_artist or artist,
                    "track": title,
                    "isrc": isrc,
                    "main_artist": main_artist or artist,
                    "source": "remix_collector",
                    "chart": "mb-remix",
                })

    return leads


def search_known_remix_pairs() -> list:
    """
    Hardcoded high-value remix pairs — confirmed blockbusters where
    guest artist royalties are almost certainly sitting unclaimed.
    """
    pairs = [
        # (guest_artist, track_title, main_artist)
        ("Nicki Minaj",      "Say So (Remix)",                "Doja Cat"),
        ("Nicki Minaj",      "Motorsport",                    "Migos"),
        ("Cardi B",          "MotorSport",                    "Migos"),
        ("Beyonce",          "Savage (Remix)",                "Megan Thee Stallion"),
        ("Nicki Minaj",      "Swalla (Remix)",                "Jason Derulo"),
        ("Cardi B",          "Finesse (Remix)",               "Bruno Mars"),
        ("Nicki Minaj",      "Tusa",                          "Karol G"),
        ("Future",           "Mask Off (Remix)",              "Kendrick Lamar"),
        ("Drake",            "In My Feelings (Remix)",        "Drake"),
        ("Lil Baby",         "Woah (Remix)",                  "Lil Baby"),
        ("Nicki Minaj",      "No Frauds",                     "Drake"),
        ("Cardi B",          "I Like It",                     "Bad Bunny"),
        ("Bad Bunny",        "I Like It",                     "Cardi B"),
        ("Nicki Minaj",      "Good Form (Remix)",             "Nicki Minaj"),
        ("Lil Uzi Vert",     "Bad and Boujee",                "Migos"),
        ("Travis Scott",     "Goosebumps (Remix)",            "Travis Scott"),
        ("Megan Thee Stallion", "WAP (Remix)",               "Cardi B"),
        ("Nicki Minaj",      "Trollz",                        "6ix9ine"),
        ("Drake",            "Life Is Good (Remix)",          "Future"),
        ("Roddy Ricch",      "The Box (Remix)",               "Roddy Ricch"),
        ("Ice Spice",        "Munch (Feelin' U) Remix",       "Ice Spice"),
        ("Nicki Minaj",      "Princess Diana (Remix)",        "Ice Spice"),
        ("Doja Cat",         "Dangerous Woman (Remix)",       "Ariana Grande"),
        ("GloRilla",         "FNF (Let's Go) Remix",          "Hitkidd"),
        ("Sexyy Red",        "Pound Town (Remix)",            "Sexyy Red"),
        ("Coi Leray",        "No More Parties (Remix)",       "Coi Leray"),
        ("Lil Durk",         "Laugh Now Cry Later (Remix)",   "Drake"),
        ("21 Savage",        "Bank Account (Remix)",          "21 Savage"),
        ("Polo G",           "Pop Out (Remix)",               "Polo G"),
        ("Jack Harlow",      "Way Out (Remix)",               "Jack Harlow"),
        ("Flo Milli",        "Eat It Up (Remix)",             "Flo Milli"),
        ("Armani White",     "BILLIE EILISH. (Remix)",        "Armani White"),
        ("Doechii",          "What It Is (Remix)",            "Doechii"),
        ("Victoria Monet",   "On My Mama (Remix)",            "Victoria Monet"),
        ("Tyla",             "Water (Remix)",                 "Tyla"),
        ("Kodak Black",      "Tunnel Vision (Remix)",         "Kodak Black"),
        ("A Boogie",         "Look Back At It (Remix)",       "A Boogie Wit Da Hoodie"),
        ("NBA YoungBoy",     "Outside Today (Remix)",         "NBA YoungBoy"),
    ]

    leads = []
    for guest, track, main in pairs:
        leads.append({
            "artist": guest,
            "track": track,
            "isrc": "",
            "main_artist": main,
            "source": "remix_collector",
            "chart": "known-remix-pairs",
        })
    return leads


def pull_remix_leads(limit_per_artist: int = 20) -> list:
    """
    Main entry point. Returns remix leads sorted by source priority.
    """
    all_leads = []
    seen = set()

    # 1. Known high-value pairs (instant, no network)
    known = search_known_remix_pairs()
    for lead in known:
        key = f"{lead['artist'].lower()}|{lead['track'].lower()}"
        if key not in seen:
            seen.add(key)
            all_leads.append(lead)
    print(f"[REMIX] Known pairs: {len(all_leads)}")

    # 2. MusicBrainz remix search for each seed artist
    for artist in SEED_ARTISTS:
        print(f"[REMIX] MusicBrainz remix search: {artist}")
        mb_leads = search_remixes_for_artist(artist, limit=limit_per_artist)
        added = 0
        for lead in mb_leads:
            key = f"{lead['artist'].lower()}|{lead['track'].lower()}"
            if key not in seen:
                seen.add(key)
                all_leads.append(lead)
                added += 1
        print(f"  → {added} new remix leads")
        time.sleep(1.1)  # MusicBrainz rate limit: 1 req/sec

    print(f"[REMIX] Total remix leads: {len(all_leads)}")
    return all_leads


if __name__ == "__main__":
    leads = pull_remix_leads()
    print(f"\nSample:")
    for l in leads[:10]:
        print(f"  {l['artist']} — {l['track']} (via {l['main_artist']})")
