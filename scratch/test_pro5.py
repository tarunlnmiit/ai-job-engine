import sys
import os
import asyncio
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from core.scraper.pro5 import Pro5Scraper

    scraper = Pro5Scraper()
    jobs = await scraper.search("engineer")
    print(f"Pro5 found {len(jobs)} jobs")
    for j in jobs[:2]:
        print(j.title, j.application_url)

if __name__ == "__main__":
    asyncio.run(main())
