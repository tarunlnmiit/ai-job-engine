import sys
import os
import asyncio
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from core.scraper.arc_dev import ArcDevScraper
    from core.scraper.pro5 import Pro5Scraper

    for scraper_cls, name in [(ArcDevScraper, "Arc.dev"), (Pro5Scraper, "Pro5.ai")]:
        print(f"\n======================\nTesting {name}...")
        scraper = scraper_cls()
        try:
            jobs = await scraper.search(role="engineer", location=None)
            print(f"[{name}] Found {len(jobs)} jobs:")
            for job in jobs[:2]:
                print(f" - {job.title} | {job.application_url}")
        except Exception as e:
            print(f"[{name}] Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
