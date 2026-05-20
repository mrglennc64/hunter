"""
Firecrawl test — SoundExchange ISRC lookup
Tests whether Firecrawl can fetch and parse SoundExchange search results.
Run: python probe/test_firecrawl.py
Requires: pip install firecrawl-py
Get API key: https://firecrawl.dev
"""

import os
import re
from firecrawl import FirecrawlApp

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = os.getenv("FIRECRAWL_API_KEY", "fc-YOUR_KEY_HERE")

TEST_CASES = [
    # (artist, track, isrc, expect_found)
    ("Post Malone", "Rockstar", "USUM71710087", True),   # should find 21 Savage listed
    ("21 Savage",   "Rockstar", "USUM71710087", False),  # LOD gap — should return 0 results
    ("Lil Durk",    "Back in Blood", "USAT22007048", False),  # confirmed NOT ASSIGNED
]

UNREGISTERED_SIGNALS = ["0 recording results", "no results", "no recordings found"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def build_isrc_url(isrc: str) -> str:
    return f"https://isrc.soundexchange.com/?tab=code&isrcCode={isrc}&showReleases=true"

def build_name_url(artist: str, track: str) -> str:
    a = artist.replace(" ", "+")
    t = re.sub(r"['\u2019`]", "", track)   # strip apostrophes
    t = re.sub(r"\s*[\(\[].*", "", t).strip()  # strip (Remix) etc
    t = t.replace(" ", "+")
    return f"https://isrc.soundexchange.com/?tab=simple&artistName={a}&title={t}&showReleases=true"

def scrape(app: FirecrawlApp, url: str) -> str:
    """Fetch URL and return page text."""
    try:
        result = app.scrape_url(url, params={"formats": ["markdown"]})
        return result.get("markdown", "") or ""
    except Exception as e:
        return f"ERROR: {e}"

def check_zero_results(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in UNREGISTERED_SIGNALS)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if "YOUR_KEY" in API_KEY:
        print("[ERROR] Set FIRECRAWL_API_KEY environment variable or paste key above.")
        return

    app = FirecrawlApp(api_key=API_KEY)

    print("=" * 60)
    print("FIRECRAWL × SOUNDEXCHANGE TEST")
    print("=" * 60)

    for artist, track, isrc, expect_found in TEST_CASES:
        print(f"\n[TEST] {artist} — {track} ({isrc})")

        # Step 1: ISRC lookup — should find the recording
        isrc_url = build_isrc_url(isrc)
        isrc_text = scrape(app, isrc_url)
        isrc_found = "1 recording" in isrc_text.lower() or isrc.lower() in isrc_text.lower()
        print(f"  ISRC lookup: {'FOUND' if isrc_found else 'NOT FOUND'}")
        print(f"  URL: {isrc_url}")

        # Step 2: Name search — check for LOD gap
        name_url = build_name_url(artist, track)
        name_text = scrape(app, name_url)
        zero = check_zero_results(name_text)
        print(f"  Name search: {'0 RESULTS (JACKPOT)' if zero else 'RESULTS FOUND'}")
        print(f"  URL: {name_url}")

        # First 300 chars of response for debugging
        preview = name_text[:300].replace("\n", " ").strip()
        print(f"  Preview: {preview}")

    print("\n" + "=" * 60)
    print("If ISRC lookup returns FOUND and name search returns 0 RESULTS")
    print("→ Firecrawl can replace Playwright for LOD gap detection.")
    print("If all results are empty/error → SoundExchange blocks Firecrawl IPs.")
    print("=" * 60)

if __name__ == "__main__":
    main()
