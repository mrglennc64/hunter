"""
Hunter.io Email Finder
Finds the direct email for an artist's manager or label A&R.
This is the "Buyer" contact — who you send the unclaimed lead to.

Free tier: 25 searches/month at hunter.io
Paid tiers start at $49/mo for 500 searches.

How to use:
  1. Sign up free at https://hunter.io
  2. Get your API key from https://hunter.io/api-keys
  3. Add HUNTER_API_KEY to your .env file

Workflow:
  - You have an unclaimed ISRC for "BossMan Dlow - Mr Pot Scraper"
  - You know the label is "Geffen Records"
  - You put "geffenrecords.com" into Hunter → get the A&R email
  - Or you search for "bossmandlow.com" / manager's site → get direct contact
"""

import time
import requests
import os
import csv
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HUNTER_API_BASE = "https://api.hunter.io/v2"
OUTREACH_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CONTACTS_FILE = os.path.join(OUTREACH_DIR, "contacts.csv")

CONTACTS_COLUMNS = [
    "artist", "track", "isrc", "status",
    "label", "domain_searched", "contact_name",
    "contact_email", "contact_role", "confidence",
    "found_at",
]


def get_api_key() -> str | None:
    key = os.getenv("HUNTER_API_KEY")
    if not key:
        print("[HUNTER] No HUNTER_API_KEY in .env — skipping email lookup.")
    return key


def domain_search(domain: str, api_key: str) -> list:
    """
    Search all emails associated with a domain.
    Returns list of {name, email, role, confidence} dicts.
    """
    try:
        res = requests.get(
            f"{HUNTER_API_BASE}/domain-search",
            params={
                "domain": domain,
                "api_key": api_key,
                "type": "personal",  # personal emails, not generic info@
                "limit": 5,
            },
            timeout=10,
        )
        data = res.json()
        emails = data.get("data", {}).get("emails", [])
        return [
            {
                "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                "email": e.get("value"),
                "role": e.get("position", ""),
                "confidence": e.get("confidence", 0),
            }
            for e in emails
        ]
    except Exception as e:
        print(f"  [HUNTER ERROR] domain={domain}: {e}")
        return []


def find_email(first_name: str, last_name: str, domain: str, api_key: str) -> dict | None:
    """
    Find a specific person's email (e.g. known manager name + label domain).
    """
    try:
        res = requests.get(
            f"{HUNTER_API_BASE}/email-finder",
            params={
                "first_name": first_name,
                "last_name": last_name,
                "domain": domain,
                "api_key": api_key,
            },
            timeout=10,
        )
        data = res.json().get("data", {})
        if data.get("email"):
            return {
                "email": data["email"],
                "confidence": data.get("score", 0),
                "role": data.get("position", ""),
            }
    except Exception as e:
        print(f"  [HUNTER FIND ERROR] {first_name} {last_name} @ {domain}: {e}")
    return None


def guess_domain(label: str) -> str | None:
    """
    Convert a label name to a likely domain.
    E.g. "Geffen Records" → "geffenrecords.com"
         "Quality Control" → "qualitycontrolmusic.com"
    """
    if not label or label.lower() in ("unknown", "independent", "indie", "none", ""):
        return None

    # Strip common suffixes
    clean = label.lower()
    for suffix in [" records", " music", " entertainment", " group", " media", " label"]:
        clean = clean.replace(suffix, "")

    # Remove spaces and special chars
    clean = "".join(c for c in clean if c.isalnum())
    return f"{clean}.com"


def save_contact(row: dict):
    file_exists = os.path.exists(CONTACTS_FILE)
    with open(CONTACTS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CONTACTS_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def find_buyers_for_leads(leads: list) -> list:
    """
    Takes the unclaimed/conflict leads from leads.csv and finds buyer contacts.
    Only processes UNCLAIMED and CONFLICT rows — no point contacting for claimed tracks.
    """
    api_key = get_api_key()
    if not api_key:
        return leads

    enriched = []
    searched_domains = set()  # avoid burning free tier on duplicate domains

    # Only work on actionable leads
    actionable = [l for l in leads if l.get("status") in ("UNCLAIMED", "CONFLICT")]
    print(f"[HUNTER] {len(actionable)} actionable leads to find buyers for.")

    for lead in actionable:
        artist = lead.get("artist", "")
        label = lead.get("label", "")
        domain = guess_domain(label)

        if not domain or domain in searched_domains:
            enriched.append({**lead, "domain_searched": domain or "", "contact_email": ""})
            continue

        searched_domains.add(domain)
        print(f"[HUNTER] Searching {domain} for {artist} (label: {label})...")

        contacts = domain_search(domain, api_key)

        if contacts:
            # Take the highest confidence contact
            best = max(contacts, key=lambda x: x["confidence"])
            print(f"  [FOUND] {best['name']} <{best['email']}> ({best['role']}, {best['confidence']}% confidence)")

            row = {
                **lead,
                "domain_searched": domain,
                "contact_name": best["name"],
                "contact_email": best["email"],
                "contact_role": best["role"],
                "confidence": best["confidence"],
                "found_at": datetime.utcnow().isoformat(),
            }
            save_contact(row)
            enriched.append(row)
        else:
            print(f"  [MISS] No contacts found at {domain}")
            enriched.append({**lead, "domain_searched": domain, "contact_email": ""})

        time.sleep(1)  # Hunter.io rate limit

    print(f"[HUNTER] Done. Contacts saved to {CONTACTS_FILE}")
    return enriched


if __name__ == "__main__":
    # Test with a sample lead
    sample_leads = [
        {
            "artist": "BossMan Dlow",
            "track": "Mr Pot Scraper",
            "isrc": "USUG12400789",
            "status": "UNCLAIMED",
            "label": "Geffen Records",
        }
    ]
    find_buyers_for_leads(sample_leads)
