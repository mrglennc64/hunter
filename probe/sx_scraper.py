"""
SoundExchange Async Stealth Scraper
- Async Playwright for speed
- playwright-stealth to mask headless fingerprint
- Proxy rotation via Webshare (or proxies.txt)
- Session rotation every 10 searches
- Human-like random delays
- Saves leads to data/leads.csv in real time
- Resumes from last ISRC if interrupted
"""

import asyncio
import csv
import os
import random
import time
from datetime import datetime

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from dotenv import load_dotenv

load_dotenv()

SX_URL = "https://isrc.soundexchange.com/"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LEADS_FILE = os.path.join(DATA_DIR, "leads.csv")
PROGRESS_FILE = os.path.join(DATA_DIR, "progress.txt")

LEADS_COLUMNS = [
    "artist", "track", "isrc", "status", "sx_result",
    "sniper_score", "label", "probed_at", "note",
]

UNREGISTERED_SIGNALS = ["0 recording results", "no results", "no recordings found"]


# ── SoundExchange page parser ─────────────────────────────────────────────────

def extract_featured_from_sx_body(body: str) -> list[str]:
    """
    Parse featured artist names from SoundExchange result page text.
    Catches patterns like 'SZA feat. Justin Bieber', 'Drake ft. SZA & Sexyy Red'.
    Returns list of featured artist name strings.
    """
    featured = []
    # Find all feat/ft/featuring patterns in the page text
    matches = re.findall(
        r'(?:[Ff]eaturing|[Ff]eat\.|[Ff]t\.)\s+([A-Za-z0-9 &,\'\.\-]+?)(?:\n|  |\d{4}|$)',
        body
    )
    for m in matches:
        # Split on & and , to get individual names
        for name in re.split(r'[,&]', m):
            name = name.strip().rstrip('.,')
            if name and len(name) > 2:
                featured.append(name)
    return list(set(featured))


# ── Featured artist parser ────────────────────────────────────────────────────

import re

def parse_featured_artists(artist_field: str) -> tuple[str, list[str]]:
    """
    Splits 'Post MaloneFeaturingMorgan Wallen' into:
      primary = 'Post Malone'
      featured = ['Morgan Wallen']

    Handles: Featuring, feat., ft., With, &, ,
    Returns (primary, [featured, ...])
    """
    # Split on Featuring / feat. / ft. / With (case-insensitive)
    split = re.split(r'[Ff]eaturing|[Ff]eat\.|[Ff]t\.|[Ww]ith(?=\s)', artist_field, maxsplit=1)

    primary = split[0].strip().rstrip(',& ')

    if len(split) == 1:
        # No featuring — check for & or , separating co-primary artists
        parts = re.split(r'[,&]', artist_field)
        if len(parts) > 1:
            primary = parts[0].strip()
            featured = [p.strip() for p in parts[1:] if p.strip()]
        else:
            featured = []
    else:
        # Split remaining on & and ,
        featured_raw = split[1]
        featured = [p.strip() for p in re.split(r'[,&]', featured_raw) if p.strip()]

    return primary, featured


# ── Proxy helpers ────────────────────────────────────────────────────────────

def load_proxies() -> list:
    env_proxies = os.getenv("PROXIES", "")
    if env_proxies:
        return [p.strip() for p in env_proxies.split(",") if p.strip()]
    proxy_file = os.path.join(os.path.dirname(__file__), "..", "proxies.txt")
    if os.path.exists(proxy_file):
        with open(proxy_file) as f:
            return [line.strip() for line in f if line.strip()]
    return []


def pick_proxy() -> dict | None:
    proxies = load_proxies()
    if not proxies:
        return None
    raw = random.choice(proxies)
    # Format: http://user:pass@host:port
    if "@" in raw:
        host_port = raw.split("@")[-1]
        server = "http://" + host_port if not host_port.startswith("http") else host_port
        return {"server": server,
                "username": raw.split("//")[1].split(":")[0],
                "password": raw.split(":")[2].split("@")[0]}
    return {"server": raw}


# ── Progress tracking ────────────────────────────────────────────────────────

def load_progress() -> set:
    if not os.path.exists(PROGRESS_FILE):
        return set()
    with open(PROGRESS_FILE) as f:
        return set(line.strip() for line in f if line.strip())


def save_progress(isrc):
    with open(PROGRESS_FILE, "a") as f:
        f.write(str(isrc) + "\n")


def save_lead(row: dict):
    file_exists = os.path.exists(LEADS_FILE)
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LEADS_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ── Browser factory ──────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


async def new_stealth_page(playwright, proxy: dict | None):
    """Launch a fresh stealth browser context."""
    launch_kwargs = {
        "headless": True,  # Always headless on VPS (no display)
        "executable_path": "/usr/bin/chromium-browser",
        "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    }
    if proxy:
        launch_kwargs["proxy"] = proxy

    browser = await playwright.chromium.launch(**launch_kwargs)

    context = await browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": random.randint(1280, 1920), "height": random.randint(768, 1080)},
        locale="en-US",
        timezone_id=random.choice(["America/New_York", "America/Chicago", "America/Los_Angeles"]),
    )

    page = await context.new_page()

    # Apply stealth patches (removes headless fingerprint tells)
    stealth = Stealth()
    await stealth.apply_stealth_async(page)

    return browser, page


