from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://wellfound.com/role/l/data-scientist/germany", wait_until="domcontentloaded")
    time.sleep(5)
    
    html = page.content()
    print("PAGE TITLE:", page.title())
    print("LENGTH OF HTML:", len(html))
    if "data-test" in html:
        print("Contains data-test")
    if "Cloudflare" in html or "cloudflare" in html or "Just a moment" in html:
        print("CLOUDFLARE DETECTED")
    
    with open("scratch/wellfound_dump.html", "w") as f:
        f.write(html)
    browser.close()
