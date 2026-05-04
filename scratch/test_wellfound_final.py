import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scraper.wellfound import WellfoundScraper

def main():
    print("\nTesting Wellfound...")
    wf = WellfoundScraper()
    jobs = wf.search("python")
    print(f"Wellfound found: {len(jobs)}")
    for j in jobs[:5]:
        print(f"  - {j.title} @ {j.company} | {j.location} | salary={j.salary} | {j.application_url}")

if __name__ == "__main__":
    main()
