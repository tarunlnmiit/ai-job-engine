import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scraper.lever import LeverScraper
from core.scraper.greenhouse import GreenhouseScraper

print("=== Lever ===")
lever = LeverScraper()
jobs = lever.search("python")
print(f"Found: {len(jobs)}")
for j in jobs[:3]:
    print(f"  - {j.title} @ {j.company} | {j.application_url[:60]}")

print("\n=== Greenhouse ===")
gh = GreenhouseScraper()
jobs = gh.search("python")
print(f"Found: {len(jobs)}")
for j in jobs[:3]:
    print(f"  - {j.title} @ {j.company} | {j.application_url[:60]}")
