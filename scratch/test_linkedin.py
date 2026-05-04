import os
import sys
# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper.linkedin import LinkedInScraper
from logger import get_logger

logger = get_logger("test_linkedin")

def test_linkedin():
    scraper = LinkedInScraper()
    print("Searching for 'Software Engineer' jobs on LinkedIn...")
    # Using 'India' location for testing if the user is in India, or 'United States'
    jobs = scraper.search("Software Engineer", location="United States", remote=True)
    
    print(f"\nFound {len(jobs)} jobs:")
    for i, job in enumerate(jobs[:10]):
        print(f"{i+1}. {job.title} at {job.company} ({job.location})")
        print(f"   Easy Apply: {job.is_easy_apply}")
        print(f"   URL: {job.application_url}")
        print(f"   Desc (first 100 chars): {job.description[:100]}...")

if __name__ == "__main__":
    test_linkedin()
