"""
Artist Contact Finder
For each catalog lead, finds the artist's direct business email from:
  1. Official website (scraped from Google)
  2. Instagram bio email
  3. Hunter.io domain search on artist's official domain

Output added to catalog:
  artist_email, artist_email_source, artist_website
"""

import re
import time
import json
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

HUNTER_KEY = os.getenv("HUNTER_API_KEY", "")
DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOG    = os.path.join(DATA_DIR, "unlock_catalog.json")
BASE_URL   = "https://traproyalties.com"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Skip generic/useless emails
SKIP_DOMAINS = [
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "me.com", "aol.com", "example.com",
    "sentry.io", "wixpress.com", "squarespace.com",
]


def clean_artist_name(artist: str) -> str:
    """Strip featuring/collab suffixes for cleaner searches."""
    artist = re.sub(r'[Ff]eaturing.*', '', artist)
    artist = re.sub(r'\bft\..*', '', artist)
    artist = re.sub(r'&.*', '', artist)
    artist = re.sub(r'\(.*?\)', '', artist)
    return artist.strip()


def is_valid_email(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    return domain not in SKIP_DOMAINS and len(email) < 80


def google_find_website(artist: str) -> str:
    """Search Google for artist's official website."""
    query = f'"{artist}" official site music contact'
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num=5"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            m = re.search(r"https?://(?!www\.google)[^\s&\"']+", href)
            if m:
                site = m.group(0)
                # Skip social media and music platforms
                skip = ["instagram", "twitter", "facebook", "spotify", "apple",
                        "youtube", "tiktok", "soundcloud", "billboard", "genius",
                        "wikipedia", "amazon", "google"]
                if not any(s in site.lower() for s in skip):
                    return site
    except Exception:
        pass
    return ""


def scrape_emails_from_url(url: str) -> list:
    """Scrape all emails from a webpage."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        text = res.text
        emails = EMAIL_RE.findall(text)
        return [e for e in set(emails) if is_valid_email(e)]
    except Exception:
        return []


def hunter_domain_email(domain: str) -> str:
    """Use Hunter.io to find any email at a domain."""
    if not HUNTER_KEY:
        return ""
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "api_key": HUNTER_KEY, "limit": 5}
    try:
        res = requests.get(url, params=params, timeout=10)
        emails = res.json().get("data", {}).get("emails", [])
        # Prefer info@, booking@, contact@, management@
        priority = ["info", "booking", "contact", "management", "press", "team"]
        for p in priority:
            for e in emails:
                if e["value"].startswith(p):
                    return e["value"]
        if emails:
            return emails[0]["value"]
    except Exception:
        pass
    return ""


def find_artist_contact(artist: str) -> dict:
    """
    Find direct contact email for an artist.
    Returns dict with email, source, website.
    """
    result = {"artist_email": "", "artist_email_source": "", "artist_website": ""}
    artist_clean = clean_artist_name(artist)

    # 1. Find official website via Google
    print(f"  [GOOGLE] Finding website for {artist_clean}...")
    website = google_find_website(artist_clean)
    time.sleep(2)

    if website:
        result["artist_website"] = website
        domain = re.sub(r"https?://", "", website).split("/")[0]
        print(f"  [SITE] {website}")

        # 2. Scrape emails from website
        emails = scrape_emails_from_url(website)
        if not emails:
            # Try /contact page
            emails = scrape_emails_from_url(website.rstrip("/") + "/contact")
        if emails:
            result["artist_email"] = emails[0]
            result["artist_email_source"] = "website_scrape"
            print(f"  [EMAIL] {emails[0]} (scraped)")
            return result

        time.sleep(1)

        # 3. Hunter.io domain search
        email = hunter_domain_email(domain)
        if email:
            result["artist_email"] = email
            result["artist_email_source"] = "hunter_domain"
            print(f"  [EMAIL] {email} (Hunter.io)")
            return result

    # 4. Fallback: Hunter.io on guessed domain
    domain_guess = artist_clean.lower().replace(" ", "").replace(".", "") + ".com"
    email = hunter_domain_email(domain_guess)
    if email:
        result["artist_email"] = email
        result["artist_email_source"] = "hunter_guessed_domain"
        result["artist_website"] = f"https://{domain_guess}"
        print(f"  [EMAIL] {email} (guessed domain)")

    if not result["artist_email"]:
        print(f"  — No direct email found")

    return result


def enrich_catalog_artist_contacts() -> int:
    """Find direct artist contacts for all catalog leads."""
    with open(CATALOG) as f:
        catalog = json.load(f)

    # Deduplicate by artist
    seen_artists = set()
    updated = 0

    for aid, lead in catalog.items():
        artist = lead.get("artist", "")
        artist_key = clean_artist_name(artist).lower()

        # Skip if already has direct contact
        if lead.get("artist_email"):
            seen_artists.add(artist_key)
            continue

        # Skip duplicates
        if artist_key in seen_artists:
            # Copy from another lead with same artist if available
            for other_lead in catalog.values():
                if clean_artist_name(other_lead.get("artist","")).lower() == artist_key \
                        and other_lead.get("artist_email"):
                    lead["artist_email"] = other_lead["artist_email"]
                    lead["artist_email_source"] = other_lead["artist_email_source"]
                    lead["artist_website"] = other_lead.get("artist_website", "")
                    break
            continue

        seen_artists.add(artist_key)
        print(f"\n[CONTACT] {artist}")
        contact = find_artist_contact(artist)

        lead["artist_email"]        = contact["artist_email"]
        lead["artist_email_source"] = contact["artist_email_source"]
        lead["artist_website"]      = contact["artist_website"]

        if contact["artist_email"]:
            updated += 1

        time.sleep(2)

    with open(CATALOG, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"\n[CONTACT] {updated} artists found with direct email")
    return updated


def print_artist_outreach_list():
    """Print ready-to-send outreach list with artist direct emails."""
    with open(CATALOG) as f:
        catalog = json.load(f)

    contacts = [(aid, l) for aid, l in catalog.items() if l.get("artist_email")]
    print(f"\n{'='*70}")
    print(f"  ARTIST DIRECT OUTREACH — {len(contacts)} contacts")
    print(f"{'='*70}")

    seen = set()
    for aid, lead in contacts:
        email = lead["artist_email"]
        if email in seen:
            continue
        seen.add(email)
        print(f"\n  {lead['artist']} — {lead['track']}")
        print(f"  Direct email: {email} ({lead.get('artist_email_source','')})")
        print(f"  Lawyer page:  {BASE_URL}/lawyer/{aid}")
        print(f"  Est. Recovery: {lead.get('bounty_low','?')} – {lead.get('bounty_high','?')}")


if __name__ == "__main__":
    print("[CONTACT] Finding direct artist contact emails...")
    enrich_catalog_artist_contacts()
    print_artist_outreach_list()
