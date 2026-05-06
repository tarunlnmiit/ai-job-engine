
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.uplers")

class UplersScraper(BaseJobScraper):
    """Scrape jobs from Uplers."""

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Uplers for jobs matching role."""
        logger.info("Uplers search: role='%s'", role)
        jobs = []
        
        try:
            async with async_playwright() as p:
                context = await get_async_browser_context(p, headless=True)
                page = await context.new_page()
                
                # Uplers jobs page
                url = f"https://www.uplers.com/talent/jobs/?job_title={role.replace(' ', '+')}"
                
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(5000)
                
                cards = await page.query_selector_all(".job-card, .job-listing-item")
                if not cards:
                    cards = await page.query_selector_all('a[href*="/jobs/"]')
                
                # Pre-extract to avoid context destroyed
                card_data = []
                for card in cards:
                    try:
                        href = await card.get_attribute("href")
                        if not href:
                            link_el = await card.query_selector("a")
                            if link_el: href = await link_el.get_attribute("href")
                        
                        text = (await card.inner_text()).split("\n")[0].strip()
                        if href and text:
                            card_data.append({"href": href, "text": text})
                    except: continue

                seen_urls = set()
                for data in card_data:
                    href = data["href"]
                    if "/jobs/" not in href or href.endswith("/jobs/"): continue
                    
                    full_url = href if href.startswith("http") else f"https://www.uplers.com{href}"
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)
                    
                    title = data["text"]
                    if not title or len(title) < 5: continue
                    
                    job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                    
                    job = Job(
                        id=job_id,
                        title=title,
                        company="Uplers Client",
                        location="Remote",
                        application_url=full_url,
                        platform="Uplers",
                        description=f"Contractual role at Uplers. Match: {role}",
                        date_found=datetime.now().isoformat()
                    )
                    jobs.append(job)
                
                logger.info("Uplers scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Uplers scraping error: %s", e)
            
        return jobs
