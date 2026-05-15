import asyncio
from playwright.async_api import async_playwright
import re

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.turing.com/jobs", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        print(f"TITLE: {await page.title()}")
        links = await page.query_selector_all("a")
        for link in links:
            href = await link.get_attribute("href")
            text = (await link.inner_text()).strip()
            if href:
                print(f"[{text}] -> {href}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
