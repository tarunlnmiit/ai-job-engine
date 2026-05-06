
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.andela")

class AndelaScraper(BaseJobScraper):
    """Scrape jobs from Andela."""

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Andela for jobs matching role."""
        logger.info("Andela search: role='%s'", role)
        jobs = []
        
        try:
            async with async_playwright() as p:
                context = await get_async_browser_context(p, headless=True)
                page = await context.new_page()
                
                # Andela public jobs page
                url = "https://andela.com/careers/"
                
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(5000)
                
                links = await page.query_selector_all('a[href*="job"]')
                
                # Pre-extract to avoid context destroyed
                link_data = []
                for link in links:
                    try:
                        text = (await link.inner_text()).strip()
                        href = await link.get_attribute("href")
                        if href and text:
                            link_data.append({"href": href, "text": text})
                    except: continue

                seen_urls = set()
                for data in link_data:
                    href = data["href"]
                    text = data["text"]
                    
                    if len(text) < 5: continue
                    
                    full_url = href if href.startswith("http") else f"https://andela.com{href}"
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)
                    
                    job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                    
                    job = Job(
                        id=job_id,
                        title=text,
                        company="Andela",
                        location="Remote",
                        application_url=full_url,
                        platform="Andela",
                        description=f"Remote role at Andela. Match: {role}",
                        date_found=datetime.now().isoformat()
                    )
                    jobs.append(job)
                
                logger.info("Andela scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Andela scraping error: %s", e)
            
        return jobs
