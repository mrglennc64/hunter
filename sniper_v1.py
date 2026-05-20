import asyncio
import random
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def sniper_hunt(isrc_list):
    # 1. Load your ammo
    with open('proxies.txt', 'r') as f:
        proxy_pool = f.read().splitlines()

    async with async_playwright() as p:
        for isrc in isrc_list:
            # 2. Pick a fresh identity for this search
            p_raw = random.choice(proxy_pool).split(':')
            current_proxy = {
                "server": f"http://{p_raw[0]}:{p_raw[1]}",
                "username": p_raw[2],
                "password": p_raw[3]
            }
            
            print(f"📡 Sniping {isrc} via {p_raw[0]} (US Resident Identity)")
            
            browser = await p.chromium.launch(headless=True, proxy=current_proxy)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = await context.new_page()
            await stealth_async(page)

            # 3. Hit the Registry
            try:
                await page.goto("https://isrc.soundexchange.com/#!/search", timeout=60000)
                await page.fill('input[name="isrc"]', isrc)
                await page.keyboard.press("Enter")
                await asyncio.sleep(5) # Give it time to load results

                if "No results found" in await page.content():
                    print(f"💰 [UNCLAIMED] Jackpot found for ISRC: {isrc}")
                    with open('bounty_leads.csv', 'a') as f:
                        f.write(f"{isrc},UNCLAIMED\n")
            except Exception as e:
                print(f"❌ Missed shot on {isrc}: {e}")
            
            await browser.close()
            await asyncio.sleep(random.uniform(10, 20)) # Cool down the barrel

# To run: asyncio.run(sniper_hunt(["ISRC1", "ISRC2"]))