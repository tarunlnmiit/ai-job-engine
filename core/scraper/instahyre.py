import os
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

logger = get_logger("scraper.instahyre")

BASE_URL = "https://www.instahyre.com/search-jobs"


class InstahyreScraper(BaseJobScraper):
    """Scrape jobs from Instahyre using Playwright."""

    def search(self, role: str, location: str = "Remote", max_pages: int = 1, **kwargs) -> list[Job]:
        logger.info("Searching Instahyre: role=%r location=%r max_pages=%d", role, location, max_pages)

        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return []

        jobs = self._search_playwright(role, location, max_pages)
        logger.info("Instahyre search complete: %d jobs found", len(jobs))
        return jobs

    def _search_playwright(self, role: str, location: str, max_pages: int) -> list[Job]:
        if not BS_AVAILABLE:
            return []

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
                    
                    try:
                        from playwright_stealth import stealth_sync
                        stealth_sync(page)
                        logger.info("Stealth mode enabled for Instahyre scraper")
                    except ImportError:
                        pass

                for pg in range(max_pages):
                    # Instahyre uses "Work From Home" instead of "Remote"
                    search_loc = location
                    if search_loc.lower() == "remote":
                        search_loc = "Work From Home"
                        
                    # Using ?skills=role&location=location format
                    url = f"{BASE_URL}/?skills={role.replace(' ', '+')}&location={search_loc.replace(' ', '+')}"
                    # Note: Instahyre pagination is often endless scrolling or client side, but we will just load the first page for now.
                    logger.debug("Fetching Instahyre URL: %s", url)

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        
                        if "Just a moment..." in page.title() or "cloudflare" in page.content().lower():
                            logger.info("Cloudflare detected on Instahyre. Please solve the captcha.")
                            try:
                                page.wait_for_function(
                                    "() => !document.title.includes('Just a moment') && !document.body.innerText.toLowerCase().includes('cloudflare')",
                                    timeout=120000
                                )
                                logger.info("Verification cleared!")
                                page.wait_for_timeout(2000)
                            except:
                                break

                        page.wait_for_timeout(random.uniform(3, 5) * 1000)
                    except Exception as e:
                        logger.warning("Page load failed: %s", e)

                    try:
                        page.wait_for_selector(".employer-block", timeout=15000)
                    except:
                        logger.warning("Job cards never appeared on Instahyre.")
                        break

                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    job_cards = soup.find_all(class_="employer-block")

                    if not job_cards:
                        break

                    for card in job_cards:
                        try:
                            job = self._parse_card(card, location)
                            if job:
                                jobs.append(job)
                        except Exception as e:
                            logger.warning("Error parsing Instahyre job card: %s", e)
                            
                    break # Only 1 page for now until we implement pagination properly

                if owned_browser:
                    if 'browser_context' in locals():
                        browser_context.close()
                    elif browser:
                        browser.close()
                else:
                    page.close()

        except Exception as e:
            logger.error("Playwright Instahyre scrape failed: %s", e, exc_info=True)

        return jobs

    def _parse_card(self, card, fallback_location: str) -> Job:
        # Title
        title_elem = card.select_one(".employer-details-mobile .employer-job-name .company-name")
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Company
        company_elem = card.select_one(".employer-details-mobile .employer-company-name .company-name")
        company = company_elem.get_text(strip=True) if company_elem else ""
        
        if not title:
            # Fallback to desktop details
            fallback_title = card.select_one(".employer-details .employer-job-name .company-name")
            if fallback_title:
                text = fallback_title.get_text(strip=True)
                if " - " in text:
                    company, title = text.split(" - ", 1)
                else:
                    title = text
                    company = "Unknown"

        if not title:
            return None

        # Link
        link_elem = card.find("a", id="employer-profile-opportunity")
        href = link_elem.get("href", "") if link_elem else ""
        job_url = f"https://www.instahyre.com{href}" if href and href.startswith("/") else href

        # Location
        loc_elem = card.select_one(".employer-details-mobile .employer-locations .info .ng-binding")
        job_location = loc_elem.get_text(strip=True) if loc_elem else fallback_location

        # Description
        desc_elem = card.select_one(".employer-notes")
        description = desc_elem.get_text(strip=True) if desc_elem else ""

        # Skills
        skills = []
        for li in card.select(".job-skills ul li"):
            skills.append(li.get_text(strip=True))
            
        description += " | Skills: " + ", ".join(skills)

        # Extract numeric ID from URL if possible
        job_id_str = title.replace(' ', '_')
        if "/job-" in job_url:
            try:
                job_id_str = job_url.split("/job-")[1].split("-")[0]
            except Exception:
                pass

        return Job(
            id=f"instahyre_{job_id_str}",
            title=title,
            company=company,
            location=job_location,
            description=description,
            skills_required=skills,
            platform="instahyre",
            application_url=job_url,
            is_easy_apply=False,
            is_remote="remote" in job_location.lower() or "work from home" in job_location.lower(),
            salary="N/A",
            posted_date=None,
            experience_required=None,
            date_found=datetime.now().strftime("%Y-%m-%d"),
        )
