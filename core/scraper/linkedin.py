import os
import random
import time
from datetime import datetime
from dotenv import load_dotenv
from .base import BaseJobScraper, Job
from logger import get_logger

load_dotenv()

logger = get_logger("scraper.linkedin")

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

# Persistent user data directory — cookies survive across runs
CHROME_USER_DATA = os.path.join(os.getcwd(), "chrome_user_data")
# Max seconds to wait for manual CAPTCHA solve in visible mode
CHALLENGE_TIMEOUT = 300


class LinkedInScraper(BaseJobScraper):
    """Scrape LinkedIn jobs with fully integrated auth.

    Auth flow:
      1. Launch headless with persistent profile (chrome_user_data).
         If cookies are fresh, no login needed.
      2. If login wall detected → auto-fill credentials headlessly.
      3. If CAPTCHA / checkpoint challenge → close headless browser,
         relaunch in VISIBLE mode so user can solve it.
         Polls until challenge cleared (up to CHALLENGE_TIMEOUT seconds).
      4. Cookies are saved in chrome_user_data, so next run is headless again.
    """

    BASE_URL = "https://www.linkedin.com"

    def __init__(self):
        self.email = os.getenv("LINKEDIN_EMAIL")
        self.password = os.getenv("LINKEDIN_PASSWORD")

    # ── Auth helpers ─────────────────────────────────────────────────

    @staticmethod
    def _is_login_wall(page) -> bool:
        """Check if we're stuck on a login page."""
        url = page.url.lower()
        if "login" in url or "authwall" in url:
            return True
        if page.locator("input[name='session_key']").count() > 0:
            return True
        return False

    @staticmethod
    def _is_challenge(page) -> bool:
        """Check if LinkedIn is showing a CAPTCHA / security checkpoint."""
        url = page.url.lower()
        return any(k in url for k in ("checkpoint", "challenge", "security-verification"))

    @staticmethod
    def _is_logged_in(page) -> bool:
        """Check if we landed on an authenticated LinkedIn page."""
        url = page.url.lower()
        return any(k in url for k in ("feed", "jobs", "mynetwork", "messaging", "in/"))

    def _fill_login_form(self, page) -> None:
        """Fill and submit the LinkedIn login form."""
        # Email
        page.locator("input#username, input[name='session_key']").first.fill(self.email)

        # Password
        page.locator("input#password, input[name='session_password']").first.fill(self.password)

        # Submit
        page.locator("button[type='submit'], button[aria-label='Sign in']").first.click()
        page.wait_for_timeout(5000)

    def _launch_context(self, playwright, headless: bool):
        """Launch a persistent Chromium context that stores cookies."""
        return playwright.chromium.launch_persistent_context(
            CHROME_USER_DATA,
            headless=headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900} if not headless else None,
        )

    def _ensure_authenticated(self, playwright, search_url: str):
        """Ensure we have an authenticated LinkedIn page. Returns (context, page).

        Auth flow:
          Stage 1 — headless with saved cookies (fast path)
          Stage 2 — visible browser for login + CAPTCHA handling
                    (LinkedIn blocks headless on their login page)
        """
        if not self.email or not self.password:
            logger.error("LinkedIn: LINKEDIN_EMAIL / LINKEDIN_PASSWORD not set in .env")
            return None, None

        # ── Stage 1: Try headless with existing cookies ──────────────
        logger.info("LinkedIn Auth [Stage 1]: Headless with saved cookies...")
        context = self._launch_context(playwright, headless=True)
        page = context.new_page()
        
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except ImportError:
            pass
            
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if not self._is_login_wall(page):
            logger.info("LinkedIn Auth: ✅ Cookies valid — already logged in!")
            return context, page

        # ── Stage 2: Visible browser login ───────────────────────────
        # LinkedIn blocks headless Chrome on their login page, so we go
        # straight to visible mode. Once logged in, cookies are saved in
        # chrome_user_data so future runs hit Stage 1 and skip login.
        logger.info("LinkedIn Auth [Stage 2]: Opening VISIBLE browser for login as %s...", self.email)
        page.close()
        context.close()

        context = self._launch_context(playwright, headless=False)
        page = context.new_page()
        
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except ImportError:
            pass
            
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)

        # Wait for login form to actually appear
        try:
            page.wait_for_selector("input#username, input[name='session_key']", timeout=30000)
            page.wait_for_timeout(2000)
            self._fill_login_form(page)
        except Exception as e:
            logger.error("LinkedIn Auth: Visible login form fill failed: %s", e)
            # Don't abort — user can still manually type credentials
            logger.warning("LinkedIn Auth: You can manually type credentials in the browser window.")

        # Poll until login succeeds or challenge is solved
        logger.info(
            "🔔 LinkedIn: Waiting for login to complete (solve CAPTCHA if one appears). "
            "Timeout: %d seconds...", CHALLENGE_TIMEOUT
        )
        deadline = time.time() + CHALLENGE_TIMEOUT
        solved = False
        last_log = 0
        while time.time() < deadline:
            remaining = int(deadline - time.time())
            now = int(time.time())
            if now - last_log >= 10:
                logger.info("LinkedIn Auth: ⏳ Waiting... %ds remaining", remaining)
                last_log = now

            if self._is_logged_in(page):
                solved = True
                break

            if not self._is_challenge(page) and not self._is_login_wall(page):
                solved = True
                break

            page.wait_for_timeout(2000)

        if not solved:
            logger.error("LinkedIn Auth: ❌ Login not completed within %ds. Aborting.", CHALLENGE_TIMEOUT)
            page.close()
            context.close()
            return None, None

        logger.info("LinkedIn Auth: ✅ Logged in! Cookies saved to %s", CHROME_USER_DATA)

        # Navigate to search
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        return context, page

    # ── Main search ──────────────────────────────────────────────────

    def search(self, role: str, location: str = "United States", remote: bool = True, experience_level: str = None, **kwargs) -> list[Job]:
        """Search LinkedIn for jobs."""
        logger.info("LinkedIn search: role='%s' location='%s' remote=%s", role, location, remote)

        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        jobs = []

        # Build search URL
        search_url = (
            f"{self.BASE_URL}/jobs/search/"
            f"?keywords={role.replace(' ', '%20')}"
            f"&location={location.replace(' ', '%20')}"
        )
        if remote:
            search_url += "&f_WT=2"
        exp_map = {
            "internship": "1", "entry": "2", "associate": "3",
            "mid": "4", "senior": "4", "director": "5", "executive": "6",
        }
        if experience_level and experience_level.lower() in exp_map:
            search_url += f"&f_E={exp_map[experience_level.lower()]}"

        try:
            with sync_playwright() as p:
                context, page = self._ensure_authenticated(p, search_url)
                if not context or not page:
                    return []

                # Final login-wall guard
                if self._is_login_wall(page):
                    logger.error("LinkedIn: Still on login wall after full auth flow. Aborting.")
                    page.close()
                    context.close()
                    return []

                # Scroll to load more jobs
                logger.debug("LinkedIn: Scrolling to load results")
                try:
                    list_selector = ".jobs-search-results-list"
                    if page.locator(list_selector).count() > 0:
                        for _ in range(3):
                            page.evaluate(f"document.querySelector('{list_selector}').scrollBy(0, 1000)")
                            page.wait_for_timeout(1500)
                    else:
                        for _ in range(3):
                            page.mouse.wheel(0, 1000)
                            page.wait_for_timeout(1500)
                except Exception as scroll_e:
                    logger.warning("LinkedIn: Scroll failed (%s), continuing anyway", scroll_e)

                # Parse search results
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")

                cards = soup.select("div.job-card-container")
                if not cards:
                    cards = soup.select(".jobs-search-results__list-item")

                logger.info("LinkedIn: Found %d job cards in DOM", len(cards))

                processed_count = 0
                for card in cards:
                    if processed_count >= 25:
                        break
                    try:
                        job_id = (
                            card.get("data-job-id")
                            or (card.find_parent("li").get("data-occludable-job-id") if card.find_parent("li") else None)
                        )
                        if not job_id:
                            continue

                        title_link = (
                            card.select_one("a[class*='job-card-list__title']")
                            or card.select_one("a.job-card-container__link")
                        )
                        if not title_link:
                            continue

                        title = title_link.get_text(strip=True)
                        job_url = f"{self.BASE_URL}/jobs/view/{job_id}/"

                        company_elem = (
                            card.select_one(".artdeco-entity-lockup__subtitle")
                            or card.select_one(".job-card-container__company-name")
                        )
                        company = company_elem.get_text(strip=True) if company_elem else "Unknown"

                        location_elem = (
                            card.select_one(".job-card-container__metadata-wrapper li")
                            or card.select_one(".job-card-container__metadata-item")
                        )
                        location_text = location_elem.get_text(strip=True) if location_elem else location

                        is_easy_apply = "Easy Apply" in card.get_text()

                        # Click card to get description from right pane
                        description = f"Job at {company}. Apply on LinkedIn."
                        try:
                            card_locator = page.locator(f"div[data-job-id='{job_id}']").first
                            if card_locator.is_visible():
                                card_locator.click()
                                page.wait_for_timeout(1200)
                                desc_elem = page.locator("div.jobs-description-content").first
                                if desc_elem.is_visible():
                                    description = desc_elem.inner_text()
                        except Exception as click_e:
                            logger.debug("LinkedIn: Could not click card %s: %s", job_id, click_e)

                        job = Job(
                            id=f"linkedin_{job_id}",
                            title=title,
                            company=company,
                            location=location_text,
                            description=description,
                            skills_required=[],
                            platform="linkedin",
                            application_url=job_url,
                            is_easy_apply=is_easy_apply,
                            is_remote="remote" in location_text.lower(),
                            salary=None,
                            posted_date=None,
                            experience_required=experience_level,
                            date_found=datetime.now().strftime("%Y-%m-%d"),
                        )
                        jobs.append(job)
                        processed_count += 1
                        logger.debug("LinkedIn: Processed %s @ %s", title, company)

                    except Exception as e:
                        logger.error("LinkedIn: Error parsing card: %s", e)
                        continue

                page.close()
                context.close()

        except Exception as e:
            logger.error("LinkedIn scraper fatal error: %s", e)

        logger.info("LinkedIn scrape complete — %d jobs found", len(jobs))
        return jobs
