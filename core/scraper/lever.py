import httpx
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

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
    """Scrape jobs from Lever boards via public API."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Lever boards for jobs using the public API."""
        logger.info("Lever API search: role=%r location=%r — checking %d companies", role, location, len(LEVER_COMPANIES))
        
        all_jobs = []
        for company in LEVER_COMPANIES:
            try:
                company_jobs = self._scrape_company_api(company, role, location)
                all_jobs.extend(company_jobs)
            except Exception as e:
                logger.error("Error scraping %s from Lever API: %s", company, e)

        logger.info("Lever API scrape complete — %d jobs found", len(all_jobs))
        return all_jobs

    def _scrape_company_api(self, company: str, role: str, location_filter: str = None) -> list[Job]:
        url = f"https://api.lever.co/v0/postings/{company}"
        try:
            r = httpx.get(url, timeout=15)
            if r.status_code != 200:
                return []

            data = r.json()
            jobs = []
            for j in data:
                title = j.get("text", "")
                if role.lower() not in title.lower():
                    continue

                # Location parsing
                categories = j.get("categories", {})
                job_location = categories.get("location", "Remote")
                commitment = categories.get("commitment", "")
                team = categories.get("team", "")
                
                # Workplace type
                workplace = j.get("workplaceType", "").lower()
                is_remote = workplace == "remote" or "remote" in job_location.lower()

                # Location filter
                if location_filter and location_filter.lower() not in ("remote", "anywhere"):
                    if location_filter.lower() not in job_location.lower() and not is_remote:
                        continue

                job = Job(
                    id=f"lever_{j.get('id')}",
                    title=title,
                    company=company.replace("-", " ").title(),
                    location=job_location,
                    description=j.get("descriptionHtml", "") + "\n" + j.get("additional", ""),
                    skills_required=[],
                    platform="lever",
                    application_url=j.get("applyUrl", ""),
                    is_easy_apply=False,
                    is_remote=is_remote,
                    salary=None,
                    posted_date=datetime.fromtimestamp(j.get("createdAt", 0) / 1000).isoformat() if j.get("createdAt") else None,
                    experience_required=None,
                    date_found=datetime.now().isoformat()
                )
                jobs.append(job)
            return jobs
        except Exception as e:
            logger.warning("Lever API error for %s: %s", company, e)
            return []
