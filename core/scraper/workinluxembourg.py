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

logger = get_logger("scraper.workinluxembourg")

class WorkInLuxembourgScraper(BaseJobScraper):
    """Scrape jobs from Work in Luxembourg (ADEM) using Playwright."""

    def search(self, role: str, location: str = "Luxembourg", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching Work in Luxembourg: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("Work in Luxembourg search complete: %d jobs found", len(jobs))
        return jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        if not BS_AVAILABLE:
            return []

        jobs = []
        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=True)
                page = context.new_page()

                for p_num in range(max_pages):
                    # URL format: https://jobs.workinluxembourg.com/offers?q={role}&page={p_num}
                    search_query = role.replace(" ", "+")
                    url = f"https://jobs.workinluxembourg.com/offers?q={search_query}&page={p_num}"
                    
                    logger.info("Navigating to %s", url)
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Wait for job listings
                    try:
                        page.wait_for_selector(".offer-card", timeout=20000)
                    except:
                        logger.warning("No job cards found on Work in Luxembourg for page %d.", p_num)
                        break

                    # Small delay to ensure content is rendered
                    page.wait_for_timeout(2000)
                    
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, "html.parser")
                    
                    # Job cards are <a> with class link-wrapper containing .offer-card
                    cards = soup.select("a.link-wrapper")
                    if not cards:
                        break

                    for card in cards:
                        try:
                            # Title is in h5
                            title_elem = card.select_one("h5")
                            if not title_elem: continue
                            title = title_elem.get_text(strip=True)
                            
                            # Link is the href of the card itself
                            href = card["href"]
                            if not href.startswith("http"):
                                href = "https://jobs.workinluxembourg.com" + href
                                
                            # Company is usually the first span inside .offer-card
                            # Or we can look for it more specifically if we had more info
                            company = "Luxembourg Employer"
                            inner_card = card.select_one(".offer-card")
                            if inner_card:
                                spans = inner_card.select("span")
                                if spans:
                                    company = spans[0].get_text(strip=True)
                                
                            job_location = "Luxembourg" # Default for this site
                            
                            job_id = hashlib.md5(href.encode()).hexdigest()

                            # FETCH FULL DESCRIPTION
                            description = ""
                            try:
                                logger.info("Fetching Work in Luxembourg detail: %s", title)
                                detail_page = context.new_page()
                                detail_page.goto(href, wait_until="domcontentloaded", timeout=30000)
                                
                                desc_elem = detail_page.locator(".offer-details, .job-description, main, body").first
                                if desc_elem.is_visible():
                                    description = desc_elem.inner_text()[:5000]
                                else:
                                    description = detail_page.locator("body").inner_text()[:5000]
                                
                                detail_page.close()
                            except Exception as desc_e:
                                logger.warning("Could not fetch detail for %s: %s", href, desc_e)
                                description = "Source: Work in Luxembourg (ADEM Official Portal)"

                            job = Job(
                                id=job_id,
                                title=title,
                                company=company,
                                location=job_location,
                                description=description,
                                application_url=href,
                                platform="WorkInLuxembourg",
                                date_found=datetime.now().isoformat()
                            )
                            jobs.append(job)
                        except Exception as e:
                            logger.error("Error parsing Work in Luxembourg card: %s", e)
                            continue
                            
                page.close()
                return jobs

        except Exception as e:
            logger.error("Work in Luxembourg scraping error: %s", e)
            return []
