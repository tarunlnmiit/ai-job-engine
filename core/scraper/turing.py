import os
import time
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.turing")

TURING_USER_DATA = os.path.join(os.getcwd(), "turing_user_data")
TURING_BASE_URL = "https://work.turing.com/jobs"
CHALLENGE_TIMEOUT = 120


class TuringScraper(BaseJobScraper):
    """Scrape jobs from work.turing.com (public job board, no auth required)."""

    def _launch_context(self, playwright):
        return playwright.chromium.launch_persistent_context(
            TURING_USER_DATA,
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
        )

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Turing search: role='%s'", role)
        jobs = []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("playwright not installed")
            return []

        search_url = f"{TURING_BASE_URL}?search={role.replace(' ', '+')}"

        try:
            with sync_playwright() as p:
                context = self._launch_context(p)
                page = context.new_page()

                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                except ImportError:
                    pass

                logger.info("Turing: Navigating to %s", search_url)
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)

                # Incapsula HARD block = specific error page (not just script references)
                def is_hard_blocked():
                    try:
                        c = page.content()
                        return "Request unsuccessful" in c and "Incapsula incident ID" in c
                    except Exception:
                        return False

                if is_hard_blocked():
                    logger.error("Turing: Hard-blocked by Incapsula. Aborting.")
                    page.close()
                    context.close()
                    return []

                # Scroll to load more
                for _ in range(5):
                    page.mouse.wheel(0, 800)
                    page.wait_for_timeout(800)
                page.mouse.wheel(0, -9999)
                page.wait_for_timeout(1000)

                from bs4 import BeautifulSoup
                content = page.content()

                debug_path = os.path.join(os.getcwd(), "turing_debug.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Turing: HTML dumped → %s", debug_path)

                soup = BeautifulSoup(content, "html.parser")

                all_classes: set[str] = set()
                for el in soup.find_all(class_=True):
                    all_classes.update(el.get("class", []))
                job_classes = sorted(
                    c for c in all_classes
                    if any(k in c.lower() for k in ("job", "card", "role", "position", "listing", "opportun"))
                )
                logger.info("Turing: Job-related classes: %s", job_classes[:40])

                cards = (
                    soup.select("[class*='job-card']")
                    or soup.select("[class*='JobCard']")
                    or soup.select("[class*='job_card']")
                    or soup.select("[class*='job-listing']")
                    or soup.select("[class*='JobListing']")
                    or soup.select("[class*='role-card']")
                    or soup.select("[class*='RoleCard']")
                    or soup.select("[class*='position-card']")
                    or soup.select("[class*='opportunity']")
                    # Grid of cards — target clickable card wrappers
                    or soup.select("a[href*='/jobs/']")
                    or soup.select("div[class*='card']")
                )

                if not cards:
                    logger.warning("Turing: No cards — extracting /jobs/ links")
                    seen_urls: set[str] = set()
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/jobs/" not in href:
                            continue
                        full_url = href if href.startswith("http") else f"https://work.turing.com{href}"
                        if full_url in seen_urls:
                            continue
                        seen_urls.add(full_url)
                        title = a.get_text(strip=True)
                        if not title or len(title) < 3:
                            continue
                        job_id = hashlib.md5(full_url.encode()).hexdigest()[:10]
                        job = Job(
                            id=f"turing_{job_id}",
                            title=title,
                            company="Turing",
                            location="Remote",
                            description=f"Remote contractual role at Turing. Role: {title}",
                            platform="turing",
                            application_url=full_url,
                            is_remote=True,
                            date_found=datetime.now().strftime("%Y-%m-%d"),
                        )
                        jobs.append(job)
                else:
                    logger.info("Turing: Found %d job cards", len(cards))
                    seen_urls: set[str] = set()
                    for card in cards[:25]:
                        try:
                            href = ""
                            for a in card.find_all("a", href=True):
                                href = a["href"]
                                break
                            if not href:
                                href = card.get("href", "")
                            full_url = href if href.startswith("http") else f"https://work.turing.com{href}" if href else ""
                            if full_url in seen_urls:
                                continue
                            seen_urls.add(full_url)

                            title_el = card.select_one("h1, h2, h3, h4") or card.select_one("[class*='title'], [class*='Title']")
                            title = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)[:80]
                            if not title or len(title) < 3:
                                continue

                            loc_el = card.select_one("[class*='location'], [class*='Location']")
                            loc_text = loc_el.get_text(strip=True) if loc_el else "Remote"

                            sal_el = (
                                card.select_one("[class*='salary']")
                                or card.select_one("[class*='Salary']")
                                or card.select_one("[class*='rate']")
                                or card.select_one("[class*='Rate']")
                                or card.select_one("[class*='badge']")
                                or card.select_one("[class*='price']")
                            )
                            salary = sal_el.get_text(strip=True) if sal_el else None

                            desc_el = card.select_one("[class*='description'], [class*='Description'], [class*='summary']")
                            description = desc_el.get_text("\n", strip=True) if desc_el else f"Remote contractual role at Turing. Role: {title}"

                            job_id = hashlib.md5((full_url or title).encode()).hexdigest()[:10]
                            job = Job(
                                id=f"turing_{job_id}",
                                title=title,
                                company="Turing",
                                location=loc_text,
                                description=description,
                                salary=salary,
                                platform="turing",
                                application_url=full_url or search_url,
                                is_remote=True,
                                date_found=datetime.now().strftime("%Y-%m-%d"),
                            )
                            jobs.append(job)
                            logger.debug("Turing: Scraped '%s'", title)

                        except Exception as e:
                            logger.error("Turing: Error on card: %s", e)
                            continue

                page.close()
                context.close()

        except Exception as e:
            logger.error("Turing scraper fatal error: %s", e)

        logger.info("Turing scrape complete — %d jobs found", len(jobs))
        return jobs
