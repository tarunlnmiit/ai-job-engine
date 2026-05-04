import os
import random
from datetime import datetime
from dotenv import load_dotenv
from .base import BaseJobScraper, Job
from logger import get_logger

load_dotenv()
logger = get_logger("scraper.naukri")

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


class NaukriScraper(BaseJobScraper):
    """Scrape jobs from Naukri.com via Playwright (no login required for search results)."""

    BASE_URL = "https://www.naukri.com"

    def search(self, role: str, location: str = "india", experience: int = 3, max_pages: int = 1, **kwargs) -> list[Job]:
        """Search Naukri for jobs using Playwright to render the React SPA."""
        logger.info("Naukri search: role='%s' location='%s' experience=%d max_pages=%d", role, location, experience, max_pages)

        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        return self._search_playwright(role, location, experience, max_pages)

    def _search_playwright(self, role: str, location: str, experience: int, max_pages: int) -> list[Job]:
        """Scrape Naukri search results using Playwright."""
        jobs = []
        cdp_url = "http://localhost:9222"

        try:
            with sync_playwright() as p:
                owned_browser = False
                browser = None
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    logger.info("Connected to existing Chrome via CDP at %s", cdp_url)
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                    page = context.new_page()
                except Exception as e:
                    logger.debug("CDP connect failed (%s) — launching persistent context browser", e)
                    user_data_dir = os.path.join(os.getcwd(), "data", "browser_session")
                    os.makedirs(user_data_dir, exist_ok=True)

                    browser_context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        headless=False,
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        locale="en-US",
                        viewport={"width": 1280, "height": 800},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-infobars",
                        ],
                        ignore_default_args=["--enable-automation"],
                    )
                    owned_browser = True
                    page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()

                    try:
                        from playwright_stealth import stealth_sync
                        stealth_sync(page)
                        logger.info("Stealth mode enabled for Naukri scraper")
                    except ImportError:
                        pass

                for pg in range(1, max_pages + 1):
                    # Naukri SRP URL format: /python-jobs?k=python&l=india&experience=3&nignbevent_src=jobsearchDesk
                    role_slug = role.lower().replace(" ", "-")
                    url = f"{self.BASE_URL}/{role_slug}-jobs?k={role.replace(' ', '%20')}&l={location.replace(' ', '%20')}&experience={experience}"
                    if pg > 1:
                        url += f"&start={20 * (pg - 1)}"

                    logger.debug("Fetching Naukri URL (page %d): %s", pg, url)

                    try:
                        # networkidle ensures React SPA has fully rendered
                        page.goto(url, wait_until="networkidle", timeout=60000)
                        page.wait_for_timeout(random.uniform(2, 3) * 1000)
                    except Exception as e:
                        logger.warning("Page load failed on page %d: %s", pg, e)
                        continue

                    # Wait for job cards to appear
                    try:
                        page.wait_for_selector("div.srp-jobtuple-wrapper", timeout=15000)
                    except Exception:
                        logger.warning("No job cards (div.srp-jobtuple-wrapper) found on Naukri page %d", pg)
                        break

                    html = page.content()
                    page_jobs = self._parse_html(html, location)
                    logger.info("Naukri page %d: found %d jobs", pg, len(page_jobs))

                    if not page_jobs:
                        break
                    jobs.extend(page_jobs)

                if owned_browser:
                    if "browser_context" in locals():
                        browser_context.close()
                    elif browser:
                        browser.close()
                else:
                    page.close()

        except Exception as e:
            logger.error("Playwright Naukri scrape failed: %s", e, exc_info=True)

        logger.info("Naukri scrape complete — %d jobs collected", len(jobs))
        return jobs

    def _parse_html(self, html: str, fallback_location: str) -> list[Job]:
        """Parse Naukri SRP HTML and return Job objects."""
        soup = BeautifulSoup(html, "html.parser")
        job_cards = soup.find_all("div", class_="srp-jobtuple-wrapper")
        logger.debug("Naukri parser: found %d job cards", len(job_cards))

        jobs = []
        for card in job_cards:
            try:
                job = self._parse_card(card, fallback_location)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.warning("Error parsing Naukri card: %s", e)
                continue

        return jobs

    def _parse_card(self, card, fallback_location: str):
        job_id = card.get("data-job-id", "")

        # Title + URL
        title_elem = card.select_one("h2 a.title")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)
        job_url = title_elem.get("href", "")

        # Company
        company_elem = card.select_one("a.comp-name")
        company = company_elem.get_text(strip=True) if company_elem else "Unknown"

        # Location (may have multiple cities)
        loc_elems = card.select("span.locWdth")
        if loc_elems:
            location_text = ", ".join(e.get_text(strip=True) for e in loc_elems)
        else:
            location_text = fallback_location

        # Experience
        exp_elem = card.select_one("span.expwdth")
        experience = exp_elem.get_text(strip=True) if exp_elem else None

        # Skills / tags
        tag_items = card.select("ul.tags-gt li.tag-li")
        skills = [li.get_text(strip=True) for li in tag_items]

        # Description snippet
        desc_elem = card.select_one("span.job-desc")
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        if skills:
            description += " | Skills: " + ", ".join(skills)

        # Posted date
        date_elem = card.select_one("span.job-post-day")
        posted_date = date_elem.get_text(strip=True) if date_elem else None

        is_remote = any(
            kw in location_text.lower() for kw in ("remote", "work from home", "wfh")
        )

        return Job(
            id=f"naukri_{job_id}",
            title=title,
            company=company,
            location=location_text,
            description=description,
            skills_required=skills,
            platform="naukri",
            application_url=job_url,
            is_easy_apply=False,
            is_remote=is_remote,
            salary=None,
            posted_date=posted_date,
            experience_required=experience,
            date_found=datetime.now().strftime("%Y-%m-%d"),
        )
