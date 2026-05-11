import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger
from playwright.sync_api import sync_playwright

logger = get_logger("scraper.lever")

# Verified Lever companies (added more European ones for the focus)
LEVER_COMPANIES = [
    # Global / US
    "lever", "outreach", "paytm", "zoox", "rippling", 
    "coda", "figma", "linear", "vercel", "brex", 
    "notion", "airtable", "segment", "hashicorp",
    "palantir", "canva", "dbt", "sourcegraph", "postman",
    # Europe Focus
    "mistral", "revolut", "bolt", "checkout", "blablacar",
    "deliveryhero", "hellofresh", "sumup", "transferwise",
    "skyscanner", "toptal"
]

class LeverScraper(BaseJobScraper):
    """Scrape jobs from Lever boards using Playwright to connect to existing Chrome."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Lever scraper: role=%r location=%r — checking %d companies", role, location, len(LEVER_COMPANIES))
        
        all_jobs = []
        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=True)
                
                for company in LEVER_COMPANIES:
                    try:
                        company_jobs = self._scrape_company(context, company, role, location)
                        all_jobs.extend(company_jobs)
                        logger.debug("Lever: Finished %s, total jobs: %d", company, len(all_jobs))
                    except Exception as e:
                        logger.error("Error scraping %s from Lever: %s", company, e)

        except Exception as e:
            logger.error("Lever scraper fatal error: %s", e)

        logger.info("Lever scrape complete — %d jobs found", len(all_jobs))
        return all_jobs

    def _scrape_company(self, context, company: str, role: str, location_filter: str = None) -> list[Job]:
        page = context.new_page()
        url = f"https://jobs.lever.co/{company}"
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for job listings
            page.wait_for_selector(".posting", timeout=10000)
            
            postings = page.query_selector_all(".posting")
            jobs = []
            
            for post in postings:
                title_elem = post.query_selector("h5")
                if not title_elem: continue
                
                title = title_elem.inner_text().strip()
                if role.lower() not in title.lower():
                    continue
                
                # Metadata (location, team, commitment)
                loc_elem = post.query_selector(".sort-by-location")
                team_elem = post.query_selector(".sort-by-team")
                commit_elem = post.query_selector(".sort-by-commitment")
                
                job_location = loc_elem.inner_text().strip() if loc_elem else "Remote"
                team = team_elem.inner_text().strip() if team_elem else ""
                commitment = commit_elem.inner_text().strip() if commit_elem else ""
                
                # Filter by location
                if location_filter and location_filter.lower() not in ("remote", "anywhere"):
                    if location_filter.lower() not in job_location.lower() and "remote" not in job_location.lower():
                        continue

                apply_url = post.query_selector("a.posting-title")
                href = apply_url.get_attribute("href") if apply_url else ""
                
                job = Job(
                    id=f"lever_{company}_{hashlib.md5(title.encode()).hexdigest()[:8]}",
                    title=title,
                    company=company.title(),
                    location=job_location,
                    description=f"Job at {company} - {team} ({commitment})",
                    platform="lever",
                    application_url=href,
                    is_remote="remote" in job_location.lower() or "remote" in commitment.lower(),
                    date_found=datetime.now().isoformat()
                )
                jobs.append(job)
            
            page.close()
            return jobs
        except Exception as e:
            logger.debug("Lever: No jobs found or timeout for %s", company)
            page.close()
            return []
