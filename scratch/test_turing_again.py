import asyncio
from playwright.async_api import async_playwright
import re

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.turing.com/jobs", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        # let's look for jobs in json data maybe
        content = await page.content()
        with open("turing_jobs_page.html", "w") as f:
            f.write(content)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
