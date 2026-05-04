import sys
import os
from playwright.sync_api import sync_playwright
import time

def inspect_instahyre():
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.getcwd(), "data", "browser_session")
        os.makedirs(user_data_dir, exist_ok=True)
        
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        
        try:
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(page)
            except:
                pass
                
            print("Navigating to Instahyre...")
            page.goto("https://www.instahyre.com/search-jobs/", wait_until="domcontentloaded", timeout=30000)
            
            print("Waiting 10 seconds for initial load...")
            page.wait_for_timeout(10000)
            
            print("Taking screenshot 1...")
            page.screenshot(path="scratch/instahyre_1.png")
            
            # Type into search
            try:
                page.fill("input#search-skills", "Python")
                page.keyboard.press("Enter")
                print("Searched for Python. Waiting 10 seconds...")
                page.wait_for_timeout(10000)
            except Exception as e:
                print("Search failed:", e)
                
            print("Taking screenshot 2...")
            page.screenshot(path="scratch/instahyre_2.png")
            
            html = page.content()
            with open("scratch/instahyre.html", "w") as f:
                f.write(html)
            print("Saved HTML")
            
        except Exception as e:
            print("Error:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    inspect_instahyre()
