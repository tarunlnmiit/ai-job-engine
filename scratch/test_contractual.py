import sys
import os
import asyncio
import traceback

# Add the project root to sys.path to import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import get_logger

logger = get_logger("test_contractual")

async def test_scraper(scraper_cls, name):
    print(f"\n======================\nTesting {name}...")
    scraper = scraper_cls()
    try:
        jobs = await scraper.search(role="engineer", location=None)
        print(f"[{name}] Found {len(jobs)} jobs:")
        for job in jobs[:2]:
            print(f" - {job.title} | {job.company} | {job.application_url}")
    except Exception as e:
        print(f"[{name}] Error: {e}")
        traceback.print_exc()

async def main():
    from core.scraper.arc_dev import ArcDevScraper
    from core.scraper.braintrust import BraintrustScraper
    from core.scraper.mercor import MercorScraper
    from core.scraper.pro5 import Pro5Scraper
    from core.scraper.turing import TuringScraper
    from core.scraper.uplers import UplersScraper

    scrapers = [
        (ArcDevScraper, "Arc.dev"),
        # (BraintrustScraper, "Braintrust"),
        (MercorScraper, "Mercor"),
        (Pro5Scraper, "Pro5.ai"),
        (TuringScraper, "Turing"),
        (UplersScraper, "Uplers"),
    ]

    for cls, name in scrapers:
        await test_scraper(cls, name)

if __name__ == "__main__":
    asyncio.run(main())
