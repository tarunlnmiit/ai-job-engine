import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scraper.remotive import RemotiveScraper
from core.scraper.weworkremotely import WeWorkRemotely
from core.scraper.wellfound import WellfoundScraper

async def main():
    print("Testing Remotive...")
    remotive = RemotiveScraper()
    jobs = remotive.search("python")
    print(f"Remotive found: {len(jobs)}")
    
    print("\nTesting WeWorkRemotely...")
    wwr = WeWorkRemotely()
    jobs = wwr.search("python")
    print(f"WeWorkRemotely found: {len(jobs)}")
    
    print("\nTesting Wellfound...")
    wf = WellfoundScraper()
    jobs = wf.search("python")
    print(f"Wellfound found: {len(jobs)}")

if __name__ == "__main__":
    asyncio.run(main())
