import os
import hashlib
import random
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

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

logger = get_logger("scraper.wellfound")

BASE_URL = "https://wellfound.com"

# Wellfound uses specific slugs for roles in their URL paths
# Format: /role/l/{role_slug}/{location_slug} or /role/r/{role_slug} for remote
ROLE_SLUG_MAP = {
    "data scientist": "data-scientist",
    "data science": "data-science",
    "ai engineer": "ai-engineer",
    "machine learning engineer": "machine-learning-engineer",
    "ml engineer": "machine-learning-engineer",
    "software engineer": "software-engineer",
    "backend engineer": "backend-engineer",
    "frontend engineer": "frontend-engineer",
    "full stack engineer": "full-stack-engineer",
    "fullstack engineer": "full-stack-engineer",
    "devops engineer": "devops-engineer",
    "data engineer": "data-engineer",
    "data analyst": "data-analyst",
    "product manager": "product-manager",
    "designer": "designer",
    "product designer": "product-designer",
    "nlp engineer": "nlp-engineer",
    "deep learning engineer": "deep-learning-engineer",
}

LOCATION_SLUG_MAP = {
    "germany": "germany",
    "berlin": "berlin",
    "munich": "munich",
    "hamburg": "hamburg",
    "netherlands": "netherlands",
    "amsterdam": "amsterdam",
    "spain": "spain",
    "france": "france",
    "paris": "paris",
    "united kingdom": "united-kingdom",
    "london": "london",
    "ireland": "ireland",
    "dublin": "dublin",
    "sweden": "sweden",
    "stockholm": "stockholm",
    "denmark": "denmark",
    "switzerland": "switzerland",
    "zurich": "zurich",
    "austria": "austria",
    "vienna": "vienna",
    "portugal": "portugal",
    "lisbon": "lisbon",
    "poland": "poland",
    "czech republic": "czech-republic",
}


