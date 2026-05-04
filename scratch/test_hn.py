import sys
import os
from pathlib import Path

# Add the project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.scraper.hacker_news import HackerNewsScraper

def test_hn_scraper():
    scraper = HackerNewsScraper()
    print("Searching Hacker News for 'Python' jobs...")
    jobs = scraper.search(role="Python", location="")
    
    print(f"\nFound {len(jobs)} jobs:")
    for i, job in enumerate(jobs[:5]):
        print(f"\n--- Job {i+1} ---")
        print(f"Title: {job.title}")
        print(f"Company: {job.company}")
        print(f"Location: {job.location}")
        print(f"URL: {job.application_url}")
        print(f"Snippet: {job.description[:100]}...")

if __name__ == "__main__":
    test_hn_scraper()
