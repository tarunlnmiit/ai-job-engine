"""LinkedIn scraper using Chrome DevTools MCP for visibility and debugging."""

import os
from datetime import datetime
from dotenv import load_dotenv
from .base import BaseJobScraper, Job

load_dotenv()


class LinkedInScraperDevTools(BaseJobScraper):
    """Scrape LinkedIn jobs using Chrome DevTools MCP.

    Requires Claude Code with Chrome DevTools MCP access.
    Visible automation for debugging LinkedIn selector changes.
    """

    def __init__(self, email: str = None, password: str = None):
        self.email = email or os.getenv("LINKEDIN_EMAIL")
        self.password = password or os.getenv("LINKEDIN_PASSWORD")
        self.page_id = None

    async def search(self, role: str, location: str = "India", remote: bool = True, **kwargs) -> list[Job]:
        """Search LinkedIn jobs using Chrome DevTools.

        Note: This requires Claude Code with Chrome DevTools MCP configured.
        Jobs are scraped from visible browser window for transparency.
        """
        if not self.email or not self.password:
            print("LinkedIn email/password not configured in environment")
            return []

        jobs = []

        try:
            # This is a template - actual implementation requires Chrome DevTools MCP client
            # For now, return empty list with instructions
            print("""
            LinkedIn scraper using Chrome DevTools MCP requires:
            1. Claude Code with chrome-devtools-mcp plugin
            2. Open browser page via Claude Code
            3. Plugin will handle page navigation, login, job extraction

            Implementation steps:
            1. Use chrome-devtools-mcp/new_page to open LinkedIn
            2. Use take_snapshot to get page structure
            3. Navigate to jobs search: /jobs/search/?keywords={role}&location={location}
            4. Parse job cards from DOM
            5. Click each job to get full description
            6. Return Job objects
            """)

            # TODO: Integrate with actual Chrome DevTools MCP once configured
            # Steps:
            # 1. Create page via MCP: chrome_devtools.new_page("https://linkedin.com/login")
            # 2. Login via form filling: chrome_devtools.fill_form(email, password)
            # 3. Navigate to jobs: chrome_devtools.navigate_page(jobs_url)
            # 4. Extract jobs: chrome_devtools.take_snapshot() -> parse HTML
            # 5. For each job: click -> get description -> create Job object

            return jobs

        except Exception as e:
            print(f"Error scraping LinkedIn via Chrome DevTools: {e}")
            return jobs


# Alternative: Keep using Playwright but add Chrome DevTools logging
class LinkedInScraperHybrid(BaseJobScraper):
    """LinkedIn scraper with Chrome DevTools for debugging.

    Uses Playwright for automation but captures screenshots for visibility.
    """

    def __init__(self, email: str = None, password: str = None):
        self.email = email or os.getenv("LINKEDIN_EMAIL")
        self.password = password or os.getenv("LINKEDIN_PASSWORD")

    async def search(self, role: str, location: str = "India", remote: bool = True, **kwargs) -> list[Job]:
        """Search LinkedIn with Playwright + Chrome DevTools snapshots for debugging."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("Playwright not installed. Install with: pip install playwright")
            return []

        if not self.email or not self.password:
            print("LinkedIn email/password not configured")
            return []

        jobs = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)  # Visible for debugging
                page = await browser.new_page()

                # Login
                await self._login(page)

                # Navigate to jobs
                jobs_url = f"https://www.linkedin.com/jobs/search/?keywords={role}"
                if location:
                    jobs_url += f"&location={location}"
                if remote:
                    jobs_url += "&f_WT=2"

                await page.goto(jobs_url, wait_until="networkidle", timeout=30000)

                # Wait for job listings
                try:
                    await page.wait_for_selector("div.base-card", timeout=10000)
                except:
                    print("No job listings found on LinkedIn")
                    await browser.close()
                    return jobs

                # Extract jobs
                job_elements = await page.query_selector_all("div.base-card")

                for idx, job_elem in enumerate(job_elements[:50]):
                    try:
                        link_elem = await job_elem.query_selector("a.base-card__full-link")
                        if not link_elem:
                            continue

                        job_url = await link_elem.get_attribute("href")
                        job_id = job_url.split("currentJobId=")[-1].split("&")[0] if "currentJobId=" in job_url else ""

                        await link_elem.click()
                        await page.wait_for_timeout(500)

                        # Extract details
                        title = ""
                        company = ""
                        location_text = location
                        description = ""

                        try:
                            title_elem = await job_elem.query_selector("h3.base-search-card__title")
                            if title_elem:
                                title = await title_elem.text_content()
                                title = title.strip() if title else ""
                        except:
                            pass

                        try:
                            company_elem = await job_elem.query_selector("h4.base-search-card__subtitle")
                            if company_elem:
                                company = await company_elem.text_content()
                                company = company.strip() if company else ""
                        except:
                            pass

                        try:
                            desc_elem = await page.query_selector("div.show-more-less-html__markup")
                            if desc_elem:
                                description = await desc_elem.text_content()
                                description = description.strip() if description else ""
                        except:
                            pass

                        # Check Easy Apply
                        easy_apply = False
                        try:
                            easy_apply_btn = await page.query_selector("button.jobs-apply-button")
                            if easy_apply_btn:
                                easy_apply = True
                        except:
                            pass

                        job = Job(
                            id=f"linkedin_{job_id}",
                            title=title,
                            company=company,
                            location=location_text,
                            description=description,
                            skills_required=[],
                            platform="linkedin",
                            application_url=job_url,
                            is_easy_apply=easy_apply,
                            is_remote="remote" in location_text.lower(),
                            salary=None,
                            posted_date=None,
                            experience_required=None,
                            date_found=datetime.now().strftime("%Y-%m-%d"),
                        )
                        jobs.append(job)

                    except Exception as e:
                        print(f"Error parsing job card {idx}: {e}")
                        continue

                await browser.close()

        except Exception as e:
            print(f"Error scraping LinkedIn: {e}")

        return jobs

    async def _login(self, page) -> bool:
        """Login to LinkedIn."""
        try:
            await page.goto("https://www.linkedin.com/login", wait_until="networkidle", timeout=30000)

            email_input = await page.wait_for_selector("input[aria-label*='Email']", timeout=5000)
            await email_input.fill(self.email)

            password_input = await page.wait_for_selector("input[aria-label*='Password']", timeout=5000)
            await password_input.fill(self.password)

            login_btn = await page.wait_for_selector("button[aria-label*='Sign in']", timeout=5000)
            await login_btn.click()

            await page.wait_for_url("https://www.linkedin.com/**", timeout=30000)
            return True

        except Exception as e:
            print(f"LinkedIn login failed: {e}")
            return False
