import sys
import os
import asyncio

# Add the project root to sys.path to import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper.braintrust import BraintrustScraper
from logger import get_logger

logger = get_logger("test_braintrust")

async def test_scraper():
    scraper = BraintrustScraper()
    jobs = await scraper.search(role="engineer", location=None)
    print(f"Found {len(jobs)} jobs:")
    for job in jobs[:5]:
        print(job)

if __name__ == "__main__":
    asyncio.run(test_scraper())
