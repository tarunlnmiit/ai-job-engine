import os
import random
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

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

class LinkedInScraper(BaseJobScraper):
    """Scrape LinkedIn jobs using Playwright via CDP for stealth."""

    BASE_URL = "https://www.linkedin.com"

    def search(self, role: str, location: str = "United States", remote: bool = True, experience_level: str = None, **kwargs) -> list[Job]:
        """Search LinkedIn for jobs."""
        logger.info("LinkedIn search: role='%s' location='%s' remote=%s", role, location, remote)
        
        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        jobs = []
        cdp_url = "http://localhost:9222"

        try:
            with sync_playwright() as p:
                browser = None
                try:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    logger.info("LinkedIn: Connected to existing Chrome via CDP")
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                except Exception as e:
                    logger.warning("LinkedIn: CDP connect failed (%s) — please start Chrome with --remote-debugging-port=9222", e)
                    return []

                page = context.new_page()
                
                # Apply filters via URL
                # f_WT=2 is Remote
                # f_E=2,3,4 is Experience (2=Entry, 3=Associate, 4=Mid-Senior)
                search_url = f"{self.BASE_URL}/jobs/search/?keywords={role.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
                if remote:
                    search_url += "&f_WT=2"
                
                # Experience mapping
                exp_map = {"internship": "1", "entry": "2", "associate": "3", "mid": "4", "senior": "4", "director": "5", "executive": "6"}
                if experience_level and experience_level.lower() in exp_map:
                    search_url += f"&f_E={exp_map[experience_level.lower()]}"

                logger.debug("LinkedIn: Navigating to %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                
                # Wait for results or login wall
                page.wait_for_timeout(5000)
                
                if "login" in page.url or page.locator("input[name='session_key']").count() > 0:
                    logger.error("LinkedIn: Login required. Please log in to your LinkedIn account in the debugging Chrome instance.")
                    page.close()
                    return []

                # Scroll to load more jobs (LinkedIn loads jobs on scroll)
                logger.debug("LinkedIn: Scrolling to load results")
                try:
                    # Scroll the left pane if it exists, otherwise scroll window
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

                # Parse the search results list
                content = page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                cards = soup.select("div.job-card-container")
                if not cards:
                    # Try alternative selector
                    cards = soup.select(".jobs-search-results__list-item")
                
                logger.info("LinkedIn: Found %d job cards in DOM", len(cards))

                processed_count = 0
                for card in cards:
                    if processed_count >= 25: 
                        break
                    
                    try:
                        # Job ID can be on the card or parent li
                        job_id = card.get('data-job-id') or card.find_parent('li').get('data-occludable-job-id') if card.find_parent('li') else None
                        if not job_id:
                            continue

                        # Find title link - it has many classes
                        title_link = card.select_one("a[class*='job-card-list__title']") or card.select_one("a.job-card-container__link")
                        if not title_link:
                            continue
                        
                        title = title_link.get_text(strip=True)
                        job_url = f"{self.BASE_URL}/jobs/view/{job_id}/"
                        
                        company_elem = card.select_one(".artdeco-entity-lockup__subtitle") or card.select_one(".job-card-container__company-name")
                        company = company_elem.get_text(strip=True) if company_elem else "Unknown"
                        
                        location_elem = card.select_one(".job-card-container__metadata-wrapper li") or card.select_one(".job-card-container__metadata-item")
                        location_text = location_elem.get_text(strip=True) if location_elem else location

                        is_easy_apply = "Easy Apply" in card.get_text()
                        
                        # Click the card to get description from the right pane
                        description = f"Job at {company}. Apply on LinkedIn."
                        try:
                            card_locator = page.locator(f"div[data-job-id='{job_id}']").first
                            if card_locator.is_visible():
                                card_locator.click()
                                page.wait_for_timeout(1200)
                                
                                # Extract description from the right pane
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
                if browser:
                    browser.close()

        except Exception as e:
            logger.error("LinkedIn scraper fatal error: %s", e)

        logger.info("LinkedIn scrape complete — %d jobs found", len(jobs))
        return jobs
