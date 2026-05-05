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

    def search(self, role: str, location: str = "Germany", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching ArbeitNow: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("ArbeitNow search complete: %d jobs found", len(jobs))
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

                for card in cards:
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
                        # Company is often in a link with /companies/
                        comp_elem = card.select_one("a[href*='/jobs/companies/']")
                        if comp_elem:
                            company = comp_elem.get_text(strip=True)
                        elif "by" in card.get_text():
                            # Fallback parsing
                            text = card.get_text()
                            if "by" in text:
                                company = text.split("by")[1].split("\n")[0].strip()
                            
                        job_location = location or "Germany" # Default for ArbeitNow
                        # Location is often near a pin icon or specific class
                        loc_elem = card.select_one(".location") or card.select_one("div.flex.items-center.text-gray-500.text-xs") or card.select_one("span:has(svg)")
                        if loc_elem:
                            job_location = loc_elem.get_text(strip=True)

                        job_id = hashlib.md5(href.encode()).hexdigest()

                        # Check for tags like "visa sponsorship"
                        description = "Includes Visa Sponsorship"
                        tags = [t.get_text(strip=True) for t in card.select(".tag")]
                        if tags:
                            description += f". Tags: {', '.join(tags)}"

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
                        jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing ArbeitNow card: %s", e)
                        continue

                page.close()
                return jobs

        except Exception as e:
            logger.error("ArbeitNow scraping error: %s", e)
            return []
