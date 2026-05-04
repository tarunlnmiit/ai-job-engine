import os
from playwright.sync_api import sync_playwright

def debug_linkedin():
    cdp_url = "http://localhost:9222"
    with sync_playwright() as p:
        try:
            print("Connecting to CDP...")
            browser = p.chromium.connect_over_cdp(cdp_url)
            print("Connected to CDP")
            context = browser.contexts[0]
            page = context.new_page()
            
            # Shorter timeout and more aggressive navigation
            url = "https://www.linkedin.com/jobs/search/?keywords=Software+Engineer&location=United+States&f_WT=2"
            print(f"Navigating to {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"Initial navigation timeout/error: {e}")
            
            print("Waiting for page to settle...")
            page.wait_for_timeout(10000)
            
            print(f"Title: {page.title()}")
            print(f"URL: {page.url}")
            
            # Take a screenshot
            page.screenshot(path="linkedin_debug.png")
            print("Screenshot saved to linkedin_debug.png")
            
            # Take a snapshot of the structure
            content = page.content()
            with open("linkedin_snapshot.html", "w") as f:
                f.write(content)
            print("Snapshot saved to linkedin_snapshot.html")
            
            # Check for common selectors
            selectors = [
                "div.job-card-container", 
                "li.jobs-search-results__list-item",
                "div.base-card",
                "a.job-card-list__title",
                "span.job-card-container__primary-description",
                "div.base-search-card",
                ".jobs-search-results-list"
            ]
            
            for s in selectors:
                count = page.locator(s).count()
                print(f"Selector '{s}': {count} elements")
                
            browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_linkedin()
