import sys
from playwright.sync_api import sync_playwright

def inspect_instahyre():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Add stealth if possible
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(page)
            except:
                pass
                
            page.goto("https://www.instahyre.com/search-jobs/", wait_until="networkidle", timeout=15000)
            
            # Print title
            print("Title:", page.title())
            
            # Wait for any job card wrapper, or just grab the body
            try:
                page.wait_for_selector(".employer-row, .employer-block, .job-card", timeout=5000)
            except:
                pass
            
            html = page.content()
            if "Just a moment..." in html:
                print("Blocked by Cloudflare!")
            else:
                print("HTML snippet:")
                print(html[1000:2000]) # just a sample
                
                # Check for input fields or job cards
                inputs = page.query_selector_all("input")
                print(f"Found {len(inputs)} input fields")
                
        except Exception as e:
            print("Error:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    inspect_instahyre()
