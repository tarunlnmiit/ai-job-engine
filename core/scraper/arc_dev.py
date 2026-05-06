
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.arc_dev")

class ArcDevScraper(BaseJobScraper):
    """Scrape jobs from Arc.dev."""

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Arc.dev for jobs matching role."""
        logger.info("Arc.dev search: role='%s'", role)
        jobs = []
        
        try:
            async with async_playwright() as p:
                context = await get_async_browser_context(p, headless=True)
                page = await context.new_page()
                
                # Arc.dev search URL
                search_query = role.replace(" ", "+")
                url = f"https://arc.dev/remote-jobs?q={search_query}"
                
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(5000)
                
                links = await page.query_selector_all('a[href*="/remote-jobs/"]')
                
                # Pre-extract to avoid context destroyed
                link_data = []
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        text = (await link.inner_text()).strip()
                        if href and text:
                            link_data.append({"href": href, "text": text})
                    except: continue

                seen_urls = set()
                for data in link_data:
                    href = data["href"]
                    if "/remote-jobs/search" in href or href == "/remote-jobs/": continue
                    
                    full_url = href if href.startswith("http") else f"https://arc.dev{href}"
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)
                    
                    title = data["text"]
                    if not title or len(title) < 5: continue
                    
                    job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                    
                    job = Job(
                        id=job_id,
                        title=title,
                        company="Arc.dev Client",
                        location="Remote",
                        application_url=full_url,
                        platform="Arc.dev",
                        description=f"Remote contractual role at Arc.dev. Match: {role}",
                        date_found=datetime.now().isoformat()
                    )
                    jobs.append(job)
                
                logger.info("Arc.dev scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Arc.dev scraping error: %s", e)
            
        return jobs
