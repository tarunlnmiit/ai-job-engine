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

logger = get_logger("scraper.arbeitnow")

class ArbeitNowScraper(BaseJobScraper):
    """Scrape jobs from ArbeitNow using Playwright."""
    _role_cache = {}  # Class-level cache for {role: [Job, Job, ...]}
    _cache_time = {} # {role: datetime}

    def search(self, role: str, location: str = "Germany", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching ArbeitNow: role=%r location=%r", role, location)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        # 1. Check cache first
        now = datetime.now()
        cache_hit = False
        if role in self._role_cache:
            last_scraped = self._cache_time.get(role)
            # Cache is valid for 10 minutes
            if last_scraped and (now - last_scraped).total_seconds() < 600:
                logger.info("⚡ Cache hit for role '%s' on ArbeitNow", role)
                cache_hit = True
        
        if cache_hit:
            all_jobs = self._role_cache[role]
        else:
            # 2. Perform global scrape for the role
            all_jobs = self._search_playwright(role, location, max_pages)
            self._role_cache[role] = all_jobs
            self._cache_time[role] = now

        # 3. Filter by location in memory
        filtered_jobs = []
        for job in all_jobs:
            if not location or location.lower() in ("remote", "any", "germany"):
                filtered_jobs.append(job)
                continue
                
            if location.lower() in job.location.lower() or \
               location.lower() in job.title.lower():
                filtered_jobs.append(job)

        logger.info("ArbeitNow search complete: %d jobs matched from %d total for role", len(filtered_jobs), len(all_jobs))
        return filtered_jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        if not BS_AVAILABLE:
            return []

        jobs = []
        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=True)
                page = context.new_page()

                # URL format: https://www.arbeitnow.com/jobs?query={role}&location={location}&visa=1
                # Or use the specific visa sponsorship page
                search_query = role.replace(" ", "+")
                
                if location and location.lower() not in ["germany", "remote", "any"]:
                    loc_slug = location.lower().replace(" ", "-")
                    url = f"https://www.arbeitnow.com/jobs/{loc_slug}?query={search_query}&visa=1"
                else:
                    url = f"https://www.arbeitnow.com/jobs?query={search_query}&visa=1"
                
                logger.info("Navigating to %s", url)
                page.bring_to_front()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for job listings
                try:
                    page.wait_for_selector("li[id^='job-'], .job-card, .job-board-card", timeout=20000)
                except:
                    # Alternative selector
                    try:
                        page.wait_for_selector("a[href*='/jobs/companies/']", timeout=5000)
                    except:
                        logger.warning("Job cards not found on ArbeitNow.")
                        return []

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                
                # Job cards are usually <li> or <div> with specific classes
                cards = soup.select("li[id^='job-']") or soup.select(".job-card")
                if not cards:
                    # Try to find by link pattern
                    cards = soup.select("h2 a[href*='/jobs/companies/']")
                    # If we found just the title links, we need to go to parents
                    cards = [c.find_parent("li") or c.find_parent("div") for c in cards if c]

                # To get full descriptions, we need to visit each job page
                # We limit this to the first 25 jobs to avoid excessive time/rate limits
                final_jobs = []
                for i, card in enumerate(cards[:25]):
                    if not card: continue
                    try:
                        title_elem = card.select_one("h2")
                        if not title_elem: continue
                        
                        title = title_elem.get_text(strip=True)
                        link_elem = title_elem.select_one("a")
                        if not link_elem: continue
                        
                        href = link_elem["href"]
                        if not href.startswith("http"):
                            href = "https://www.arbeitnow.com" + href
                            
                        company = "Unknown"
                        comp_elem = card.select_one("a[href*='/jobs/companies/']")
                        if comp_elem:
                            company = comp_elem.get_text(strip=True)
                            
                        job_location = location or "Germany"
                        loc_elem = card.select_one(".location") or card.select_one("div.flex.items-center.text-gray-500.text-xs")
                        if loc_elem:
                            job_location = loc_elem.get_text(strip=True)

                        job_id = hashlib.md5(href.encode()).hexdigest()

                        # FETCH FULL DESCRIPTION
                        description = ""
                        try:
                            logger.info("Fetching full description for job %d: %s", i+1, title)
                            detail_page = context.new_page()
                            detail_page.goto(href, wait_until="domcontentloaded", timeout=30000)
                            
                            # ArbeitNow description is usually in a div with specific classes
                            desc_elem = detail_page.locator("#job-description, .job-description, .prose").first
                            if desc_elem.is_visible():
                                description = desc_elem.inner_text()
                            else:
                                # Fallback to body content if specific selector fails
                                description = detail_page.locator("body").inner_text()[:3000]
                            
                            detail_page.close()
                        except Exception as desc_e:
                            logger.warning("Could not fetch detail for %s: %s", href, desc_e)
                            description = "Includes Visa Sponsorship. Full description fetch failed."

                        job = Job(
                            id=job_id,
                            title=title,
                            company=company,
                            location=job_location,
                            description=description,
                            application_url=href,
                            platform="ArbeitNow",
                            date_found=datetime.now().isoformat()
                        )
                        final_jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing ArbeitNow card: %s", e)
                        continue

                page.close()
                return final_jobs

        except Exception as e:
            logger.error("ArbeitNow scraping error: %s", e)
            return []
