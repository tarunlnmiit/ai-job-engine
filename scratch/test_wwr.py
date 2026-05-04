import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        stealth_async = None
        
    async with async_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "data", "browser_session")
        os.makedirs(user_data_dir, exist_ok=True)
        
        browser_context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
        
        if stealth_async:
            await stealth_async(page)
            
        url = "https://weworkremotely.com/remote-jobs/search?term=python"
        
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        content = await page.content()
        if "Just a moment..." in await page.title() or "cloudflare" in content.lower():
            try:
                await page.wait_for_function(
                    "() => !document.title.includes('Just a moment') && !document.body.innerText.toLowerCase().includes('cloudflare')",
                    timeout=30000
                )
            except:
                pass
                
        # Find the job list container and dump outerHTML of first li
        li_elem = await page.query_selector("article ul li")
        if li_elem:
            html = await li_elem.evaluate("el => el.outerHTML")
            print("First item HTML:\n", html)
        else:
            print("No li found in article ul")

        await browser_context.close()

if __name__ == "__main__":
    asyncio.run(main())
