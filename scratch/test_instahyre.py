import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.scraper.instahyre import InstahyreScraper

def test_instahyre():
    scraper = InstahyreScraper()
    jobs = scraper.search(role="Data Scientist", location="")
    print(f"Found {len(jobs)} jobs from Instahyre.")
    for j in jobs[:2]:
        print(j.title, j.company, j.application_url)

if __name__ == "__main__":
    test_instahyre()
