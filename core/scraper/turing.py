
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.turing")

class TuringScraper(BaseJobScraper):
    """Scrape jobs from Turing."""

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Turing for jobs matching role."""
        logger.info("Turing search: role='%s'", role)
        jobs = []
        
        try:
            async with async_playwright() as p:
                context = await get_async_browser_context(p, headless=True)
                page = await context.new_page()
                
                # Turing search URL
                url = "https://www.turing.com/jobs"
                
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(5000)
                
                elements = await page.query_selector_all('a')
                
                # Pre-extract to avoid context destroyed
                link_data = []
                for el in elements:
                    try:
                        text = (await el.inner_text()).strip()
                        href = await el.get_attribute("href")
                        if href and text:
                            link_data.append({"href": href, "text": text})
                    except: continue

                seen_urls = set()
                for data in link_data:
                    href = data["href"]
                    text = data["text"]
                    
                    if "/jobs/" in href and any(keyword in text.lower() for keyword in [role.lower(), "engineer", "developer", "scientist", "analyst"]):
                        
                        full_url = href if href.startswith("http") else f"https://www.turing.com{href}"
                        if full_url in seen_urls: continue
                        seen_urls.add(full_url)
                        
                        job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                        
                        job = Job(
                            id=job_id,
                            title=text,
                            company="Turing",
                            location="Remote",
                            application_url=full_url,
                            platform="Turing",
                            description=f"Remote contractual role at Turing. Match: {role}",
                            date_found=datetime.now().isoformat()
                        )
                        jobs.append(job)
                
                logger.info("Turing scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Turing scraping error: %s", e)
            
        return jobs
