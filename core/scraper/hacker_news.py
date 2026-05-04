import httpx
import re
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.hacker_news")

class HackerNewsScraper(BaseJobScraper):
    """Scrape jobs from Hacker News 'Who is hiring' threads using Algolia API."""

    ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
    ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items"

    def search(self, role: str, location: str = "", max_pages: int = 1, **kwargs) -> list[Job]:
        """Search the latest HN 'Who is hiring' thread for matching roles."""
        logger.info("HN search: role='%s' location='%s'", role, location)
        jobs = []

        try:
            # 1. Find the latest 'Who is hiring' story
            params = {
                "tags": "story,author_whoishiring",
                "query": "Who is hiring",
                "hitsPerPage": 1
            }
            r = httpx.get(self.ALGOLIA_SEARCH_URL, params=params, timeout=10)
            if r.status_code != 200:
                logger.error("HN Algolia search failed with status %d", r.status_code)
                return []

            hits = r.json().get("hits", [])
            if not hits:
                logger.warning("No 'Who is hiring' threads found")
                return []

            latest_story = hits[0]
            story_id = latest_story["objectID"]
            story_title = latest_story["title"]
            logger.info("Found latest HN thread: '%s' (ID: %s)", story_title, story_id)

            # 2. Get all comments (job posts) for this story
            story_r = httpx.get(f"{self.ALGOLIA_ITEM_URL}/{story_id}", timeout=20)
            if story_r.status_code != 200:
                logger.error("Failed to fetch HN story details for ID %s", story_id)
                return []

            story_data = story_r.json()
            comments = story_data.get("children", [])
            logger.debug("Processing %d top-level comments from HN thread", len(comments))

            # 3. Filter comments by role and location
            # Note: Top-level comments in 'Who is hiring' are the actual job posts
            for comment in comments:
                text = comment.get("text")
                if not text:
                    continue

                # Basic filtering
                text_lower = text.lower()
                role_match = not role or role.lower() in text_lower
                loc_match = not location or location.lower() in text_lower

                if role_match and loc_match:
                    job = self._parse_comment(comment, story_id)
                    if job:
                        jobs.append(job)

        except Exception as e:
            logger.error("Error scraping Hacker News: %s", e, exc_info=True)

        logger.info("HN scrape complete — %d jobs matched", len(jobs))
        return jobs

    def _parse_comment(self, comment: dict, story_id: str) -> Job:
        """Parse an HN comment into a Job object."""
        html_text = comment.get("text", "")
        # Remove HTML tags for the description
        clean_text = re.sub('<[^<]+?>', ' ', html_text)
        clean_text = clean_text.replace('&quot;', '"').replace('&amp;', '&').replace('&#x27;', "'")
        
        # Try to extract Company and Role from the first line
        # HN posts usually follow: Company | Role | Location | Type
        lines = clean_text.split('\n')
        header = lines[0].strip()
        parts = [p.strip() for p in header.split('|')]
        
        company = parts[0] if len(parts) > 0 else "Unknown"
        title = parts[1] if len(parts) > 1 else parts[0]
        location = parts[2] if len(parts) > 2 else "Remote"
        
        # If parts didn't work well, fallback
        if len(company) > 50: # Likely not just a company name
            company = "Hacker News Post"

        job_id = f"hn_{comment['id']}"
        app_url = f"https://news.ycombinator.com/item?id={comment['id']}"

        return Job(
            id=job_id,
            title=title,
            company=company,
            location=location,
            description=clean_text[:1000] + ("..." if len(clean_text) > 1000 else ""),
            application_url=app_url,
            platform="hacker_news",
            is_remote="remote" in location.lower() or "remote" in clean_text.lower(),
            date_found=datetime.now().strftime("%Y-%m-%d"),
            posted_date=datetime.fromtimestamp(comment.get("created_at_i", datetime.now().timestamp()))
        )
