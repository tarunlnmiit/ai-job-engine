import os
import time
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.uplers")

UPLERS_USER_DATA = os.path.join(os.getcwd(), "uplers_user_data")
UPLERS_JOBS_URL = "https://platform.uplers.com/talent/all-opportunities"
CHALLENGE_TIMEOUT = 600


class UplersScraper(BaseJobScraper):
    """Scrape jobs from Uplers platform (platform.uplers.com)."""

    def _launch_context(self, playwright, headless: bool):
        return playwright.chromium.launch_persistent_context(
            UPLERS_USER_DATA,
            headless=headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900} if not headless else None,
        )

    def _handle_popups(self, page):
        """Handle annoying Uplers popups like 'Profile Outdated'."""
        try:
            # The user mentioned a 'Skip' button on an 'outdated profile' dialog
            # We'll try to find any button with 'Skip' or 'Update later' text
            skip_selectors = [
                "button:has-text('Skip')",
                "button:has-text('Skip for now')",
                "button:has-text('Update later')",
                "span:has-text('Skip')",
                ".modal-close",
                "[class*='close']"
            ]
            for selector in skip_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=1500):
                        logger.info("Uplers: Found popup element '%s', attempting to skip...", selector)
                        btn.click()
                        page.wait_for_timeout(1000)
                        return True
                except:
                    continue
        except Exception as e:
            logger.debug("Uplers: Error during popup handling: %s", e)
        return False

    @staticmethod
    def _is_logged_in(page) -> bool:
        url = page.url.lower()
        if any(k in url for k in ("login", "signin", "auth", "sso", "logout")):
            return False
        # Must be on an authenticated sub-route — not just the root domain
        return any(k in url for k in ("talent/", "dashboard", "profile", "all-opportunities"))

    def _ensure_authenticated(self, playwright):
        """Return (context, page) with authenticated Uplers session, or (None, None)."""
        logger.info("Uplers Auth [Stage 1]: Visible browser with saved cookies...")
        context = self._launch_context(playwright, headless=False)
        page = context.new_page()
        page.goto(UPLERS_JOBS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        if self._is_logged_in(page):
            logger.info("Uplers Auth: ✅ Cookies valid — already logged in!")
            return context, page

        logger.info("Uplers Auth [Stage 2]: Opening VISIBLE browser — please log in...")
        page.close()
        context.close()

        context = self._launch_context(playwright, headless=False)
        page = context.new_page()
        page.goto("https://platform.uplers.com", wait_until="domcontentloaded", timeout=30000)

        logger.info(
            "🔔 Uplers: Log in manually in the browser window (e.g., using Google Login). Timeout: %ds...",
            CHALLENGE_TIMEOUT,
        )
        deadline = time.time() + CHALLENGE_TIMEOUT
        last_log = 0
        while time.time() < deadline:
            now = int(time.time())
            if now - last_log >= 10:
                logger.info("Uplers Auth: ⏳ Waiting... %ds remaining", int(deadline - time.time()))
                last_log = now
            if self._is_logged_in(page):
                break
            page.wait_for_timeout(2000)
        else:
            logger.error("Uplers Auth: ❌ Login not completed within %ds. Aborting.", CHALLENGE_TIMEOUT)
            page.close()
            context.close()
            return None, None

        logger.info("Uplers Auth: ✅ Logged in! Cookies saved to %s", UPLERS_USER_DATA)
        page.goto(UPLERS_JOBS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        self._handle_popups(page)
        return context, page

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Uplers search: role='%s'", role)
        jobs = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright not installed")
            return []

        try:
            with sync_playwright() as p:
                context, page = self._ensure_authenticated(p)
                if not context or not page:
                    return []

                if not self._is_logged_in(page):
                    logger.error("Uplers: Still not logged in after auth flow. Aborting.")
                    page.close()
                    context.close()
                    return []

                # Construct search URL
                search_query = role.replace(" ", "+")
                search_url = f"{UPLERS_JOBS_URL}?search={search_query}"
                logger.info("Uplers: Navigating to %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                # Wait for SPA JS to fully render
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)
                self._handle_popups(page)

                # Scroll to trigger lazy-loaded cards
                for _ in range(5):
                    page.mouse.wheel(0, 800)
                    page.wait_for_timeout(800)
                page.mouse.wheel(0, -9999)
                page.wait_for_timeout(1000)

                from bs4 import BeautifulSoup
                content = page.content()

                # Dump raw HTML for selector debugging
                debug_path = os.path.join(os.getcwd(), "uplers_debug.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Uplers: HTML dumped → %s", debug_path)

                soup = BeautifulSoup(content, "html.parser")

                # Log all class names that look job-related (helps tune selectors)
                all_classes: set[str] = set()
                for el in soup.find_all(class_=True):
                    all_classes.update(el.get("class", []))
                job_classes = sorted(
                    c for c in all_classes
                    if any(k in c.lower() for k in ("job", "card", "opportun", "list", "item", "role", "position"))
                )
                logger.info("Uplers: Job-related classes in DOM: %s", job_classes[:40])

                # Find cards — broad selector sweep
                card_selector = (
                    "[class*='opportunit'], [class*='JobCard'], [class*='job-card'], "
                    "[class*='job_card'], [class*='card-item'], [class*='listing'], "
                    "[class*='Listing'], [class*='role-card'], [class*='RoleCard'], "
                    "[class*='position'], [class*='product-job']"
                )
                cards = (
                    soup.select("[class*='opportunit']")
                    or soup.select("[class*='JobCard']")
                    or soup.select("[class*='job-card']")
                    or soup.select("[class*='job_card']")
                    or soup.select("[class*='card-item']")
                    or soup.select("[class*='product-job']")
                    or soup.select("[class*='listing']")
                    or soup.select("[class*='Listing']")
                    or soup.select("[class*='role-card']")
                    or soup.select("[class*='RoleCard']")
                    or soup.select("[class*='position']")
                )
                logger.info("Uplers: Found %d job cards in DOM", len(cards))

                # Collect job IDs from hrefs or data attributes
                job_ids = []
                seen = set()
                for card in cards:
                    # Try href first (e.g. ?activeJob=HR030226121609)
                    href = card.get("href") or ""
                    for a in card.find_all("a", href=True):
                        href = a["href"]
                        break
                    job_id = None
                    if "activeJob=" in href:
                        job_id = href.split("activeJob=")[-1].split("&")[0]
                    if not job_id:
                        # Fall back to data-* attributes
                        for attr, val in card.attrs.items():
                            if "id" in attr.lower() and val and val not in seen:
                                job_id = str(val)
                                break
                    if job_id and job_id not in seen:
                        seen.add(job_id)
                        job_ids.append(job_id)

                # If no IDs found via DOM, try clicking cards directly via Playwright
                if not job_ids:
                    logger.warning("Uplers: No job IDs extracted from DOM — will click cards by index")
                    card_locators = page.locator(card_selector).all()
                    job_ids = list(range(len(card_locators)))  # use index as key

                logger.info("Uplers: Processing %d job IDs", min(len(job_ids), 25))

                for idx, job_key in enumerate(job_ids[:25]):
                    try:
                        if isinstance(job_key, int):
                            # Click by index
                            locators = page.locator(card_selector).all()
                            if job_key >= len(locators):
                                continue
                            locators[job_key].click()
                        else:
                            # Navigate to URL with activeJob param
                            job_url = f"{UPLERS_JOBS_URL}?activeJob={job_key}"
                            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)

                        page.wait_for_timeout(1500)
                        self._handle_popups(page)

                        detail_soup = BeautifulSoup(page.content(), "html.parser")

                        # Detail panel selector
                        panel = (
                            detail_soup.select_one("[class*='detail']")
                            or detail_soup.select_one("[class*='panel']")
                            or detail_soup.select_one("[class*='job-info']")
                            or detail_soup.select_one("main")
                        )
                        if not panel:
                            panel = detail_soup.body

                        # Title
                        title_el = panel.select_one("h1") or panel.select_one("h2") or panel.select_one("h3")
                        title = title_el.get_text(strip=True) if title_el else f"Uplers Role #{idx + 1}"

                        if len(title) < 3:
                            continue

                        # Location
                        loc_el = panel.select_one("[class*='location']") or panel.select_one("[class*='Location']")
                        loc_text = loc_el.get_text(strip=True) if loc_el else (location or "Remote")

                        # Salary
                        sal_el = panel.select_one("[class*='salary']") or panel.select_one("[class*='Salary']") or panel.select_one("[class*='compensation']")
                        salary = sal_el.get_text(strip=True) if sal_el else None

                        # Skills
                        skill_els = panel.select("[class*='skill'], [class*='tag'], [class*='Tag'], [class*='Skill']")
                        skills = [s.get_text(strip=True) for s in skill_els if s.get_text(strip=True)]

                        # Posted date
                        date_el = panel.select_one("[class*='date'], [class*='Date'], [class*='posted'], time")
                        posted_date = date_el.get_text(strip=True) if date_el else None

                        # Full description — using specific Uplers selectors found in investigation
                        desc_el = (
                            detail_soup.select_one(".jobDescription #hsContent")
                            or detail_soup.select_one(".jobDescription .HSContent")
                            or (panel.select_one("[class*='description']") if panel else None)
                            or (panel.select_one("[class*='Description']") if panel else None)
                            or (panel.select_one("[class*='jd']") if panel else None)
                            or (panel.select_one("[class*='content']") if panel else None)
                        )
                        if desc_el:
                            description = desc_el.get_text("\n", strip=True)
                        else:
                            description = panel.get_text("\n", strip=True)[:3000] if panel else "No description found."

                        app_url = (
                            f"{UPLERS_JOBS_URL}?activeJob={job_key}"
                            if isinstance(job_key, str)
                            else page.url
                        )

                        job_id_hash = (
                            job_key if isinstance(job_key, str)
                            else hashlib.md5(app_url.encode()).hexdigest()[:10]
                        )

                        job = Job(
                            id=f"uplers_{job_id_hash}",
                            title=title,
                            company="Uplers Client",
                            location=loc_text,
                            description=description,
                            skills_required=skills,
                            salary=salary,
                            posted_date=posted_date,
                            platform="uplers",
                            application_url=app_url,
                            is_remote="remote" in loc_text.lower(),
                            date_found=datetime.now().strftime("%Y-%m-%d"),
                        )
                        jobs.append(job)
                        logger.debug("Uplers: Scraped '%s'", title)

                    except Exception as e:
                        logger.error("Uplers: Error on card %s: %s", job_key, e)
                        continue

                page.close()
                context.close()

        except Exception as e:
            logger.error("Uplers scraper fatal error: %s", e)

        logger.info("Uplers scrape complete — %d jobs found", len(jobs))
        return jobs
