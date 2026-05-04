import os
import sys
# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper.indeed import IndeedScraper
from logger import get_logger

logger = get_logger("test_indeed")

def test_indeed():
    scraper = IndeedScraper()
    print("Searching for 'Software Engineer' jobs on Indeed...")
    jobs = scraper.search("Software Engineer", location="Remote", max_pages=1)
    
    print(f"\nFound {len(jobs)} jobs:")
    for i, job in enumerate(jobs[:10]):
        print(f"{i+1}. {job.title} at {job.company} ({job.location})")
        print(f"   Salary: {job.salary}")
        print(f"   URL: {job.application_url}")

if __name__ == "__main__":
    test_indeed()
