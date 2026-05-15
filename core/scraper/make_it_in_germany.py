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

logger = get_logger("scraper.make_it_in_germany")

class MakeItInGermanyScraper(BaseJobScraper):
    """Scrape jobs from Make it in Germany (official German job portal)."""

    def search(self, role: str, location: str = "Germany", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching Make it in Germany: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("Make it in Germany search complete: %d jobs found", len(jobs))
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

                url = "https://www.make-it-in-germany.com/en/working-in-germany/job-listings"
                logger.info("Navigating to %s", url)
                page.goto(url, wait_until="load", timeout=60000)
                page.wait_for_timeout(3000)

                # Wait for job listings to load
                try:
                    page.wait_for_selector(".job-listing, .job-item, .job-card, [data-testid*='job']", timeout=20000)
                except:
                    logger.warning("Job listings not found on Make it in Germany.")
                    return []

                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")

                # Find job items - try multiple selectors
                job_items = (
                    soup.select(".job-listing") or
                    soup.select(".job-item") or
                    soup.select(".job-card") or
                    soup.select("[data-testid*='job']") or
                    soup.select("article.job")
                )

                for item in job_items:
                    try:
                        # Try to find title and link
                        title_elem = item.select_one("a[href*='/job/'], h2 a, h3 a, .job-title a")
                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)
                        href = title_elem.get("href", "")
                        if not href.startswith("http"):
                            href = "https://www.make-it-in-germany.com" + href

                        job_id = hashlib.md5(href.encode()).hexdigest()

                        # Extract company
                        company_elem = item.select_one(".company, .employer, [data-testid*='company']")
                        company = company_elem.get_text(strip=True) if company_elem else "Unknown"

                        # Extract location
                        location_elem = item.select_one(".location, .city, [data-testid*='location']")
                        job_location = location_elem.get_text(strip=True) if location_elem else "Germany"

                        # Location filter
                        if location and location.lower() not in ("remote", "anywhere", "germany"):
                            if location.lower() not in job_location.lower():
                                continue

                        # FETCH FULL DESCRIPTION
                        description = ""
                        try:
                            logger.info("Fetching Make it in Germany detail: %s", title)
                            detail_page = context.new_page()
                            detail_page.goto(href, wait_until="domcontentloaded", timeout=30000)
                            
                            desc_elem = detail_page.locator(".job-description, .description, main, body").first
                            if desc_elem.is_visible():
                                description = desc_elem.inner_text()[:5000]
                            else:
                                description = detail_page.locator("body").inner_text()[:5000]
                            
                            detail_page.close()
                        except Exception as desc_e:
                            logger.warning("Could not fetch detail for %s: %s", href, desc_e)
                            desc_elem = item.select_one(".description, .job-description, p")
                            description = desc_elem.get_text(strip=True) if desc_elem else f"Job opportunity in {job_location}"

                        job = Job(
                            id=job_id,
                            title=title,
                            company=company,
                            location=job_location,
                            description=description,
                            application_url=href,
                            platform="Make it in Germany",
                            date_found=datetime.now().isoformat()
                        )
                        jobs.append(job)
                    except Exception as e:
                        logger.error("Error parsing Make it in Germany job item: %s", e)
                        continue

                page.close()
                unique_jobs = {j.id: j for j in jobs}.values()
                return list(unique_jobs)

        except Exception as e:
            logger.error("Make it in Germany scraping error: %s", e)
            return []
