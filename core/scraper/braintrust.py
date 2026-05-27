
import os
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from .auth_handler import AsyncAuthHandler
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.braintrust")

BRAINTRUST_USER_DATA = os.path.join(os.getcwd(), "braintrust_user_data")
BRAINTRUST_LOGIN_URL = "https://app.usebraintrust.com/login"
BRAINTRUST_JOBS_URL = "https://app.usebraintrust.com/jobs"

class BraintrustScraper(BaseJobScraper):
    """Scrape jobs from Braintrust."""

    @staticmethod
    async def _is_logged_in(page) -> bool:
        """Check if logged in by URL or DOM."""
        url = page.url.lower()
        if any(k in url for k in ("login", "signin", "auth", "logout")):
            return False
        return "app.usebraintrust.com" in url and "/jobs" in url

    async def _launch_context(self, playwright, headless: bool):
        """Launch browser context for Braintrust."""
        return await get_async_browser_context(playwright, headless=headless, user_data_dir=BRAINTRUST_USER_DATA)

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Braintrust for jobs matching role."""
        logger.info("Braintrust search: role='%s' location='%s'", role, location)
        jobs = []

        try:
            async with async_playwright() as p:
                auth = AsyncAuthHandler(
                    platform="braintrust",
                    user_data_dir=BRAINTRUST_USER_DATA,
                    login_url=BRAINTRUST_LOGIN_URL,
                    check_fn=self._is_logged_in
                )
                context, page = await auth.authenticate(p, self._launch_context)
                if not context or not page:
                    logger.warning("Braintrust: Authentication failed")
                    return []
                
                # Braintrust search URL - using app subdomain to avoid 404s
                search_query = role.replace(" ", "%20")
                url = f"{BRAINTRUST_JOBS_URL}?q={search_query}"
                
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(3000) 
                
                links = await page.query_selector_all('a[href^="/jobs/"]')
                
                # Pre-extract data to avoid "execution context destroyed" errors
                link_data = []
                for link in links:
                    href = await link.get_attribute("href")
                    if not href or href == "/jobs/": continue
                    text = (await link.inner_text()).strip()
                    link_data.append({"href": href, "text": text})

                seen_ids = set()
                count = 0
                for data in link_data:
                    if count >= 20: break # Limit for performance
                    
                    href = data["href"]
                    job_id = href.split("/")[-1]
                    if not job_id or job_id == "jobs": continue
                    if job_id in seen_ids: continue
                    seen_ids.add(job_id)
                    
                    title = data["text"]
                    if not title or len(title) < 5: continue
                    
                    full_url = f"https://app.usebraintrust.com{href}"
                    
                    # Fetch detailed description
                    logger.info("Braintrust: Fetching details for %s", full_url)
                    description = ""
                    try:
                        detail_page = await context.new_page()
                        await detail_page.goto(full_url, wait_until="networkidle", timeout=30000)
                        
                        # Try to find description - using sanitized testid found in investigation
                        content_el = await detail_page.query_selector('[data-testid="sanitized"], div[class*="JobDetail"], main, article')
                        if content_el:
                            description = await content_el.inner_text()
                        
                        if not description:
                            description = await detail_page.inner_text('body')
                            
                        await detail_page.close()
                    except Exception as e:
                        logger.warning("Could not fetch Braintrust description for %s: %s", full_url, e)
                        description = f"Contractual role at Braintrust. Match: {role}"

                    job = Job(
                        id=job_id,
                        title=title,
                        company="Braintrust Client",
                        location="Remote",
                        application_url=full_url,
                        platform="Braintrust",
                        description=description[:5000],
                        date_found=datetime.now().isoformat()
                    )
                    jobs.append(job)
                    count += 1
                
                logger.info("Braintrust scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Braintrust scraping error: %s", e)
            
        return jobs
