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

logger = get_logger("scraper.relocateme")

class RelocateMeScraper(BaseJobScraper):
    """Scrape jobs from Relocate.me using Playwright."""

    def search(self, role: str, location: str = "Germany", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching Relocate.me: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("Relocate.me search complete: %d jobs found", len(jobs))
        return jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        if not BS_AVAILABLE:
            return []

        jobs = []
        cdp_url = "http://localhost:9222"

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    context = browser.contexts[0]
                    page = context.new_page()
                except Exception as e:
                    logger.warning("Could not connect to CDP, launching fresh browser: %s", e)
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                # URL format: https://relocate.me/search?query={role}&location={location}
                search_query = role.replace(" ", "+")
                loc_query = location.replace(" ", "+")
                url = f"https://relocate.me/search?query={search_query}&location={loc_query}"
                
                logger.info("Navigating to %s", url)
                page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Check for "jobs available" text to confirm load
                try:
                    page.wait_for_selector(".jobs-list", timeout=10000)
                except:
                    # Alternative selector based on markdown analysis
                    try:
                        page.wait_for_selector("a[href*='/j/']", timeout=5000)
                    except:
                        logger.warning("Job cards not found on Relocate.me.")
                        return []

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Looking at the markdown, jobs are in sections or links
                # Usually job cards have a specific structure on relocate.me
                # Let's try to find them by link pattern /j/
                job_links = soup.select("a[href*='/j/']")
                
                for link_tag in job_links:
                    try:
                        # Find the parent container that has more info
                        # On relocate.me, the link usually contains the title
                        title = link_tag.get_text(strip=True)
                        if not title or len(title) < 5: continue
                        
                        href = link_tag["href"]
                        if not href.startswith("http"):
                            href = "https://relocate.me" + href
                            
                        # Unique ID
                        job_id = hashlib.md5(href.encode()).hexdigest()
                        
                        # Parent or siblings often contain company/location
                        parent = link_tag.find_parent()
                        # Relocate.me markdown shows company above the link in some views
                        # or in a specific block. Let's try to find company and location.
                        company = "Unknown"
                        job_location = location
                        
                        # Try to find nearby text for company/location
                        container = link_tag.find_parent("div", class_="job-card") or parent
                        if container:
                            # This depends on the exact HTML, but based on common patterns:
                            comp_elem = container.select_one(".company-name") or container.select_one("strong")
                            if comp_elem:
                                company = comp_elem.get_text(strip=True)
                            
                            loc_elem = container.select_one(".location") or container.select_one("span")
                            if loc_elem:
                                job_location = loc_elem.get_text(strip=True)

                        job = Job(
                            id=job_id,
                            title=title,
                            company=company,
                            location=job_location,
                            description=f"International relocation opportunity in {job_location}",
                            application_url=href,
                            platform="Relocate.me",
                            date_found=datetime.now().isoformat()
                        )
                        jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing Relocate.me card: %s", e)
                        continue

                page.close()
                # Deduplicate by ID
                unique_jobs = {j.id: j for j in jobs}.values()
                return list(unique_jobs)

        except Exception as e:
            logger.error("Relocate.me scraping error: %s", e)
            return []
