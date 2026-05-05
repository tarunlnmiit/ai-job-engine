import random
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

try:
    from bs4 import BeautifulSoup
    BS_AVAILABLE = True
except ImportError:
    BS_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = get_logger("scraper.hirist")

class HiristScraper(BaseJobScraper):
    """Scrape jobs from Hirist using Playwright."""

    def search(self, role: str, location: str = "Remote", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching Hirist: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("Hirist search complete: %d jobs found", len(jobs))
        return jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        """Scrape Hirist search results using Playwright."""
        jobs = []

        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=False)
                page = context.pages[0] if context.pages else context.new_page()

                # Hirist search URL format: https://www.hirist.com/search/{role}-{location}.html
                # Replace spaces with hyphens
                search_query = f"{role} {location}".strip().replace(" ", "-").lower()
                url = f"https://www.hirist.com/search/{search_query}.html"
                
                logger.info("Navigating to %s", url)
                page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Wait for job cards to load
                try:
                    page.wait_for_selector(".joblist-card-v2", timeout=10000)
                except:
                    logger.warning("Job cards not found on Hirist page.")
                    return []

                # Scroll to load more if needed (Hirist uses infinite scroll)
                if max_pages > 1:
                    for _ in range(max_pages * 2):
                        page.keyboard.press("PageDown")
                        page.wait_for_timeout(1000)

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Cards can be identified by class or data-testid
                cards = soup.select(".joblist-card-v2")
                if not cards:
                    cards = soup.select('[data-testid^="job-list-"]')

                for card in cards:
                    try:
                        title_elem = card.select_one('[data-testid="job_title"]')
                        if not title_elem:
                            continue
                            
                        title = title_elem.get_text(strip=True)
                        
                        # Link is usually the parent <a>
                        link_elem = card.find_parent("a") or card.select_one("a")
                        link = ""
                        if link_elem and link_elem.has_attr("href"):
                            link = link_elem["href"]
                            if not link.startswith("http"):
                                link = "https://www.hirist.com" + link

                        # Company name - Hirist often hides this or puts it in a separate tag
                        # Sometimes it's in a subtitle or not present on the card for premium jobs
                        company = "Confidential/Premium"
                        
                        location_elem = card.select_one('[data-testid="job_location"]')
                        job_location = location_elem.get_text(strip=True) if location_elem else location

                        exp_elem = card.select_one('[data-testid="job_experience"]')
                        experience = exp_elem.get_text(strip=True) if exp_elem else "N/A"

                        # Extract tags (skills)
                        tags = [tag.get_text(strip=True) for tag in card.select('[data-testid^="job_tag_"]')]
                        description = f"Experience: {experience}. Skills: {', '.join(tags)}"

                        # Unique ID for the job
                        import hashlib
                        job_id = hashlib.md5(f"{title}{company}{link}".encode()).hexdigest()

                        job = Job(
                            id=job_id,
                            title=title,
                            company=company,
                            location=job_location,
                            description=description,
                            application_url=link,
                            platform="Hirist",
                            date_found=datetime.now().isoformat()
                        )
                        jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing Hirist card: %s", e)
                        continue

                page.close()
                return jobs

        except Exception as e:
            logger.error("Hirist scraping error: %s", e)
            return []