class WellfoundScraper(BaseJobScraper):
    """Scrape jobs from Wellfound (formerly AngelList) using Playwright.

    Uses the /role/l/{role}/{location} URL path which correctly loads
    filtered results, instead of the broken ?q= query params.
    """

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Wellfound search: role='%s' location='%s'", role, location)

        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        return self._search_playwright(role, location)

    def _build_url(self, role: str, location: str) -> str:
        """Build the correct Wellfound search URL.

        Wellfound ignores ?q= and &location= query params on /jobs.
        The correct format is:
          /role/l/{role_slug}/{location_slug}  — for location-based search
          /role/r/{role_slug}                  — for remote-only search
        """
        role_lower = role.lower().strip()
        role_slug = ROLE_SLUG_MAP.get(role_lower, role_lower.replace(" ", "-"))

        loc_lower = (location or "").lower().strip()
        is_remote = not loc_lower or loc_lower in ("remote", "any", "")

        if is_remote:
            url = f"{BASE_URL}/role/r/{role_slug}"
        else:
            location_slug = LOCATION_SLUG_MAP.get(loc_lower, loc_lower.replace(" ", "-"))
            url = f"{BASE_URL}/role/l/{role_slug}/{location_slug}"

        return url

    def _launch_context(self, playwright, headless: bool):
        """Launch a persistent Chromium context that stores cookies."""
        CHROME_USER_DATA = os.path.join(os.getcwd(), "chrome_user_data")
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

    def _is_blocked(self, page) -> bool:
        """Check if Wellfound is showing a CAPTCHA (DataDome/Cloudflare)."""
        try:
            html = page.content().lower()
            if "geo.captcha-delivery.com" in html or "datadome" in html or "cloudflare" in html:
                return True
            return False
        except Exception:
            return False

    def _search_playwright(self, role: str, location: str) -> list[Job]:
        """Scrape Wellfound search results using Playwright."""
        jobs = []

        try:
            import time
            with sync_playwright() as p:
                url = self._build_url(role, location)
                logger.info("Fetching Wellfound URL: %s", url)

                # Stage 1: Try Headless
                context = self._launch_context(p, headless=True)
                page = context.new_page()
                
                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                except ImportError:
                    pass
                
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

                # Check if blocked by DataDome / Cloudflare
                if self._is_blocked(page):
                    logger.warning("Wellfound: CAPTCHA detected → reopening in VISIBLE mode...")
                    page.close()
                    context.close()

                    # Stage 2: Visible Mode
                    context = self._launch_context(p, headless=False)
                    page = context.new_page()
                    
                    try:
                        from playwright_stealth import stealth_sync
                        stealth_sync(page)
                    except ImportError:
                        pass
                    
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)

                    # Poll until CAPTCHA is solved
                    logger.warning("🔔 Wellfound CAPTCHA appeared — please solve it in the browser window! Waiting up to 180s...")
                    deadline = time.time() + 180
                    solved = False
                    while time.time() < deadline:
                        if not self._is_blocked(page):
                            solved = True
                            break
                        page.wait_for_timeout(2000)
                        
                    if not solved:
                        logger.error("Wellfound: ❌ CAPTCHA not solved within 180s. Aborting.")
                        page.close()
                        context.close()
                        return []
                    
                    logger.info("Wellfound: ✅ CAPTCHA solved! Proceeding...")
                    # Give it a moment to load the actual jobs page
                    page.wait_for_timeout(3000)

                try:
                    # Wait for job cards to render
                    page.wait_for_selector(
                        "[data-test='JobApplicationApplyButton'], a[href*='/jobs/'], div.mb-6",
                        timeout=20000
                    )
                    page.wait_for_timeout(random.uniform(1500, 2500))
                    logger.info("Wellfound page loaded: %s", page.title())
                except Exception as e:
                    logger.warning("Wellfound page load issue (might be 0 jobs): %s", e)

                html = page.content()
                page_jobs = self._parse_html(html)
                logger.info("Wellfound: found %d jobs", len(page_jobs))
                jobs.extend(page_jobs)

                page.close()
                context.close()

        except Exception as e:
            logger.error("Wellfound Playwright scrape failed: %s", e, exc_info=True)

        logger.info("Wellfound scrape complete — %d jobs collected", len(jobs))
        return jobs

    def _parse_html(self, html: str) -> list[Job]:
        """Parse Wellfound job listing page.

        The role page (e.g. /role/l/data-scientist/germany) uses a different
        card structure than the homepage. Each company block is:
          <div class="mb-6 w-full rounded border border-gray-400 bg-white">
            <div> ... company header ... </div>
            <div class="mb-4 w-full px-4"> ... job details ... </div>
          </div>
        """
        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: Role page cards — rounded bordered white cards
        job_cards = soup.find_all(
            "div",
            class_=lambda c: c and "mb-6" in c and "rounded" in c and "border-gray-400" in c and "bg-white" in c
        )

        # Strategy 2: Homepage/search cards — border-b bordered rows
        if not job_cards:
            job_cards = soup.find_all(
                "div",
                class_=lambda c: c and "border-b" in c and "border-gray-400" in c and "py-3" in c
            )

        logger.debug("Wellfound parser: found %d candidate job cards", len(job_cards))

        jobs = []
        seen_ids = set()
        for card in job_cards:
            try:
                parsed_jobs = self._parse_role_card(card)
                for job in parsed_jobs:
                    if job and job.id not in seen_ids:
                        seen_ids.add(job.id)
                        jobs.append(job)
            except Exception as e:
                logger.warning("Error parsing Wellfound card: %s", e)
                continue

        return jobs

    def _parse_role_card(self, card) -> list[Job]:
        """Parse a company card from the role page.

        Each card contains a company header and one or more job postings.
        """
        jobs = []

        # Extract company name from the header
        company = "Unknown"
        company_link = card.find("a", href=lambda h: h and "/company/" in h)
        if company_link:
            # Try the company logo alt text first
            company_img = company_link.find("img")
            if company_img and company_img.get("alt"):
                company = company_img["alt"].replace(" company logo", "").strip()
            else:
                # Try the h2 text
                h2 = company_link.find("h2")
                if h2:
                    company = h2.get_text(strip=True)
                else:
                    company = company_link.get_text(strip=True)

        # Find all job links in this card (a company card may have multiple jobs)
        job_links = card.find_all("a", href=lambda h: h and h.startswith("/jobs/"))
        if not job_links:
            # Fallback: try with full URL
            job_links = card.find_all("a", href=lambda h: h and "/jobs/" in h)

        for job_link in job_links:
            title = job_link.get_text(strip=True)
            if not title:
                continue

            job_path = job_link.get("href", "")
            if job_path.startswith("/"):
                job_url = f"{BASE_URL}{job_path}"
            else:
                job_url = job_path

            # Extract job ID from path: /jobs/4092966-senior-data-scientist-campaigns
            job_id_part = job_path.split("/jobs/")[-1].split("-")[0] if "/jobs/" in job_path else ""
            if not job_id_part:
                job_id_part = hashlib.md5(job_url.encode()).hexdigest()[:8]
            job_id = f"wellfound_{job_id_part}"

            # Location: look in sibling/parent elements for location icon + text
            location_text = "Remote"
            # Find the job detail container (parent div with px-4)
            detail_div = job_link.find_parent("div", class_=lambda c: c and "px-4" in c if c else False)
            if detail_div:
                # Location is in a span after a location SVG icon
                loc_spans = detail_div.find_all("span", class_=lambda c: c and "text-xs" in c if c else False)
                for span in loc_spans:
                    text = span.get_text(strip=True)
                    # Skip salary spans (contain $ or €)
                    if "$" in text or "€" in text or "equity" in text.lower():
                        continue
                    # Skip date spans
                    if any(kw in text.lower() for kw in ("ago", "today", "yesterday", "week", "month")):
                        continue
                    # Skip experience spans
                    if "of exp" in text.lower() or "years" in text.lower():
                        continue
                    if text and len(text) > 1:
                        location_text = text
                        break

            # Salary
            salary = None
            if detail_div:
                for span in detail_div.find_all("span", class_=lambda c: c and "text-xs" in c if c else False):
                    text = span.get_text(strip=True)
                    if "$" in text or "€" in text:
                        salary = text
                        break

            # Posted date
            posted_date = None
            if detail_div:
                for span in detail_div.find_all("span", class_=lambda c: c and "text-dark-a" in c if c else False):
                    text = span.get_text(strip=True)
                    if any(kw in text.lower() for kw in ("ago", "today", "yesterday", "week", "month")):
                        posted_date = text
                        break

            is_remote = "remote" in location_text.lower()

            job = Job(
                id=job_id,
                title=title,
                company=company,
                location=location_text,
                description="",  # Would require visiting each job page
                skills_required=[],
                platform="wellfound",
                application_url=job_url,
                is_easy_apply=True,  # Wellfound has in-platform apply
                is_remote=is_remote,
                salary=salary,
                posted_date=posted_date,
                experience_required=None,
                date_found=datetime.now().strftime("%Y-%m-%d"),
            )
            jobs.append(job)

        return jobs
