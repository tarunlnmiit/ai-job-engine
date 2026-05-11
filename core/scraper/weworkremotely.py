import os
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

logger = get_logger("scraper.weworkremotely")

BASE_URL = "https://weworkremotely.com"


class WeWorkRemotely(BaseJobScraper):
    """Scrape jobs from WeWorkRemotely using Playwright to bypass Cloudflare."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("WeWorkRemotely search: role='%s'", role)
        
        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        jobs = []
        cdp_url = "http://localhost:9222"

        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=True)
                page = context.pages[0] if context.pages else context.new_page()

                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                    logger.info("Stealth mode enabled for WeWorkRemotely scraper")
                except ImportError:
                    pass

                # Instead of RSS which is hard to parse when redirected, we scrape the HTML search page.
                url = f"{BASE_URL}/remote-jobs/search?term={role.replace(' ', '+')}"
                logger.debug("Fetching WeWorkRemotely URL: %s", url)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Wait for Cloudflare
                    html_content = page.content()
                    if "Just a moment..." in page.title() or "cloudflare" in html_content.lower():
                        logger.info("Cloudflare detected on WeWorkRemotely. Waiting...")
                        try:
                            page.wait_for_function(
                                "() => !document.title.includes('Just a moment') && !document.body.innerText.toLowerCase().includes('cloudflare')",
                                timeout=120000
                            )
                            logger.info("Verification cleared!")
                            page.wait_for_timeout(2000)
                        except:
                            logger.warning("Cloudflare bypass timed out.")
                            
                    page.wait_for_timeout(random.uniform(2, 4) * 1000)
                except Exception as e:
                    logger.warning("Page load failed: %s", e)

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                
                # WWR jobs are listed under article > ul > li
                articles = soup.find_all("article")
                job_list_items = []
                for article in articles:
                    ul = article.find("ul")
                    if ul:
                        job_list_items.extend(ul.find_all("li", recursive=False))
                
                logger.debug("Found %d job list items on WWR", len(job_list_items))

                for item in job_list_items:
                    # Skip elements that are just "view all" buttons or similar non-job elements
                    if "view-all" in item.get("class", []):
                        continue
                        
                    title_elem = item.find(class_="title") or item.find(class_="new-listing__header__title")
                    company_elem = item.find(class_="company") or item.find(class_="new-listing__company-name")
                    
                    if not title_elem:
                        continue
                        
                    title = title_elem.get_text(strip=True)
                    company = company_elem.get_text(strip=True) if company_elem else "WeWorkRemotely"
                    
                    # WWR has location/region sometimes in '.region' or '.new-listing__company-headquarters'
                    loc_elem = item.find(class_="region") or item.find(class_="new-listing__company-headquarters")
                    job_location = loc_elem.get_text(strip=True) if loc_elem else "Remote"
                    if not job_location or job_location.lower() == "remote":
                        job_location = "Remote"
                    else:
                        job_location = f"Remote ({job_location})"
                        
                    # Find link
                    # Usually there are multiple links, the main job link is often the second one or the one with a specific class.
                    # Usually, the 'a' tag wrapping the content or the nearest 'a' tag.
                    link_elem = None
                    # Try to find a link that goes to /remote-jobs/
                    for a in item.find_all("a", href=True):
                        href = a["href"]
                        if "/remote-jobs/" in href and "search?" not in href:
                            link_elem = a
                            break
                    # If not found, just grab the last link
                    if not link_elem:
                        links = item.find_all("a", href=True)
                        if links:
                            link_elem = links[-1]

                    href = link_elem["href"] if link_elem else ""
                    if href.startswith("/"):
                        job_url = f"{BASE_URL}{href}"
                    else:
                        job_url = href

                    job_id = job_url.split("/")[-1].split("?")[0] if job_url else str(random.randint(1000, 9999))
                    
                    # Exclude obvious ads if we can, though some "feature" are just sponsored real jobs
                    # If it's a bootcamp ad it might not match role, but we'll include it and let the scorer filter it.

                    job = Job(
                        id=f"wwr_{job_id}",
                        title=title,
                        company=company,
                        location=job_location,
                        description="",  # We'd have to visit each page to get the full description, skip for now
                        skills_required=[],
                        platform="weworkremotely",
                        application_url=job_url,
                        is_easy_apply=False,
                        is_remote=True,
                        salary=None,
                        posted_date=None,
                        experience_required=None,
                        date_found=datetime.now().strftime("%Y-%m-%d"),
                    )
                    jobs.append(job)

                page.close()

        except Exception as e:
            logger.error("Error scraping WeWorkRemotely: %s", e, exc_info=True)

        logger.info("WeWorkRemotely scrape complete — %d jobs collected", len(jobs))
        return jobs
