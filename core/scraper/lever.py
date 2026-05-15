import hashlib
import json
import urllib.request
import urllib.error
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.lever")

# Companies known to use Lever for their job boards
LEVER_COMPANIES = [
    # Global / US
    "lever", "outreach", "zoox", "rippling",
    "coda", "linear", "vercel", "brex",
    "notion", "airtable", "hashicorp",
    "palantir", "canva", "sourcegraph", "postman",
    # Europe Focus
    "mistral", "revolut", "bolt-eu", "checkout", "blablacar",
    "deliveryhero", "hellofresh", "sumup", "wise",
    "skyscanner", "toptal",
]


class LeverScraper(BaseJobScraper):
    """Scrape jobs from Lever boards using the public JSON API.
    
    Uses https://api.lever.co/v0/postings/{company}?mode=json — 
    no browser needed, much faster and more reliable than Playwright.
    """

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Lever scraper: role=%r location=%r — checking %d companies", role, location, len(LEVER_COMPANIES))

        all_jobs = []
        for company in LEVER_COMPANIES:
            try:
                company_jobs = self._fetch_company(company, role, location)
                if company_jobs:
                    logger.info("✅ Lever: %s — %d matching jobs", company, len(company_jobs))
                    all_jobs.extend(company_jobs)
                else:
                    logger.info("   Lever: %s — no matching jobs", company)
            except Exception as e:
                logger.warning("⚠️  Lever: %s — error: %s", company, e)

        logger.info("Lever scrape complete — %d jobs found", len(all_jobs))
        return all_jobs

    def _fetch_company(self, company: str, role: str, location_filter: str = None) -> list[Job]:
        """Fetch jobs from a company's Lever board via the public JSON API."""
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug("Lever: %s — no board found (404)", company)
            else:
                logger.debug("Lever: %s — HTTP %d", company, e.code)
            return []
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return []

        if not isinstance(data, list):
            return []

        jobs = []
        role_lower = role.lower()

        for posting in data:
            title = posting.get("text", "")
            if role_lower not in title.lower():
                continue

            categories = posting.get("categories", {})
            job_location = categories.get("location", "Remote")
            commitment = categories.get("commitment", "")
            team = categories.get("team", "")

            # Filter by location
            if location_filter and location_filter.lower() not in ("remote", "anywhere", "any", "germany"):
                if location_filter.lower() not in job_location.lower() and "remote" not in job_location.lower():
                    continue

            description = posting.get("descriptionPlain", "")
            additional = posting.get("additionalPlain", "")
            full_description = f"{description}\n\n{additional}".strip()

            href = posting.get("hostedUrl", "")
            job_id = f"lever_{company}_{hashlib.md5(title.encode()).hexdigest()[:8]}"

            job = Job(
                id=job_id,
                title=title,
                company=company.replace("-", " ").title(),
                location=job_location,
                description=full_description[:3000],
                platform="lever",
                application_url=href,
                is_remote="remote" in job_location.lower() or "remote" in commitment.lower(),
                date_found=datetime.now().isoformat()
            )
            jobs.append(job)

        return jobs
