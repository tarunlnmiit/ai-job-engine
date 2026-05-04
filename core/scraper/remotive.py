import httpx
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.remotive")


class RemotiveScraper(BaseJobScraper):
    """Scrape jobs from Remotive (remote-only jobs)."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Remotive for remote jobs matching role."""
        logger.info("Remotive search: role='%s'", role)
        jobs = []
        url = "https://remotive.com/api/remote-jobs"

        try:
            params = {"search": role}
            logger.debug("Remotive GET %s params=%s", url, params)
            r = httpx.get(url, params=params, timeout=10)
            logger.debug("Remotive response: HTTP %d — length: %d bytes", r.status_code, len(r.content))
            if r.status_code != 200:
                logger.warning("Remotive returned HTTP %d", r.status_code)
                return jobs

            data = r.json()
            raw_jobs = data.get("jobs", [])
            logger.debug("Remotive raw job count: %d", len(raw_jobs))

            for j in raw_jobs:
                job = Job(
                    id=f"remotive_{j['id']}",
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location=j.get("job_country", "Remote"),
                    description=j.get("description", ""),
                    skills_required=[],
                    platform="remotive",
                    application_url=j.get("url", ""),
                    is_easy_apply=False,
                    is_remote=True,
                    salary=j.get("salary", ""),
                    posted_date=None,
                    experience_required=None,
                    date_found=datetime.now().strftime("%Y-%m-%d"),
                )
                jobs.append(job)

        except Exception as e:
            logger.error("Error scraping Remotive: %s", e, exc_info=True)

        logger.info("Remotive scrape complete — %d jobs found", len(jobs))
        return jobs
