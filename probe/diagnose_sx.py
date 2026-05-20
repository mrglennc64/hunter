"""
Diagnostic v3 — finds buttons, waits for results element, dumps full DOM.
"""

import asyncio
from playwright.async_api import async_playwright

SX_URL = "https://isrc.soundexchange.com/#!/search"


async def diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("[DIAG] Loading page...")
        await page.goto(SX_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(4)

        # Dismiss cookie dialog
        try:
            btn = page.locator("button:has-text('Accept'), button:has-text('Allow'), button:has-text('Save')")
            if await btn.count() > 0:
                await btn.first.click()
                print("[DIAG] Cookie dismissed")
                await asyncio.sleep(2)
        except Exception:
            pass

        # Screenshot before search
        await page.screenshot(path="/root/hunter/data/sx_before.png")
        print("[DIAG] Before-search screenshot saved")

        # List ALL buttons on the page
        buttons = await page.query_selector_all("button")
        print(f"\n[DIAG] Found {len(buttons)} buttons:")
        for i, b in enumerate(buttons):
            txt = await b.inner_text()
            cls = await b.get_attribute("class")
            print(f"  [{i}] text='{txt.strip()}' | class={cls}")

        # Fill search fields
        await page.fill("#search-artist-name-input", "Doechii")
        await asyncio.sleep(0.8)
        await page.fill("#search-recording-title-input", "Anxiety")
        await asyncio.sleep(0.8)

        # Screenshot after filling
        await page.screenshot(path="/root/hunter/data/sx_filled.png")
        print("\n[DIAG] Filled-form screenshot saved")

        # Try pressing Enter on the field
        await page.focus("#search-recording-title-input")
        await page.keyboard.press("Enter")
        print("[DIAG] Pressed Enter")

        # Wait longer for Angular to render results
        await asyncio.sleep(12)

        # Screenshot after search
        await page.screenshot(path="/root/hunter/data/sx_results.png")
        print("[DIAG] Results screenshot saved")

        # Dump full body text
        body_text = await page.inner_text("body")
        print("\n[DIAG] === PAGE TEXT ===")
        print(body_text[:5000])
        print("[DIAG] === END ===")

        # Also dump raw HTML snippet around results area
        html = await page.content()
        # Find where results might be
        for keyword in ["result", "claim", "performer", "isrc", "recording"]:
            idx = html.lower().find(keyword)
            if idx != -1:
                print(f"\n[DIAG] Found '{keyword}' in HTML at pos {idx}:")
                print(html[max(0,idx-100):idx+300])
                break

        await browser.close()


asyncio.run(diagnose())
