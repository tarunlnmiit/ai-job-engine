
import os
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from .auth_handler import AsyncAuthHandler
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.mercor")

MERCOR_USER_DATA = os.path.join(os.getcwd(), "mercor_user_data")
MERCOR_LOGIN_URL = "https://mercor.com/login"
MERCOR_HOME_URL = "https://mercor.com"

class MercorScraper(BaseJobScraper):
    """Scrape jobs from Mercor."""

    @staticmethod
    async def _is_logged_in(page) -> bool:
        """Check if logged in by URL or DOM."""
        url = page.url.lower()
        if any(k in url for k in ("login", "signin", "auth", "logout")):
            return False
        return "mercor.com" in url

    async def _launch_context(self, playwright, headless: bool):
        """Launch browser context for Mercor."""
        return await get_async_browser_context(playwright, headless=headless, user_data_dir=MERCOR_USER_DATA)

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Mercor for jobs matching role."""
        logger.info("Mercor search: role='%s'", role)
        jobs = []

        try:
            async with async_playwright() as p:
                auth = AsyncAuthHandler(
                    platform="mercor",
                    user_data_dir=MERCOR_USER_DATA,
                    login_url=MERCOR_LOGIN_URL,
                    check_fn=self._is_logged_in
                )
                context, page = await auth.authenticate(p, self._launch_context)
                if not context or not page:
                    logger.warning("Mercor: Authentication failed")
                    return []

                # Mercor landing
                url = MERCOR_HOME_URL
                
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
                    
                    full_url = href if href.startswith("http") else f"https://mercor.com{href}"
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)
                    
                    job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                    
                    # Fetch detailed description
                    logger.info("Mercor: Fetching details for %s", full_url)
                    description = ""
                    try:
                        detail_page = await context.new_page()
                        await detail_page.goto(full_url, wait_until="networkidle", timeout=30000)
                        
                        # Try to find description in schema.org or specific divs
                        desc_handle = await detail_page.query_selector('script[type="application/ld+json"]')
                        if desc_handle:
                            try:
                                import json
                                ld_data = json.loads(await desc_handle.inner_text())
                                if isinstance(ld_data, dict):
                                    description = ld_data.get("description", "")
                                elif isinstance(ld_data, list):
                                    for item in ld_data:
                                        if item.get("@type") == "JobPosting":
                                            description = item.get("description", "")
                                            break
                            except: pass
                            
                        if not description:
                            # Fallback to main content area
                            content_el = await detail_page.query_selector('main, article, .job-description')
                            if content_el:
                                description = await content_el.inner_text()
                        
                        if not description:
                            description = await detail_page.inner_text('body')
                            
                        await detail_page.close()
                    except Exception as e:
                        logger.warning("Could not fetch Mercor description for %s: %s", full_url, e)
                        description = f"Remote contractual role via Mercor AI. Match: {role}"

                    job = Job(
                        id=job_id,
                        title=text,
                        company="Mercor",
                        location="Remote",
                        application_url=full_url,
                        platform="Mercor",
                        description=description[:5000], # Cap length
                        date_found=datetime.now().isoformat()
                    )
                    jobs.append(job)
                
                logger.info("Mercor scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Mercor scraping error: %s", e)
            
        return jobs
