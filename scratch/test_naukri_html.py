import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "data", "browser_session")
        os.makedirs(user_data_dir, exist_ok=True)

        cdp_url = "http://localhost:9222"
        owned = False
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            print("Connected via CDP")
        except Exception:
            browser_context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            owned = True
            page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(page)
            except ImportError:
                pass
            print("Launched persistent context")

        url = "https://www.naukri.com/python-jobs?k=python&l=india"
        print(f"Navigating to: {url}")

        # Wait for networkidle so React hydration can finish
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        print("Title:", page.title())

        # Naukri uses React with hashed classnames — look for data attributes or role/semantic elements
        selectors_to_try = [
            # New Naukri React SRP selectors
            "div.srp-jobtuple-wrapper",
            "div[class*='srp-jobtuple']",
            "div[class*='jobTuple']",
            "div[class*='tuple']",
            "article[class*='tuple']",
            # New list-based
            "div.list",
            "div[class*='job-list']",
            # Generic fallbacks
            "a[class*='title']",
            "a[href*='/job-listings']",
            # Data attrs
            "div[data-job-id]",
            "div[data-id]",
        ]

        found_sel = None
        for sel in selectors_to_try:
            elems = page.query_selector_all(sel)
            print(f"  '{sel}' → {len(elems)} items")
            if elems and not found_sel:
                found_sel = sel

        if found_sel:
            first = page.query_selector(found_sel)
            html = first.evaluate("el => el.outerHTML")
            print(f"\nFirst card HTML ('{found_sel}'):\n{html[:3000]}")
        else:
            # Dump a section of the body
            print("\nDumping body innerHTML (first 4000 chars):")
            body = page.evaluate("document.body.innerHTML")
            print(body[:4000])

        if owned:
            browser_context.close()
        else:
            page.close()

if __name__ == "__main__":
    main()
