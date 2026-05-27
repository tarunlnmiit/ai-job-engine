import os
import tempfile
import shutil
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.turing")

TURING_BASE_URL = "https://work.turing.com/jobs"


class TuringScraper(BaseJobScraper):
    """Scrape jobs from work.turing.com (public job board, no auth required)."""

    def _launch_context(self, playwright, headless=True):
        """Launch a fresh browser context with a temporary profile directory."""
        temp_dir = tempfile.mkdtemp(prefix="turing_pw_")
        logger.debug("Turing: Using temp browser profile: %s", temp_dir)

        context = playwright.chromium.launch_persistent_context(
            temp_dir,
            headless=headless,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
        )
        return context, temp_dir

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Turing search: role='%s'", role)
        jobs: list[Job] = []

        try:
            from playwright.sync_api import sync_playwright
            from bs4 import BeautifulSoup
        except ImportError as e:
            logger.error("Missing dependency: %s", e)
            return []

        search_url = f"{TURING_BASE_URL}?search={role.replace(' ', '+')}"
        headless = kwargs.get("headless", True)

        temp_dir = None
        try:
            with sync_playwright() as p:
                context, temp_dir = self._launch_context(p, headless=headless)
                page = context.new_page()

                # Apply stealth if available
                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                except ImportError:
                    pass

                logger.info("Turing: Navigating to %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                # Wait for job cards to render
                try:
                    page.wait_for_selector(
                        "article[data-job-card-id]", timeout=20000
                    )
                except Exception:
                    logger.warning("Turing: Timeout waiting for job cards")

                # Scroll to load more results
                for _ in range(3):
                    page.mouse.wheel(0, 1000)
                    page.wait_for_timeout(1000)

                # Collect all job card IDs from the listing page
                card_els = page.query_selector_all("article[data-job-card-id]")

                if not card_els:
                    logger.warning(
                        "Turing: No job cards found. Trying fallback."
                    )
                    card_els = page.query_selector_all(
                        ".group.relative.cursor-pointer"
                    )

                if not card_els:
                    logger.info("Turing: No jobs found on page.")
                    page.close()
                    context.close()
                    return []

                # Pre-collect card metadata from listing page using BS4
                content = page.content()
                soup = BeautifulSoup(content, "html.parser")
                card_soups = soup.select("article[data-job-card-id]")

                card_data = []
                for cs in card_soups:
                    job_id = cs.get("data-job-card-id")
                    if not job_id:
                        continue
                    title_el = cs.select_one("h3")
                    title = title_el.get_text(strip=True) if title_el else "Unknown Role"
                    snippet_el = cs.select_one("p")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    salary = None
                    card_text = cs.get_text()
                    if "$" in card_text:
                        badge = cs.find(string=lambda t: t and "$" in t)
                        if badge:
                            salary = badge.strip()
                    card_data.append({
                        "job_id": job_id,
                        "title": title,
                        "snippet": snippet,
                        "salary": salary,
                    })

                logger.info("Turing: Found %d job cards", len(card_data))

                count = 0
                for cd in card_data:
                    if count >= 20:
                        break
                    job_id = cd["job_id"]
                    title = cd["title"]
                    snippet = cd["snippet"]
                    salary = cd["salary"]
                    full_url = f"{TURING_BASE_URL}?jobId={job_id}"
                    description = snippet

                    logger.info("Turing: Fetching details for '%s'", title)

                    try:
                        # Click the specific card to open the detail side panel
                        card_selector = f'article[data-job-card-id="{job_id}"]'

                        # Ensure we're on the listing page
                        if "jobId=" in page.url and f"jobId={job_id}" not in page.url:
                            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_selector(card_selector, timeout=10000)

                        card_handle = page.query_selector(card_selector)
                        if card_handle:
                            card_handle.click()
                            page.wait_for_timeout(1500)

                            # Wait for the "Job Description" heading in the panel
                            try:
                                page.wait_for_selector(
                                    'h3:text("Job Description")',
                                    timeout=5000,
                                )
                            except Exception:
                                pass

                            detail_soup = BeautifulSoup(
                                page.content(), "html.parser"
                            )

                            # Find "Job Description" h3 → next sibling div
                            desc_header = detail_soup.find(
                                lambda tag: tag.name == "h3"
                                and "Job Description" in (tag.text or "")
                            )
                            if desc_header:
                                desc_panel = desc_header.find_next("div")
                                if desc_panel:
                                    description = desc_panel.get_text(
                                        "\n", strip=True
                                    )
                            else:
                                # Fallback: look for any large text block
                                # in the right-side panel
                                panels = detail_soup.select(
                                    "aside, [class*='detail'], [class*='panel']"
                                )
                                for panel in panels:
                                    text = panel.get_text("\n", strip=True)
                                    if len(text) > 200:
                                        description = text
                                        break
                    except Exception as e:
                        logger.warning(
                            "Turing: Could not fetch details for '%s': %s",
                            title, e,
                        )

                    job = Job(
                        id=f"turing_{job_id}",
                        title=title,
                        company="Turing",
                        location="Remote",
                        description=description[:5000],
                        salary=salary,
                        platform="turing",
                        application_url=full_url,
                        is_remote=True,
                        date_found=datetime.now().strftime("%Y-%m-%d"),
                    )
                    jobs.append(job)
                    count += 1
                    logger.debug("Turing: Scraped '%s'", title)

                page.close()
                context.close()

        except Exception as e:
            logger.error("Turing scraper fatal error: %s", e)
        finally:
            # Clean up temp browser profile
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

        logger.info("Turing scrape complete — %d jobs found", len(jobs))
        return jobs
