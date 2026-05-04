import httpx
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.greenhouse")

# All verified working as of May 2026 via boards-api.greenhouse.io/v1/boards/{slug}/jobs
GREENHOUSE_COMPANIES = [
    # Big Tech / Cloud
    "airbnb", "stripe", "figma", "gitlab", "databricks",
    "datadog", "vercel", "brex", "anthropic",
    # Fintech
    "coinbase", "robinhood", "chime", "monzo", "faire",
    # Productivity / SaaS
    "asana", "mixpanel", "gusto", "lattice", "amplitude",
    "postman", "dropbox", "twilio", "workato", "airtable",
    # Remote-first / tools
    "remote",
]


class GreenhouseScraper(BaseJobScraper):
    """Scrape jobs from Greenhouse boards via public API."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Greenhouse search: role='%s' — checking %d companies", role, len(GREENHOUSE_COMPANIES))
        jobs = []
        for company in GREENHOUSE_COMPANIES:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
            try:
                logger.debug("Greenhouse GET %s", url)
                r = httpx.get(url, timeout=10)
                if r.status_code != 200:
                    logger.debug("Greenhouse %s HTTP %d — skipping", company, r.status_code)
                    continue

                data = r.json()
                all_postings = data.get("jobs", [])
                matched = [j for j in all_postings if role.lower() in j["title"].lower()]
                logger.debug("Greenhouse %s: %d postings, %d match '%s'", company, len(all_postings), len(matched), role)

                for j in matched:
                    # Location: Greenhouse returns a location object
                    location_name = j.get("location", {}).get("name", "Remote")
                    # Filter by location if specified (loose match)
                    if location and location.lower() not in ("remote", "anywhere"):
                        if location.lower() not in location_name.lower() and "remote" not in location_name.lower():
                            continue

                    job = Job(
                        id=f"greenhouse_{j['id']}",
                        title=j["title"],
                        company=company.replace("-", " ").title(),
                        location=location_name,
                        description=j.get("content", ""),
                        skills_required=[],
                        platform="greenhouse",
                        application_url=j.get("absolute_url", ""),
                        is_easy_apply=False,
                        is_remote="remote" in location_name.lower(),
                        salary=None,
                        posted_date=j.get("updated_at", None),
                        experience_required=None,
                        date_found=datetime.now().strftime("%Y-%m-%d"),
                    )
                    jobs.append(job)
            except Exception as e:
                logger.error("Error scraping %s from Greenhouse: %s", company, e)
                continue

        logger.info("Greenhouse scrape complete — %d jobs found", len(jobs))
        return jobs
