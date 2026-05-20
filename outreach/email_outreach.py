"""
Email Outreach — TrapRoyalties
For each catalog lead with attorney/manager data:
  1. Use Hunter.io to find attorney email by name + firm
  2. Save email to catalog
  3. Print outreach list ready to send

Usage:
    python3 outreach/email_outreach.py           # find emails only
    python3 outreach/email_outreach.py --send    # find + send emails (requires SMTP config)
"""

import os, sys, json, time, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

HUNTER_KEY  = os.getenv("HUNTER_API_KEY", "")
DATA_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOG     = os.path.join(DATA_DIR, "unlock_catalog.json")
BASE_URL    = "https://traproyalties.com"

# Known firm → domain mappings (Hunter.io needs domain, not firm name)
FIRM_DOMAINS = {
    "manatt phelps": "manatt.com",
    "myman greenspan": "mymanlaw.com",
    "jackoway austen": "jatlaw.com",
    "king holmes": "khps.com",
    "carter woodard": "carterwoodard.com",
    "carroll guido": "cgclaw.com",
    "king ballow": "kingballow.com",
    "hirschfeld kraemer": "hklaw.com",
    "northstar group": "thenorthstargroup.net",
    "weinberger law": "weinbergerlaw.com",
    "barnes thornburg": "btlaw.com",
    "ziffren brittenham": "ziffrenlaw.com",
    "sadow": "sadowandfroy.com",
    "gang tyre": "gangtyre.com",
    "roc nation": "rocnation.com",
    "full stop management": "fullstopmanagement.com",
    "xo records": "xorecords.com",
    "sb projects": "sb-projects.com",
    "top dawg": "topdawgentertainment.com",
    "pgLang": "pglang.com",
    "88rising": "88rising.com",
    "s10 entertainment": "s10ent.com",
    "salxco": "salxco.com",
    "cactus jack": "cactusjackrecords.com",
    "quality control": "qualitycontrolmusic.com",
    "october's very own": "october'sveryown.com",
    "blueprint group": "blueprintgroup.com",
    "parkwood": "parkwoodentertainment.com",
    "tap music": "tapmusic.net",
    "rimas entertainment": "rimasentertainment.com",
    "private garden": "privatgarden.com",
    "creed entertainment": "creedentertainment.com",
    "only the family": "otfrecords.com",
    "freebandz": "freebandz.com",
    "starboy": "starboyentertainment.com",
    "hypnotize minds": "hypnotizemindz.com",
    "universal music latin": "umusic.com",

    # ── Atlanta firms ──────────────────────────────────────────────────────────
    "sadow": "sadowandfroy.com",
    "sadow & froy": "sadowandfroy.com",
    "findling": "findlinglaw.com",
    "the findling law firm": "findlinglaw.com",
    "steel law": "thesteellawfirm.com",
    "the steel law firm": "thesteellawfirm.com",
    "granderson des rochers": "gdrfirm.com",
    "ward law": "wardlawgroup.com",
    "ward law group": "wardlawgroup.com",
    "ewing law": "ewinglaw.com",
    "quality control": "qualitycontrolmusic.com",
    "paper route empire": "paperrouteempire.com",
    "ysl records": "yslrecords.com",
    "eardrummers": "eardrummers.com",
    "empire distribution": "empire.com",
    "grand hustle": "grandhustle.com",
    "street execs": "streetexecs.com",
    "lvrn": "lvrn.com",
    "dreamville": "dreamvillerecords.com",
    "300 entertainment": "300ent.com",
    "mizay entertainment": "mizayentertainment.com",
}

# Verified emails (manually confirmed — do not overwrite with Hunter guesses)
VERIFIED_EMAILS = {
    "Eric Greenspan":    "egreenspan@mymangreenspan.com",
    "Damien Granderson": "damien@gdrfirm.com",
    "Dave Free":         "dave@pg-lang.com",
    "Londell McMillan":  "llm@thenorthstargroup.biz",
    "info@freebandz":    "info@freebandz.com",
}


def get_firm_domain(firm_name: str) -> str:
    """Map firm name to domain for Hunter.io lookup."""
    firm_lower = firm_name.lower()
    for key, domain in FIRM_DOMAINS.items():
        if key in firm_lower:
            return domain
    # Fallback: try to guess domain from firm name
    # e.g. "Smith Law Group" -> "smithlawgroup.com"
    clean = firm_lower.replace(" llp", "").replace(" llc", "").replace(" pc", "")
    clean = clean.replace(" ", "").replace("&", "and").replace(",", "")
    return f"{clean}.com"


