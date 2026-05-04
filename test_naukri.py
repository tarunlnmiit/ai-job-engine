#!/usr/bin/env python3
"""Test Naukri scraper — API first, then Playwright with Google OAuth fallback."""

import sys
sys.path.insert(0, '.')

from logger import get_logger
logger = get_logger("test")

from core.scraper.naukri import NaukriScraper

logger.info("Testing Naukri scraper (API → Google OAuth Playwright fallback)...")
scraper = NaukriScraper()

print("\n" + "="*60)
print("Testing Naukri search: 'Data Scientist' in India")
print("="*60)

jobs = scraper.search("Data Scientist", location="India", experience=2)

print(f"\nTotal jobs found: {len(jobs)}")
if jobs:
    print(f"\nFirst {min(5, len(jobs))} jobs:\n")
    for i, job in enumerate(jobs[:5]):
        print(f"[{i+1}] {job.title}")
        print(f"    Company: {job.company}")
        print(f"    Location: {job.location}")
        print(f"    Remote: {job.is_remote}")
        print(f"    URL: {job.application_url[:70]}")
        print()
else:
    print("\nNo jobs found.")
    print("Note: If API returned 0 results, Playwright will attempt Google OAuth login.")
    print("Ensure GOOGLE_EMAIL and GOOGLE_PASSWORD are set in .env")
    print("Use Google App Password (not main password) for security.")

print("\n" + "="*60)
logger.info("Test complete")
