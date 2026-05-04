from datetime import datetime
import os
import random
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

logger = get_logger("scraper.indeed")

BASE_URL = "https://in.indeed.com/jobs"


class IndeedScraper(BaseJobScraper):
    """Scrape jobs from Indeed India via Playwright (public search, no login)."""

    def search(self, role: str, location: str = "Remote", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching Indeed: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("Indeed search complete: %d jobs found", len(jobs))
        return jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        if not BS_AVAILABLE:
            logger.error("BeautifulSoup not installed. Run: pip install beautifulsoup4")
            return []

        jobs = []
        cdp_url = "http://localhost:9222"

        try:
            with sync_playwright() as p:
                # Try connecting to existing Chrome with real profile first
                owned_browser = False
                browser = None
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    logger.info("Connected to existing Chrome via CDP at %s", cdp_url)
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                    page = context.new_page()
                except Exception as e:
                    logger.warning("CDP connect failed (%s) — launching persistent context browser", e)
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
                            "--disable-infobars"
                        ],
                        ignore_default_args=["--enable-automation"]
                    )
                    owned_browser = True
                    page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
                    
                    # Apply stealth to bypass Cloudflare
                    try:
                        from playwright_stealth import stealth_sync
                        stealth_sync(page)
                        logger.info("Stealth mode enabled for Indeed scraper")
                    except ImportError:
                        logger.warning("playwright-stealth not found — skipping stealth mode")

                has_waited_for_login = False
                for pg in range(max_pages):
                    url = f"{BASE_URL}?q={role}&l={location}&start={pg * 10}"
                    logger.debug("Fetching Indeed page %d: %s", pg + 1, url)

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        
                        # Manual Login Check: If "Sign in" is visible, wait for user to potentially sign in
                        if not has_waited_for_login and page.query_selector("a[href*='logging'], a:has-text('Sign in'), .gnav-LoggedOut"):
                            logger.info("Sign-in button detected. Please sign in manually. Waiting 2 minutes...")
                            page.wait_for_timeout(120000)
                            has_waited_for_login = True

                        # Check for login redirect (enforced by Indeed)
                        if "auth" in page.url or "secure.indeed.com" in page.url:
                            logger.info("Indeed login required. Please log in manually in the browser window.")
                            try:
                                # Wait for the user to complete login and return to a jobs page
                                page.wait_for_url("**/jobs**", timeout=120000)
                                logger.info("Login detected! Resuming search.")
                                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            except Exception as login_err:
                                logger.error("Login flow failed or timed out: %s", login_err)
                                break

                        # Check for Cloudflare/Human verification
                        if "Just a moment..." in page.title() or "cloudflare" in page.content().lower():
                            logger.info("Cloudflare 'Verify you are human' detected. Please solve the captcha in the browser.")
                            try:
                                # Wait for the verification to complete and redirect back to jobs page
                                page.wait_for_function(
                                    "() => !document.title.includes('Just a moment') && !document.body.innerText.toLowerCase().includes('cloudflare')",
                                    timeout=120000
                                )
                                logger.info("Verification cleared! Resuming search.")
                                page.wait_for_timeout(2000)
                            except Exception as cf_err:
                                logger.error("Cloudflare verification timed out or failed: %s", cf_err)
                                break

                        delay = random.uniform(3, 7)
                        page.wait_for_timeout(delay * 1000) 
                    except Exception as e:
                        logger.warning("Page load failed or timed out on page %d: %s. Continuing...", pg + 1, e)
                        # Don't break here, try to see if content still loaded or move to next page

                    # Dismiss intercept/sign-in modal if present
                    try:
                        modal_selectors = [
                            "[data-testid='passport-intercept-type-modal']",
                            "#vjs-container-modal",
                            ".jobsearch-ResultsList-modal"
                        ]
                        for selector in modal_selectors:
                            modal = page.query_selector(selector)
                            if modal:
                                logger.debug("Dismissing Indeed modal: %s", selector)
                                close_btn = modal.query_selector("button[aria-label='close'], button[aria-label='Close'], button:last-child")
                                if close_btn:
                                    close_btn.click()
                                else:
                                    page.keyboard.press("Escape")
                                page.wait_for_timeout(1000)
                    except Exception as e:
                        logger.debug("Modal dismiss attempt failed: %s", e)

                    # Wait for job cards to render
                    try:
                        page.wait_for_selector("[data-testid='slider_item'], article, .jobsearch-ResultsList li", timeout=10000)
                    except Exception:
                        logger.warning("Job cards never appeared on page %d", pg + 1)
                        break

                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")

                    job_cards = soup.find_all(attrs={"data-testid": "slider_item"})
                    if not job_cards:
                        job_cards = soup.find_all("article")
                    if not job_cards:
                        job_cards = soup.find_all("div", {"data-qa": "organic"})

                    if not job_cards:
                        logger.warning("No job cards on page %d for %r in %r", pg + 1, role, location)
                        break

                    logger.debug("Found %d job cards on page %d", len(job_cards), pg + 1)

                    for card in job_cards:
                        try:
                            job = self._parse_card(card, location)
                            if job:
                                jobs.append(job)
                                logger.debug("Parsed: %r at %r", job.title, job.company)
                        except Exception as e:
                            logger.warning("Error parsing job card: %s", e)

                if owned_browser:
                    if 'browser_context' in locals():
                        browser_context.close()
                    elif browser:
                        browser.close()
                else:
                    page.close()

        except Exception as e:
            logger.error("Playwright scrape failed: %s", e, exc_info=True)

        return jobs

    def _parse_card(self, card, fallback_location: str):
        # Title: span inside h2.jobTitle > a.jcs-JobTitle
        title_elem = card.find("a", class_=lambda x: x and "jcs-JobTitle" in x if x else False)
        if not title_elem:
            title_elem = card.find("h2", class_=lambda x: x and "jobTitle" in x if x else False)
        if not title_elem:
            title_elem = card.find("a", attrs={"data-testid": "job-title"})
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title:
            return None

        # Job URL: href on jcs-JobTitle anchor
        href = title_elem.get("href", "") if title_elem.name == "a" else ""
        if not href:
            link = card.find("a", href=lambda x: x and "/rc/clk" in x if x else False)
            href = link.get("href", "") if link else ""
        job_url = f"https://in.indeed.com{href}" if href and not href.startswith("http") else href

        # Company: data-testid="company-name"
        company_elem = card.find(attrs={"data-testid": "company-name"})
        company = company_elem.get_text(strip=True) if company_elem else "Unknown"

        # Location: data-testid="text-location"
        location_elem = card.find(attrs={"data-testid": "text-location"})
        job_location = location_elem.get_text(strip=True) if location_elem else fallback_location

        # Snippets: data-testid can contain multiple values like "attribute_snippet_testid salary-snippet-container"
        snippets = card.find_all(attrs={"data-testid": lambda x: x and "attribute_snippet_testid" in x})
        description_parts = []
        job_salary = "N/A"
        
        for snip in snippets:
            text = snip.get_text(strip=True)
            if any(c in text for c in "₹$") or "month" in text.lower() or "year" in text.lower() or "/hr" in text.lower():
                job_salary = text
            else:
                description_parts.append(text)
        
        description = " | ".join(description_parts)

        # Fallback 1: specific salary-snippet testid
        if job_salary == "N/A":
            salary_snippet = card.find(attrs={"data-testid": lambda x: x and "salary-snippet" in x})
            if salary_snippet:
                job_salary = salary_snippet.get_text(strip=True)

        # Fallback 2: CSS classes
        if job_salary == "N/A":
            salary_snippet = card.find("div", class_=lambda x: x and "salary-snippet" in x)
            if not salary_snippet:
                salary_snippet = card.find("div", class_=lambda x: x and "metadata" in x and "salary" in x)
            if salary_snippet:
                job_salary = salary_snippet.get_text(strip=True)
        
        # Fallback 3: Aggressive search in all metadata elements
        if job_salary == "N/A":
            metadata_group = card.find(class_=lambda x: x and "jobMetaDataGroup" in x)
            if metadata_group:
                for li in metadata_group.find_all("li"):
                    text = li.get_text(strip=True)
                    if any(c in text for c in "₹$") or "month" in text.lower() or "year" in text.lower():
                        job_salary = text
                        break

        return Job(
            id=f"indeed_{job_url.split('/')[-1] if job_url else title.replace(' ', '_')[:20]}",
            title=title,
            company=company,
            location=job_location,
            description=description,
            skills_required=[],
            platform="indeed",
            application_url=job_url,
            is_easy_apply=False,
            is_remote="remote" in job_location.lower(),
            salary=job_salary,
            posted_date=None,
            experience_required=None,
            date_found=datetime.now().strftime("%Y-%m-%d"),
        )
