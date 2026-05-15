import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scraper.thehub import TheHubScraper
from core.scraper.make_it_in_germany import MakeItInGermanyScraper
from core.scraper.eures import EURESScraper
from core.scraper.workinluxembourg import WorkInLuxembourgScraper

def main():
    print("Testing The Hub Scraper...")
    hub = TheHubScraper()
    jobs = hub.search(role="Software Engineer", location="Denmark", max_pages=1)
    if jobs:
        print(f"Found {len(jobs)} jobs.")
        print(f"First job description snippet (up to 500 chars):")
        print(jobs[0].description[:500])
    else:
        print("No jobs found on The Hub.")
        
    print("\n-------------------------------\n")
    print("Testing Make it in Germany Scraper...")
    mig = MakeItInGermanyScraper()
    jobs = mig.search(role="Software Engineer", location="Germany", max_pages=1)
    if jobs:
        print(f"Found {len(jobs)} jobs.")
        print(f"First job description snippet (up to 500 chars):")
        print(jobs[0].description[:500])
    else:
        print("No jobs found on Make it in Germany.")

if __name__ == "__main__":
    main()