def hunter_find_email(first_name: str, last_name: str, domain: str) -> dict:
    """Use Hunter.io email finder API."""
    if not HUNTER_KEY:
        return {"error": "No HUNTER_API_KEY set"}

    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain":      domain,
        "first_name":  first_name,
        "last_name":   last_name,
        "api_key":     HUNTER_KEY,
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if data.get("data", {}).get("email"):
            return {
                "email":      data["data"]["email"],
                "confidence": data["data"].get("score", 0),
                "source":     "hunter_finder",
            }
        return {"error": "not found"}
    except Exception as e:
        return {"error": str(e)}


def hunter_domain_search(domain: str, name: str) -> dict:
    """Search all emails at a domain, then filter by name."""
    if not HUNTER_KEY:
        return {"error": "No HUNTER_API_KEY set"}

    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain":  domain,
        "api_key": HUNTER_KEY,
        "limit":   10,
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        emails = data.get("data", {}).get("emails", [])
        name_lower = name.lower()
        for e in emails:
            full = f"{e.get('first_name','')} {e.get('last_name','')}".lower()
            if any(part in full for part in name_lower.split()):
                return {
                    "email":      e["value"],
                    "confidence": e.get("confidence", 0),
                    "source":     "hunter_domain",
                }
        return {"error": "name not found in domain"}
    except Exception as e:
        return {"error": str(e)}


def find_email_for_rep(name: str, firm: str) -> str:
    """Check verified list first, then Hunter finder, then domain search."""
    # Check verified emails — no API call needed
    if name in VERIFIED_EMAILS:
        email = VERIFIED_EMAILS[name]
        print(f"    [VERIFIED] {email}")
        return email

    parts = name.strip().split()
    if len(parts) < 2:
        return ""

    first, last = parts[0], parts[-1]
    domain = get_firm_domain(firm)

    # Try email finder first
    result = hunter_find_email(first, last, domain)
    if result.get("email"):
        print(f"    [HUNTER] {result['email']} (confidence: {result['confidence']}%)")
        return result["email"]

    time.sleep(1)

    # Fallback: domain search
    result = hunter_domain_search(domain, name)
    if result.get("email"):
        print(f"    [HUNTER] {result['email']} via domain search")
        return result["email"]

    print(f"    [HUNTER] No email found for {name} @ {domain}")
    return ""


def enrich_emails(catalog: dict) -> int:
    """Find emails for all leads that have attorney/manager but no email yet."""
    updated = 0
    for aid, lead in catalog.items():
        atty_name = lead.get("attorney_name", "")
        atty_firm = lead.get("attorney_firm", "")
        mgr_name  = lead.get("manager_name", "")
        mgr_firm  = lead.get("manager_firm", "")

        changed = False

        if atty_name and atty_firm and not lead.get("attorney_email"):
            print(f"  [EMAIL] {lead['artist']} → attorney: {atty_name} @ {atty_firm}")
            email = find_email_for_rep(atty_name, atty_firm)
            if email:
                lead["attorney_email"] = email
                changed = True
            time.sleep(1.5)

        if mgr_name and mgr_firm and not lead.get("manager_email"):
            print(f"  [EMAIL] {lead['artist']} → manager: {mgr_name} @ {mgr_firm}")
            email = find_email_for_rep(mgr_name, mgr_firm)
            if email:
                lead["manager_email"] = email
                changed = True
            time.sleep(1.5)

        if changed:
            updated += 1

    return updated


def print_outreach_list(catalog: dict):
    """Print all leads ready to contact."""
    print(f"\n{'='*70}")
    print(f"  OUTREACH LIST — {sum(1 for l in catalog.values() if l.get('attorney_email') or l.get('manager_email'))} contacts found")
    print(f"{'='*70}")
    for aid, lead in catalog.items():
        atty_email = lead.get("attorney_email", "")
        mgr_email  = lead.get("manager_email", "")
        if not atty_email and not mgr_email:
            continue
        print(f"\n  {lead['artist']} — {lead['track']}")
        print(f"  Lawyer page: {BASE_URL}/lawyer/{aid}")
        if atty_email:
            print(f"  Attorney: {lead.get('attorney_name')} <{atty_email}>")
        if mgr_email:
            print(f"  Manager:  {lead.get('manager_name')} <{mgr_email}>")
        print(f"  Est. Recovery: {lead.get('bounty_low')} – {lead.get('bounty_high')}")


if __name__ == "__main__":
    if not HUNTER_KEY:
        print("[ERROR] Set HUNTER_API_KEY in .env")
        sys.exit(1)

    with open(CATALOG) as f:
        catalog = json.load(f)

    leads_with_reps = sum(1 for l in catalog.values() if l.get("attorney_firm") or l.get("manager_firm"))
    print(f"[OUTREACH] {len(catalog)} leads | {leads_with_reps} have rep data")
    print(f"[OUTREACH] Finding emails via Hunter.io...")

    updated = enrich_emails(catalog)

    with open(CATALOG, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"\n[OUTREACH] {updated} leads enriched with emails")
    print_outreach_list(catalog)
