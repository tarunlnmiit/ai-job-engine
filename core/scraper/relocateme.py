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
        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=False)
                page = context.new_page()

                # Global search for role only to avoid flaky location parameters
                search_query = role.replace(" ", "+")
                url = f"https://relocate.me/search?query={search_query}"
                
                logger.info("Navigating to %s (Global Search)", url)
                page.bring_to_front()
                page.goto(url, wait_until="load", timeout=60000)
                page.wait_for_timeout(2000)
                
                # Wait for job listings
                try:
                    page.wait_for_selector(".jobs-list, .jobs-list__job", timeout=20000)
                except:
                    # Check for Cloudflare
                    if "Cloudflare" in page.content() or "cf-browser-verification" in page.content():
                        logger.warning("Cloudflare challenge detected on Relocate.me. Please solve it in the browser.")
                        # Wait a bit longer for user to solve
                        try:
                            page.wait_for_selector(".jobs-list, .jobs-list__job", timeout=30000)
                        except:
                            return []
                    else:
                        logger.warning("Job listings not found on Relocate.me search results.")
                        return []

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Find job items
                job_items = soup.select(".jobs-list__job")
                for item in job_items:
                    try:
                        title_elem = item.select_one(".job__title a")
                        if not title_elem:
                            continue
                        
                        title = title_elem.get_text(strip=True).split("\nin")[0].strip()
                        href = title_elem["href"]
                        if not href.startswith("http"):
                            href = "https://relocate.me" + href
                            
                        # Unique ID
                        job_id = hashlib.md5(href.encode()).hexdigest()
                        
                        # Info blocks (Location and Company are often in similar div structures)
                        info_blocks = item.select(".job__company p")
                        job_location = "International"
                        company = "Unknown"
                        
                        if len(info_blocks) >= 1:
                            job_location = info_blocks[0].get_text(strip=True)
                        if len(info_blocks) >= 2:
                            company = info_blocks[1].get_text(strip=True)

                        # Location filter (case-insensitive)
                        if location and location.lower() not in ("remote", "anywhere", "international"):
                            if location.lower() not in job_location.lower():
                                # Try checking the title or the URL if the location block is messy
                                if location.lower() not in title.lower() and location.lower() not in href.lower():
                                    continue

                        job = Job(
                            id=job_id,
                            title=title,
                            company=company,
                            location=job_location,
                            description=f"International relocation opportunity in {job_location}. Company: {company}",
                            application_url=href,
                            platform="Relocate.me",
                            date_found=datetime.now().isoformat()
                        )
                        jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing Relocate.me job item: %s", e)
                        continue

                page.close()
                # Deduplicate by ID
                unique_jobs = {j.id: j for j in jobs}.values()
                return list(unique_jobs)

        except Exception as e:
            logger.error("Relocate.me scraping error: %s", e)
            return []
