
import os
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from .auth_handler import AsyncAuthHandler
from logger import get_logger
from .browser_utils import get_async_browser_context
from playwright.async_api import async_playwright

logger = get_logger("scraper.arc_dev")

ARC_DEV_USER_DATA = os.path.join(os.getcwd(), "arc_dev_user_data")
ARC_DEV_LOGIN_URL = "https://arc.dev/login"
ARC_DEV_JOBS_URL = "https://arc.dev/remote-jobs"

class ArcDevScraper(BaseJobScraper):
    """Scrape jobs from Arc.dev."""

    @staticmethod
    async def _is_logged_in(page) -> bool:
        """Check if logged in by URL or DOM."""
        url = page.url.lower()
        if any(k in url for k in ("login", "signin", "auth", "logout")):
            return False
        return "arc.dev" in url and "remote-jobs" in url

    async def _launch_context(self, playwright, headless: bool):
        """Launch browser context for Arc.dev."""
        return await get_async_browser_context(playwright, headless=headless, user_data_dir=ARC_DEV_USER_DATA)

    async def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Arc.dev for jobs matching role."""
        logger.info("Arc.dev search: role='%s'", role)
        jobs = []

        try:
            async with async_playwright() as p:
                auth = AsyncAuthHandler(
                    platform="arc_dev",
                    user_data_dir=ARC_DEV_USER_DATA,
                    login_url=ARC_DEV_LOGIN_URL,
                    check_fn=self._is_logged_in
                )
                context, page = await auth.authenticate(p, self._launch_context)
                if not context or not page:
                    logger.warning("Arc.dev: Authentication failed")
                    return []
                
                # Arc.dev search URL
                search_query = role.replace(" ", "+")
                url = f"{ARC_DEV_JOBS_URL}?q={search_query}"
                
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
                count = 0
                for data in link_data:
                    if count >= 20: break # Limit for performance
                    
                    href = data["href"]
                    if "/remote-jobs/details/" not in href and "/remote-jobs/j/" not in href: continue
                    
                    full_url = href if href.startswith("http") else f"https://arc.dev{href}"
                    if full_url in seen_urls: continue
                    seen_urls.add(full_url)
                    
                    title = data["text"]
                    if not title or len(title) < 5: continue
                    
                    job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                    
                    # Fetch detailed description
                    logger.info("Arc.dev: Fetching details for %s", full_url)
                    description = ""
                    try:
                        detail_page = await context.new_page()
                        await detail_page.goto(full_url, wait_until="networkidle", timeout=30000)
                        
                        # Arc.dev usually has descriptions in a specific container
                        content_el = await detail_page.query_selector('div[class*="JobDetails"], div[class*="Description"], main')
                        if content_el:
                            description = await content_el.inner_text()
                        
                        if not description:
                            description = await detail_page.inner_text('body')
                            
                        await detail_page.close()
                    except Exception as e:
                        logger.warning("Could not fetch Arc.dev description for %s: %s", full_url, e)
                        description = f"Remote contractual role at Arc.dev. Match: {role}"

                    job = Job(
                        id=job_id,
                        title=title,
                        company="Arc.dev Client",
                        location="Remote",
                        application_url=full_url,
                        platform="Arc.dev",
                        description=description[:5000],
                        date_found=datetime.now().isoformat()
                    )
                    jobs.append(job)
                    count += 1
                
                logger.info("Arc.dev scrape complete — %d jobs found", len(jobs))
                
        except Exception as e:
            logger.error("Arc.dev scraping error: %s", e)
            
        return jobs
