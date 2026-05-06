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

logger = get_logger("scraper.wellfound")

BASE_URL = "https://wellfound.com"


class WellfoundScraper(BaseJobScraper):
    """Scrape jobs from Wellfound (formerly AngelList) using Playwright."""

    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        logger.info("Wellfound search: role='%s' location='%s'", role, location)

        if not PLAYWRIGHT_AVAILABLE or not BS_AVAILABLE:
            logger.error("Playwright or BeautifulSoup not installed.")
            return []

        return self._search_playwright(role, location)

    def _search_playwright(self, role: str, location: str) -> list[Job]:
        """Scrape Wellfound search results using Playwright."""
        jobs = []

        try:
            from .browser_utils import get_browser_context
            with sync_playwright() as p:
                context = get_browser_context(p, headless=False)
                page = context.pages[0] if context.pages else context.new_page()

                try:
                    from playwright_stealth import stealth_sync
                    stealth_sync(page)
                    logger.info("Stealth mode enabled for Wellfound scraper")
                except ImportError:
                    pass

                # Build search URL — Wellfound uses ?q= for role, &remote=true for remote
                params = f"q={role.replace(' ', '+')}"
                # Check if remote-only filter should be applied
                is_remote_search = not location or location.lower() in ("remote", "")
                if is_remote_search:
                    params += "&remote=true"
                elif location:
                    params += f"&location={location.replace(' ', '+')}"

                url = f"{BASE_URL}/jobs?{params}"
                logger.debug("Fetching Wellfound URL: %s", url)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)

                    # Wait for job cards to render — they have Apply buttons once loaded
                    page.wait_for_selector(
                        "[data-test='JobApplicationApplyButton']",
                        timeout=20000
                    )
                    page.wait_for_timeout(random.uniform(1500, 2500))
                    logger.debug("Wellfound page loaded: %s", page.title())
                except Exception as e:
                    logger.warning("Wellfound page load issue: %s", e)

                html = page.content()
                page_jobs = self._parse_html(html)
                logger.info("Wellfound: found %d jobs", len(page_jobs))
                jobs.extend(page_jobs)

                page.close()

        except Exception as e:
            logger.error("Wellfound Playwright scrape failed: %s", e, exc_info=True)

        logger.info("Wellfound scrape complete — %d jobs collected", len(jobs))
        return jobs

    def _parse_html(self, html: str) -> list[Job]:
        """Parse Wellfound job listing page."""
        soup = BeautifulSoup(html, "html.parser")

        # Job cards: divs containing a /jobs/ link and a /company/ link
        # They share the pattern: border-b border-gray-400 py-3
        job_cards = soup.find_all(
            "div",
            class_=lambda c: c and "border-b" in c and "border-gray-400" in c and "py-3" in c
        )
        logger.debug("Wellfound parser: found %d candidate job cards", len(job_cards))

        jobs = []
        seen_ids = set()
        for card in job_cards:
            try:
                job = self._parse_card(card)
                if job and job.id not in seen_ids:
                    seen_ids.add(job.id)
                    jobs.append(job)
            except Exception as e:
                logger.warning("Error parsing Wellfound card: %s", e)
                continue

        return jobs

    def _parse_card(self, card) -> Job | None:
        # Job title + URL: first <a href="/jobs/...">
        job_link = card.find("a", href=lambda h: h and h.startswith("/jobs/"))
        if not job_link:
            return None

        title = job_link.get_text(strip=True)
        job_path = job_link["href"]
        job_url = f"{BASE_URL}{job_path}"
        # Extract numeric ID from path like /jobs/4163194-mid-market-account-executive
        job_id_part = job_path.split("/jobs/")[-1].split("-")[0]
        job_id = f"wellfound_{job_id_part}"

        # Company: <a href="/company/..."> for the logo, or text in the metadata line
        company_link = card.find("a", href=lambda h: h and h.startswith("/company/"))
        if company_link:
            company_img = company_link.find("img")
            if company_img and company_img.get("alt"):
                # "Postman company logo" -> "Postman"
                company = company_img["alt"].replace(" company logo", "").strip()
            else:
                company = company_link.get_text(strip=True)
        else:
            company = "Unknown"

        # Metadata line: "CompanyName • Remote • $180k – $230k • today"
        # It's in a small <div class="text-sm"> containing multiple <span>s
        meta_div = card.find("div", class_=lambda c: c and "text-sm" in c)
        location_text = "Remote"
        salary = None
        posted_date = None

        if meta_div:
            full_meta = meta_div.get_text(separator=" ", strip=True)
            # Split by bullet "•"
            parts = [p.strip() for p in full_meta.replace("•", "|").split("|") if p.strip()]
            # parts[0] = company name, parts[1] = location, parts[2] = salary, parts[3] = date
            if len(parts) >= 2:
                location_text = parts[1].strip()
            if len(parts) >= 3:
                # Could be salary or date — salary contains "$" or "k"
                for part in parts[2:]:
                    if "$" in part or "k" in part.lower():
                        salary = part.strip()
                    elif any(kw in part.lower() for kw in ("today", "day", "hour", "week", "month", "ago")):
                        posted_date = part.strip()

        is_remote = "remote" in location_text.lower()

        return Job(
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
