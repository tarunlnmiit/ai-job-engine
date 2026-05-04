import os
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.lever")

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

# Verified working as of May 2026 (or known high-profile Lever users)
# Many companies use company.lever.co or jobs.lever.co/company
LEVER_COMPANIES = [
    "lever", "outreach", "paytm", "zoox", "rippling", 
    "coda", "figma", "linear", "vercel", "brex", 
    "notion", "airtable", "segment", "hashicorp",
    "palantir", "canva", "dbt", "sourcegraph", "postman"
]

class LeverScraper(BaseJobScraper):
    """Scrape jobs from Lever boards using Playwright (Synchronous)."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search Lever boards for jobs."""
        logger.info("Lever search: role='%s' — checking %d companies", role, len(LEVER_COMPANIES))
        
        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        all_jobs = []
        cdp_url = "http://localhost:9222"

        try:
            with sync_playwright() as p:
                browser = None
                try:
                    # Attempt to connect to existing chrome first
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    logger.info("Lever: Connected to existing Chrome via CDP")
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                except Exception as e:
                    logger.warning("Lever: CDP connect failed (%s) — launching persistent context", e)
                    user_data_dir = os.path.join(os.getcwd(), "data", "browser_session")
                    os.makedirs(user_data_dir, exist_ok=True)
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        headless=True
                    )

                for company in LEVER_COMPANIES:
                    company_jobs = self._scrape_company(context, company, role, location)
                    all_jobs.extend(company_jobs)
                    logger.debug("Lever: Finished %s, total jobs: %d", company, len(all_jobs))

                if browser:
                    browser.close()
                else:
                    context.close()

        except Exception as e:
            logger.error("Lever scraper fatal error: %s", e)

        logger.info("Lever scrape complete — %d jobs found", len(all_jobs))
        return all_jobs

    def _scrape_company(self, context, company: str, role: str, location_filter: str = None) -> list[Job]:
        jobs = []
        url = f"https://jobs.lever.co/{company}"
        page = context.new_page()
        
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except ImportError:
            pass

        try:
            logger.debug("Lever: Visiting %s", url)
            response = page.goto(url, wait_until="networkidle", timeout=30000)
            
            if response and response.status == 404:
                logger.warning("Lever: Board for '%s' returned 404. Removing from list or skipping.", company)
                return []
            
            # Wait for content or no-postings
            try:
                page.wait_for_selector(".posting, .no-postings-message", timeout=5000)
            except:
                pass

            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            posting_divs = soup.select("div.posting")
            for div in posting_divs:
                title_elem = div.select_one("h5[data-qa='posting-name']")
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                
                # Role filter
                if role.lower() not in title.lower():
                    continue

                link_elem = div.select_one("a.posting-title")
                apply_url = link_elem['href'] if link_elem else url

                # Categories
                categories_div = div.select_one(".posting-categories")
                location_text = "Remote"
                is_remote = False
                
                if categories_div:
                    loc_elem = categories_div.select_one(".location")
                    if loc_elem:
                        location_text = loc_elem.get_text(strip=True)
                    
                    workplace_elem = categories_div.select_one(".workplaceTypes")
                    if workplace_elem and "remote" in workplace_elem.get_text().lower():
                        is_remote = True
                    elif "remote" in location_text.lower():
                        is_remote = True

                # Location filter
                if location_filter and location_filter.lower() not in ("remote", "anywhere"):
                    if location_filter.lower() not in location_text.lower() and not is_remote:
                        continue

                job = Job(
                    id=f"lever_{div.get('data-qa-posting-id', apply_url.split('/')[-1])}",
                    title=title,
                    company=company.title(),
                    location=location_text,
                    description=f"Job at {company.title()}. Apply via Lever.",
                    skills_required=[],
                    platform="lever",
                    application_url=apply_url,
                    is_easy_apply=False,
                    is_remote=is_remote,
                    salary=None,
                    posted_date=None,
                    experience_required=None,
                    date_found=datetime.now().strftime("%Y-%m-%d"),
                )
                jobs.append(job)

        except Exception as e:
            logger.warning("Lever: Error scraping %s: %s", company, e)
        finally:
            page.close()
        
        return jobs
