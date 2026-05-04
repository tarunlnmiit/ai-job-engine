import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        print("Connected via CDP")

        url = "https://wellfound.com/jobs?q=python&remote=true"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Wait for apply buttons to appear (confirms job cards are rendered)
        page.wait_for_selector("[data-test='JobApplicationApplyButton']", timeout=20000)
        page.wait_for_timeout(2000)
        print("Title:", page.title())

        # Find the parent container of an apply button — that's our job card
        card_html = page.evaluate("""
            () => {
                const btn = document.querySelector("[data-test='JobApplicationApplyButton']");
                if (!btn) return "NO BUTTON FOUND";
                // Walk up to find a meaningful container
                let el = btn;
                for (let i = 0; i < 8; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    // Look for a container that has title-like text content
                    const h = el.querySelector('a[href*="/jobs/"]') || el.querySelector('h2') || el.querySelector('h3');
                    if (h) return el.outerHTML.substring(0, 4000);
                }
                return btn.parentElement.parentElement.outerHTML.substring(0, 4000);
            }
        """)
        print("\nJob card HTML:\n", card_html)

        # Also check how many apply buttons (= how many job cards)
        count = len(page.query_selector_all("[data-test='JobApplicationApplyButton']"))
        print(f"\nTotal apply buttons (job cards): {count}")

        # Find job title links
        job_links = page.evaluate("""
            () => [...document.querySelectorAll('a[href*="/jobs/"]')]
                    .map(a => ({href: a.href, text: a.innerText.trim().substring(0, 80)}))
                    .filter(a => a.text.length > 0)
                    .slice(0, 10)
        """)
        print("\nJob links found:")
        for l in job_links:
            print(f"  {l['href']} → {l['text']}")

        page.close()

if __name__ == "__main__":
    main()
