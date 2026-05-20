"""
Session Manager
- Rotates proxies and user agents
- Manages browser lifecycle (new context every N searches)
- Enforces human-like delays between requests
"""

import random
import time
import os
from dotenv import load_dotenv

load_dotenv()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
    {"width": 2560, "height": 1440},
]

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "America/Atlanta",
    "America/Detroit",
]


def load_proxies() -> list:
    """Load proxy list from env or proxies.txt file."""
    # Option 1: Comma-separated proxies in .env
    env_proxies = os.getenv("PROXIES", "")
    if env_proxies:
        return [p.strip() for p in env_proxies.split(",") if p.strip()]

    # Option 2: proxies.txt file (one per line)
    proxy_file = os.path.join(os.path.dirname(__file__), "..", "proxies.txt")
    if os.path.exists(proxy_file):
        with open(proxy_file) as f:
            return [line.strip() for line in f if line.strip()]

    # No proxies configured — run without (not recommended for large runs)
    print("[WARN] No proxies configured. Running without IP rotation.")
    return []


def get_proxy_config() -> dict | None:
    proxies = load_proxies()
    if not proxies:
        return None
    proxy = random.choice(proxies)
    return {"server": proxy}


def human_delay(min_sec=8, max_sec=25):
    """Main delay between searches — mimics human reading/thinking time."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def reading_delay():
    """Short pause after results load — simulates reading the page."""
    time.sleep(random.uniform(2, 5))


def typing_delay():
    """Per-character delay when filling input fields."""
    return random.uniform(0.05, 0.18)


def new_browser_context(playwright, rotate_proxy=True):
    """
    Create a fresh browser + context with randomized fingerprint.
    Call this every 10-15 searches to rotate session.
    """
    proxy = get_proxy_config() if rotate_proxy else None

    launch_args = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
        ],
    }
    if proxy:
        launch_args["proxy"] = proxy

    browser = playwright.chromium.launch(**launch_args)

    context = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport=random.choice(VIEWPORTS),
        locale="en-US",
        timezone_id=random.choice(TIMEZONES),
        java_script_enabled=True,
        # Mask webdriver flag
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    # Remove automation fingerprint
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)

    return browser, context


def should_rotate_session(search_count: int) -> bool:
    """Rotate browser session every 10-15 searches."""
    return search_count % random.randint(10, 15) == 0
