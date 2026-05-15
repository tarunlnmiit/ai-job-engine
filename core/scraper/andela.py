import os
import time
import hashlib
from datetime import datetime
from .base import BaseJobScraper, Job
from logger import get_logger

logger = get_logger("scraper.andela")

ANDELA_USER_DATA = os.path.join(os.getcwd(), "andela_user_data")
ANDELA_JOBS_URL = "https://talent.andela.com/jobs"
CHALLENGE_TIMEOUT = 600


class AndelaScraper(BaseJobScraper):
    """Scrape jobs from Andela (talent.andela.com)."""

    def _launch_context(self, playwright, headless: bool):
        return playwright.chromium.launch_persistent_context(
            ANDELA_USER_DATA,
            headless=headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900} if not headless else None,
        )

    @staticmethod
    def _is_logged_in(page) -> bool:
        url = page.url.lower()
        if any(k in url for k in ("login", "signin", "auth", "signup", "sso")):
            return False
        return "talent.andela.com" in url and any(k in url for k in ("jobs", "dashboard", "profile", "opportunities"))

    def _ensure_authenticated(self, playwright):
        """Return (context, page) with authenticated Andela session, or (None, None)."""
        logger.info("Andela Auth [Stage 1]: Visible browser with saved cookies...")
        context = self._launch_context(playwright, headless=False)
        page = context.new_page()
        page.goto(ANDELA_JOBS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        if self._is_logged_in(page):
            logger.info("Andela Auth: ✅ Cookies valid — already logged in!")
            return context, page

        logger.info("Andela Auth [Stage 2]: Please log in at talent.andela.com...")
        page.goto("https://talent.andela.com", wait_until="domcontentloaded", timeout=30000)

        logger.info("🔔 Andela: Log in manually in browser window. Timeout: %ds...", CHALLENGE_TIMEOUT)
        deadline = time.time() + CHALLENGE_TIMEOUT
        last_log = 0
        while time.time() < deadline:
            now = int(time.time())
            if now - last_log >= 10:
                logger.info("Andela Auth: ⏳ Waiting... %ds remaining", int(deadline - time.time()))
                last_log = now
            if self._is_logged_in(page):
                break
            page.wait_for_timeout(2000)
        else:
            logger.error("Andela Auth: ❌ Login not completed within %ds. Aborting.", CHALLENGE_TIMEOUT)
            page.close()
            context.close()
            return None, None

        logger.info("Andela Auth: ✅ Logged in! Cookies saved to %s", ANDELA_USER_DATA)
        page.goto(ANDELA_JOBS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        return context, page

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Andela search: role='%s'", role)
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

                # Wait for Next.js to hydrate and render job cards
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)

                # Scroll to load more
                for _ in range(5):
                    page.mouse.wheel(0, 800)
                    page.wait_for_timeout(800)
                page.mouse.wheel(0, -9999)
                page.wait_for_timeout(1000)

                from bs4 import BeautifulSoup
                content = page.content()

                debug_path = os.path.join(os.getcwd(), "andela_debug.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Andela: HTML dumped → %s", debug_path)

                soup = BeautifulSoup(content, "html.parser")

                all_classes: set[str] = set()
                for el in soup.find_all(class_=True):
                    all_classes.update(el.get("class", []))
                job_classes = sorted(
                    c for c in all_classes
                    if any(k in c.lower() for k in ("job", "card", "opportun", "list", "item", "role", "position"))
                )
                logger.info("Andela: Job-related classes in DOM: %s", job_classes[:40])

                cards = (
                    soup.select("[class*='job-card']")
                    or soup.select("[class*='JobCard']")
                    or soup.select("[class*='job_card']")
                    or soup.select("[class*='opportunit']")
                    or soup.select("[class*='role-card']")
                    or soup.select("[class*='RoleCard']")
                    or soup.select("[class*='position']")
                    or soup.select("[class*='listing']")
                )
                logger.info("Andela: Found %d job cards", len(cards))

                # Extract job IDs / hrefs
                job_entries = []
                seen = set()
                for card in cards:
                    href = ""
                    for a in card.find_all("a", href=True):
                        href = a["href"]
                        break
                    if not href:
                        href = card.get("href", "")

                    full_url = href if href.startswith("http") else f"https://talent.andela.com{href}" if href else ""
                    if full_url in seen or not full_url:
                        continue
                    seen.add(full_url)

                    title_el = card.select_one("h1, h2, h3, h4") or card.select_one("[class*='title'], [class*='Title']")
                    title = title_el.get_text(strip=True) if title_el else ""
                    job_entries.append({"url": full_url, "title": title})

                # Fallback: collect all /jobs/ links
                if not job_entries:
                    logger.warning("Andela: No cards found — extracting /jobs/ links")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/jobs/" in href and href not in seen:
                            seen.add(href)
                            full_url = href if href.startswith("http") else f"https://talent.andela.com{href}"
                            job_entries.append({"url": full_url, "title": a.get_text(strip=True)})

                logger.info("Andela: Processing %d jobs", min(len(job_entries), 25))

                for entry in job_entries[:25]:
                    try:
                        page.goto(entry["url"], wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass
                        page.wait_for_timeout(1500)

                        detail_soup = BeautifulSoup(page.content(), "html.parser")
                        panel = (
                            detail_soup.select_one("[class*='detail']")
                            or detail_soup.select_one("[class*='job-info']")
                            or detail_soup.select_one("main")
                            or detail_soup.body
                        )

                        title_el = panel.select_one("h1") or panel.select_one("h2")
                        title = title_el.get_text(strip=True) if title_el else entry["title"]
                        if not title or len(title) < 3:
                            continue

                        loc_el = panel.select_one("[class*='location'], [class*='Location']")
                        loc_text = loc_el.get_text(strip=True) if loc_el else (location or "Remote")

                        sal_el = panel.select_one("[class*='salary'], [class*='Salary'], [class*='compensation']")
                        salary = sal_el.get_text(strip=True) if sal_el else None

                        skill_els = panel.select("[class*='skill'], [class*='tag'], [class*='Tag'], [class*='Skill']")
                        skills = [s.get_text(strip=True) for s in skill_els if s.get_text(strip=True)]

                        date_el = panel.select_one("[class*='date'], [class*='Date'], [class*='posted'], time")
                        posted_date = date_el.get_text(strip=True) if date_el else None

                        desc_el = (
                            panel.select_one("[class*='description']")
                            or panel.select_one("[class*='Description']")
                            or panel.select_one("[class*='content']")
                        )
                        description = desc_el.get_text("\n", strip=True) if desc_el else panel.get_text("\n", strip=True)[:3000]

                        job_id = hashlib.md5(entry["url"].encode()).hexdigest()[:10]
                        job = Job(
                            id=f"andela_{job_id}",
                            title=title,
                            company="Andela Client",
                            location=loc_text,
                            description=description,
                            skills_required=skills,
                            salary=salary,
                            posted_date=posted_date,
                            platform="andela",
                            application_url=entry["url"],
                            is_remote="remote" in loc_text.lower(),
                            date_found=datetime.now().strftime("%Y-%m-%d"),
                        )
                        jobs.append(job)
                        logger.debug("Andela: Scraped '%s'", title)

                    except Exception as e:
                        logger.error("Andela: Error on %s: %s", entry.get("url"), e)
                        continue

                page.close()
                context.close()

        except Exception as e:
            logger.error("Andela scraper fatal error: %s", e)

        logger.info("Andela scrape complete — %d jobs found", len(jobs))
        return jobs
