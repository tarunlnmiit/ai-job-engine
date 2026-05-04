import sys
import os
sys.path.append(os.getcwd())

from core.scraper.lever import LeverScraper
from logger import get_logger

logger = get_logger("test_lever")

def test():
    scraper = LeverScraper()
    # Test with just one company that we know might be failing or working
    from core.scraper.lever import LEVER_COMPANIES
    scraper.search_companies = ["palantir", "lever"]
    # Manually override the loop in search if needed, but I'll just change the list in the class for this instance
    import core.scraper.lever
    core.scraper.lever.LEVER_COMPANIES = ["palantir", "lever"]
    
    jobs = scraper.search(role="Software Engineer", location="Remote")
    print(f"Found {len(jobs)} jobs")
    for j in jobs:
        print(f"{j.company} - {j.title}")

if __name__ == "__main__":
    test()
