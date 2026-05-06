import httpx
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.mercor")


class MercorScraper(BaseJobScraper):
    """Scrape jobs from Mercor."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Mercor for jobs matching role."""
        logger.info("Mercor search: role='%s'", role)
        jobs = []
        
        # TODO: Implement actual scraping logic for Mercor
        logger.warning("MercorScraper is a placeholder and needs implementation.")

        logger.info("Mercor scrape complete — %d jobs found", len(jobs))
        return jobs
