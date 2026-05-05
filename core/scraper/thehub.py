import hashlib
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

logger = get_logger("scraper.thehub")

class TheHubScraper(BaseJobScraper):
    """Scrape jobs from The Hub (Nordics) using Playwright."""

    def search(self, role: str, location: str = "Denmark", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching The Hub: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("The Hub search complete: %d jobs found", len(jobs))
        return jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        if not BS_AVAILABLE:
            return []

        jobs = []
        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=False)
                page = context.new_page()

                # URL format: https://thehub.io/jobs?search={role}&country={location}
                country_map = {
                    "denmark": "DK",
                    "norway": "NO",
                    "sweden": "SE",
                    "finland": "FI"
                }
                country_code = country_map.get(location.lower(), "DK")
                
                url = f"https://thehub.io/jobs?search={role.replace(' ', '%20')}&country={country_code}"
                
                logger.info("Navigating to %s", url)
                page.bring_to_front()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for job listings
                try:
                    page.wait_for_selector(".job-card, [class*='JobCard'], a[href*='/jobs/']", timeout=20000)
                except:
                    logger.warning("Job listings not found on The Hub.")
                    return []

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Job cards are usually in specific classes
                cards = soup.select(".job-card") or soup.select("[class*='JobCard']") or soup.select(".card")
                if not cards:
                    # Fallback to link pattern
                    cards = soup.select("a[href*='/jobs/']")
                    # Filter for links that look like job cards
                    cards = [c.find_parent("div") or c for c in cards if len(c.get_text()) > 10]
                for card in cards:
                    try:
                        title_elem = card.select_one(".job-card__title") or card.select_one("h4")
                        if not title_elem: continue
                        
                        title = title_elem.get_text(strip=True)
                        
                        link_elem = card.select_one("a[href*='/jobs/']")
                        if not link_elem: continue
                        
                        href = link_elem["href"]
                        if not href.startswith("http"):
                            href = "https://thehub.io" + href
                            
                        company = "Unknown"
                        comp_elem = card.select_one(".job-card__company-name")
                        if comp_elem:
                            company = comp_elem.get_text(strip=True)
                            
                        job_location = location
                        loc_elem = card.select_one(".job-card__location")
                        if loc_elem:
                            job_location = loc_elem.get_text(strip=True)

                        job_id = hashlib.md5(href.encode()).hexdigest()

                        job = Job(
                            id=job_id,
                            title=title,
                            company=company,
                            location=job_location,
                            description=f"Startup job in the Nordics ({job_location})",
                            application_url=href,
                            platform="The Hub",
                            date_found=datetime.now().isoformat()
                        )
                        jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing The Hub card: %s", e)
                        continue

                page.close()
                return jobs

        except Exception as e:
            logger.error("The Hub scraping error: %s", e)
            return []