# ── Core probe logic ─────────────────────────────────────────────────────────

async def dismiss_cookie_dialog(page):
    """Dismiss Osano cookie consent if it appears."""
    try:
        accept = page.locator("button:has-text('Accept'), button:has-text('Allow'), button:has-text('Agree')")
        if await accept.count() > 0:
            await accept.first.click()
            await asyncio.sleep(1)
    except Exception:
        pass


async def name_search_registered(page, artist: str, track: str) -> bool:
    """
    Confirm registration via name+title search.
    Returns True if track IS registered (found by name), False if truly unregistered.
    Used as double-check when ISRC lookup shows 0 results — remixes often have
    different ISRCs in our DB vs SoundExchange, causing false JACKPOT flags.
    """
    # Strip feat./remix suffixes for a cleaner title search
    clean_track = re.sub(r'\s*[\(\[].*', '', track).strip()
    # Use primary artist only
    primary_artist = re.split(r'[Ff]eaturing|[Ff]eat\.|[Ff]t\.|,|&', artist)[0].strip()

    try:
        await page.goto(SX_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(random.uniform(2.5, 4.0))
        await dismiss_cookie_dialog(page)
        await asyncio.sleep(1)

        await page.click("button:has-text('SEARCH')")
        await asyncio.sleep(random.uniform(1.5, 2.5))

        await page.fill("#search-artist-name-input", primary_artist)
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await page.fill("#search-recording-title-input", clean_track)
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await page.keyboard.press("Enter")
        await asyncio.sleep(random.uniform(8, 12))

        body = (await page.inner_text("body")).lower()

        if any(s in body for s in UNREGISTERED_SIGNALS):
            return False  # truly not registered
        elif "recording results" in body:
            return True   # registered under a different ISRC
        return True       # inconclusive — assume registered (avoid false positives)

    except Exception:
        return True  # on error, assume registered (safe default)


async def probe_one(page, target: dict) -> dict:
    """Search SoundExchange by ISRC. Unregistered = JACKPOT.
    ISRC is required — tracks without one are skipped entirely.
    No ISRC = never officially released = not a legitimate claim.
    """
    isrc = str(target.get("isrc") or "").strip()
    artist = target.get("artist", "")
    track = target.get("track", "")

    if not isrc or isrc.lower() in ("nan", "none", ""):
        print(f"  [SKIP] No ISRC — not an official release: {artist} - {track}")
        return {**target, "status": "SKIP", "sx_result": "no isrc — unofficial release", "probed_at": datetime.utcnow().isoformat()}

    try:
        await page.goto(SX_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(random.uniform(2.5, 4.0))

        # Dismiss cookie dialog if present
        await dismiss_cookie_dialog(page)
        await asyncio.sleep(1)

        # Click LOOK UP BY CODE tab
        await page.click("button:has-text('LOOK UP BY CODE')")
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # Fill ISRC directly
        await page.fill("#search-isrc-input", isrc)
        await asyncio.sleep(random.uniform(0.5, 1.2))
        await page.keyboard.press("Enter")

        # Wait for Angular to render results
        await asyncio.sleep(random.uniform(8, 12))

        body = (await page.inner_text("body")).lower()

        sx_featured = []

        if any(s in body for s in UNREGISTERED_SIGNALS):
            # ISRC not in SoundExchange = officially released but not registered.
            # We already enforced ISRC presence above, so this is a real JACKPOT.
            status = "JACKPOT"
            print(f"  [JACKPOT] NOT REGISTERED: {artist} - {track} ({isrc})")
        elif "recording results" in body:
            status = "REGISTERED"
            # Extract any featured artists SoundExchange lists on this recording
            sx_featured = extract_featured_from_sx_body(body)
            if sx_featured:
                print(f"  [SX] Featured artists on SoundExchange: {', '.join(sx_featured)}")
        else:
            status = "UNKNOWN"

        return {
            **target,
            "status": status,
            "sx_result": status.lower(),
            "sx_featured": sx_featured,
            "probed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        print(f"  [ERROR] {artist} - {track}: {e}")
        return {
            **target,
            "status": "ERROR",
            "sx_result": str(e)[:100],
            "probed_at": datetime.utcnow().isoformat(),
        }


async def probe_featured(page, target: dict, guest_artist: str) -> dict | None:
    """
    Search SoundExchange by GUEST ARTIST name + track title.
    If 0 results → guest never claimed their performer share = JACKPOT.
    """
    track = target.get("track", "")
    isrc = target.get("isrc", "")

    try:
        await page.goto(SX_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(random.uniform(2.5, 4.0))
        await dismiss_cookie_dialog(page)
        await asyncio.sleep(1)

        # Use SEARCH tab — search by guest artist name + title
        await page.click("button:has-text('SEARCH')")
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # Clean track title: strip (Remix)/(feat.)... suffixes and apostrophes
        # SoundExchange stores titles differently — "What's Poppin (Remix)" fails
        # but "Whats Poppin" finds the right recording
        clean_track = re.sub(r'\s*[\(\[].*', '', track).strip()
        clean_track = clean_track.replace("\u2019", "").replace("'", "").replace("`", "")

        await page.fill("#search-artist-name-input", guest_artist)
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await page.fill("#search-recording-title-input", clean_track)
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await page.keyboard.press("Enter")
        await asyncio.sleep(random.uniform(8, 12))

        body = (await page.inner_text("body")).lower()

        if any(s in body for s in UNREGISTERED_SIGNALS):
            print(f"  [JACKPOT] GUEST UNCLAIMED: {guest_artist} on '{track}' ({isrc})")
            return {
                **target,
                "artist": guest_artist,
                "status": "GUEST_UNCLAIMED",
                "sx_result": f"guest not found: {guest_artist}",
                "probed_at": datetime.utcnow().isoformat(),
            }
        return None

    except Exception as e:
        print(f"  [ERROR] guest probe {guest_artist}: {e}")
        return None


# ── Main probe runner ────────────────────────────────────────────────────────

async def run_probe_async(targets: list, max_per_session: int = 50):
    """
    Main async probe loop.
    max_per_session=50  → start mode
    max_per_session=100 → daily full mode
    """
    done = load_progress()
    # Enforce ISRC requirement — no ISRC = unofficial release = skip before browser opens
    no_isrc = [t for t in targets if not t.get("isrc") or str(t["isrc"]).strip().lower() in ("nan", "none", "")]
    if no_isrc:
        print(f"[PROBE] Skipping {len(no_isrc)} targets with no ISRC (unofficial releases)")
    remaining = [t for t in targets if t.get("isrc") and str(t["isrc"]).strip().lower() not in ("nan", "none", "") and t["isrc"] not in done]

    print(f"[PROBE] {len(remaining)} targets with ISRC | {len(done)} already done | limit: {max_per_session}")

    unclaimed = 0
    conflicts = 0
    count = 0

    async with async_playwright() as p:
        proxy = pick_proxy()
        browser, page = await new_stealth_page(p, proxy)

        for i, target in enumerate(remaining):
            if count >= max_per_session:
                print(f"[PROBE] Session limit reached ({max_per_session}). Run again tomorrow.")
                break

            # Rotate session every 10 searches
            if count > 0 and count % 10 == 0:
                print(f"[PROBE] Rotating session at search #{count}...")
                await browser.close()
                await asyncio.sleep(random.uniform(5, 12))
                proxy = pick_proxy()
                browser, page = await new_stealth_page(p, proxy)

            print(f"[PROBE] [{count+1}/{len(remaining)}] {target.get('artist')} - {target.get('track')}")

            result = await probe_one(page, target)
            save_lead(result)
            save_progress(target["isrc"])

            if result["status"] == "JACKPOT":
                unclaimed += 1
            elif result["status"] == "REGISTERED":
                # Merge featured artists: from CSV artist field + from SoundExchange page
                _, csv_featured = parse_featured_artists(target.get("artist", ""))
                sx_featured = result.get("sx_featured", [])
                # Combine, deduplicate (case-insensitive), skip primary artist
                primary_artist = re.split(r'[Ff]eaturing|[Ff]eat\.|[Ff]t\.|,|&', target.get("artist", ""))[0].strip().lower()
                seen = {primary_artist}
                all_featured = []
                for name in csv_featured + sx_featured:
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        all_featured.append(name)

                for guest in all_featured:
                    print(f"  [LOD CHECK] Probing performer LOD: {guest} on '{target.get('track')}'")
                    await asyncio.sleep(random.uniform(5, 10))
                    guest_result = await probe_featured(page, target, guest)
                    if guest_result:
                        save_lead(guest_result)
                        unclaimed += 1

            count += 1

            # Human delay: 8-25 seconds between searches
            await asyncio.sleep(random.uniform(8, 25))

        await browser.close()

    print(f"\n[PROBE] Complete — Searched: {count} | Unclaimed: {unclaimed} | Conflicts: {conflicts}")
    print(f"[PROBE] Leads saved to: {LEADS_FILE}")


def run_probe(targets: list, max_per_session: int = 50):
    """Sync entry point — wraps the async runner."""
    asyncio.run(run_probe_async(targets, max_per_session))


if __name__ == "__main__":
    import argparse, csv as _csv
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", help="Path to targets CSV")
    parser.add_argument("--limit", type=int, default=50, help="Max probes per session")
    args = parser.parse_args()

    targets = []
    with open(args.csv_file, newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            artist = (row.get("artist") or row.get("Artist") or "").strip()
            track  = (row.get("track")  or row.get("Track")  or row.get("song") or row.get("Song") or "").strip()
            isrc   = (row.get("isrc")   or row.get("ISRC")   or "").strip()
            if artist and track:
                targets.append({"artist": artist, "track": track, "isrc": isrc})

    print(f"[PROBE] Loaded {len(targets)} targets from {args.csv_file}")
    run_probe(targets, max_per_session=args.limit)
