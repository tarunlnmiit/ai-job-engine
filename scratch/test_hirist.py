import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.scraper.hirist import HiristScraper

def test_hirist():
    print("Testing Hirist Scraper...")
    scraper = HiristScraper()
    
    # Test with a common role
    role = "Python Developer"
    location = "Remote"
    
    print(f"Searching for '{role}' in '{location}'...")
    jobs = scraper.search(role=role, location=location, max_pages=1)
    
    print(f"\nFound {len(jobs)} jobs.")
    
    for i, job in enumerate(jobs[:5], 1):
        print(f"\n--- Job {i} ---")
        print(f"Title: {job.title}")
        print(f"Company: {job.company}")
        print(f"Location: {job.location}")
        print(f"Link: {job.application_url}")
        print(f"Description: {job.description[:100]}...")

if __name__ == "__main__":
    test_hirist()
