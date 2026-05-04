import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scraper.weworkremotely import WeWorkRemotely

def main():
    print("\nTesting WeWorkRemotely...")
    wwr = WeWorkRemotely()
    jobs = wwr.search("python")
    print(f"WeWorkRemotely found: {len(jobs)}")
    for j in jobs[:3]:
        print(f"  - {j.title} @ {j.company} | {j.location} | {j.application_url}")

if __name__ == "__main__":
    main()
