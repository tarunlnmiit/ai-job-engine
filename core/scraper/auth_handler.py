import os
import time
from pathlib import Path
from logger import get_logger

logger = get_logger("scraper.auth")

CHALLENGE_TIMEOUT = 120


def get_cookies_path(user_data_dir: str) -> str:
    """Get path to cookies.json in user data directory."""
    cookies_path = Path(user_data_dir) / "cookies.json"
    return str(cookies_path)


def has_saved_cookies(user_data_dir: str) -> bool:
    """Check if cookies.json exists and is valid."""
    cookies_path = Path(user_data_dir) / "cookies.json"
    return cookies_path.exists() and cookies_path.stat().st_size > 10


def load_cookies(user_data_dir: str) -> list | None:
    """Load cookies from file."""
    try:
        import json
        cookies_path = Path(user_data_dir) / "cookies.json"
        if cookies_path.exists():
            with open(cookies_path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Failed to load cookies: %s", e)
    return None


def save_cookies(context, user_data_dir: str):
    """Save cookies from browser context to file."""
    try:
        import json
        cookies = context.cookies()
        user_data_path = Path(user_data_dir)
        user_data_path.mkdir(parents=True, exist_ok=True)
        cookies_path = user_data_path / "cookies.json"
        with open(cookies_path, "w") as f:
            json.dump(cookies, f)
        logger.info("Cookies saved to %s", cookies_path)
    except Exception as e:
        logger.warning("Failed to save cookies: %s", e)


def get_env_creds(platform: str) -> tuple[str, str] | None:
    """Get credentials from .env for platform. Returns (email, password) or None."""
    email_key = f"{platform.upper()}_EMAIL"
    password_key = f"{platform.upper()}_PASSWORD"

    email = os.getenv(email_key)
    password = os.getenv(password_key)

    if email and password:
        logger.info("Found .env credentials for %s", platform)
        return email, password

    return None


class SyncAuthHandler:
    """Handle 3-stage sync authentication: cookies → .env → manual."""

    def __init__(self, platform: str, user_data_dir: str, login_url: str, check_fn):
        """
        Args:
            platform: Platform name (uplers, andela, turing)
            user_data_dir: Directory for persistent cookies
            login_url: URL to navigate for login
            check_fn: Callable(page) → bool indicating if logged in
        """
        self.platform = platform
        self.user_data_dir = user_data_dir
        self.login_url = login_url
        self.check_fn = check_fn

    def authenticate(self, playwright, launch_context_fn) -> tuple:
        """
        Execute 3-stage auth. Returns (context, page) or (None, None) on failure.

        Args:
            playwright: Playwright instance
            launch_context_fn: Callable(playwright, headless: bool) → context
        """
        # Stage 1: Try saved cookies (headless)
        logger.info("%s Auth [Stage 1]: Checking saved cookies...", self.platform)
        context = launch_context_fn(playwright, headless=True)
        page = context.new_page()
        try:
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            if self.check_fn(page):
                logger.info("%s Auth: ✅ Cookies valid", self.platform)
                return context, page

            page.close()
            context.close()
        except Exception as e:
            logger.warning("%s Stage 1 error: %s", self.platform, e)
            try:
                page.close()
                context.close()
            except:
                pass

        # Stage 2: Try .env credentials (headless)
        logger.info("%s Auth [Stage 2]: Checking .env credentials...", self.platform)
        creds = get_env_creds(self.platform)
        if creds:
            email, password = creds
            context = launch_context_fn(playwright, headless=True)
            page = context.new_page()
            try:
                page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)

                # Try to fill email/password fields
                email_inputs = page.query_selector_all("input[type='email'], input[name*='email' i], input[id*='email' i]")
                password_inputs = page.query_selector_all("input[type='password']")

                if email_inputs and password_inputs:
                    logger.info("%s: Attempting login with .env credentials...", self.platform)
                    email_inputs[0].fill(email)
                    password_inputs[0].fill(password)

                    # Look for submit button
                    submit = page.query_selector("button[type='submit'], button:has-text('Log in'), button:has-text('Sign in')")
                    if submit:
                        submit.click()
                    else:
                        password_inputs[0].press("Enter")

                    # Wait for nav + check
                    try:
                        page.wait_for_load_state("networkidle", timeout=30000)
                    except:
                        pass
                    page.wait_for_timeout(4000)

                    if self.check_fn(page):
                        logger.info("%s Auth: ✅ Logged in with .env credentials", self.platform)
                        save_cookies(context, self.user_data_dir)
                        return context, page

                page.close()
                context.close()
            except Exception as e:
                logger.warning("%s Stage 2 error: %s", self.platform, e)
                try:
                    page.close()
                    context.close()
                except:
                    pass

        # Stage 3: Manual login (headless=False)
        logger.info("%s Auth [Stage 3]: Opening visible browser for manual login...", self.platform)
        context = launch_context_fn(playwright, headless=False)
        page = context.new_page()

        try:
            page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
            logger.info("🔔 %s: Log in manually in the browser window. Timeout: %ds", self.platform, CHALLENGE_TIMEOUT)

            deadline = time.time() + CHALLENGE_TIMEOUT
            last_log = 0
            while time.time() < deadline:
                now = int(time.time())
                if now - last_log >= 10:
                    logger.info("%s Auth: ⏳ Waiting... %ds remaining", self.platform, int(deadline - time.time()))
                    last_log = now

                if self.check_fn(page):
                    logger.info("%s Auth: ✅ Manual login successful", self.platform)
                    save_cookies(context, self.user_data_dir)
                    return context, page

                page.wait_for_timeout(2000)

            logger.error("%s Auth: ❌ Manual login timeout (%ds)", self.platform, CHALLENGE_TIMEOUT)
            page.close()
            context.close()
            return None, None

        except Exception as e:
            logger.error("%s Stage 3 error: %s", self.platform, e)
            try:
                page.close()
                context.close()
            except:
                pass
            return None, None


class AsyncAuthHandler:
    """Handle 3-stage async authentication: cookies → .env → manual."""

    def __init__(self, platform: str, user_data_dir: str, login_url: str, check_fn):
        """
        Args:
            platform: Platform name (braintrust, arc_dev, mercor)
            user_data_dir: Directory for persistent cookies
            login_url: URL to navigate for login
            check_fn: Async callable(page) → bool indicating if logged in
        """
        self.platform = platform
        self.user_data_dir = user_data_dir
        self.login_url = login_url
        self.check_fn = check_fn

    async def authenticate(self, playwright, launch_context_fn) -> tuple:
        """
        Execute 3-stage auth. Returns (context, page) or (None, None) on failure.

        Args:
            playwright: Async playwright instance
            launch_context_fn: Async callable(playwright, headless: bool) → context
        """
        # Stage 1: Try saved cookies (headless)
        logger.info("%s Auth [Stage 1]: Checking saved cookies...", self.platform)
        context = await launch_context_fn(playwright, headless=True)
        page = await context.new_page()
        try:
            await page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            if await self.check_fn(page):
                logger.info("%s Auth: ✅ Cookies valid", self.platform)
                return context, page

            await page.close()
            await context.close()
        except Exception as e:
            logger.warning("%s Stage 1 error: %s", self.platform, e)
            try:
                await page.close()
                await context.close()
            except:
                pass

        # Stage 2: Try .env credentials (headless)
        logger.info("%s Auth [Stage 2]: Checking .env credentials...", self.platform)
        creds = get_env_creds(self.platform)
        if creds:
            email, password = creds
            context = await launch_context_fn(playwright, headless=True)
            page = await context.new_page()
            try:
                await page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)

                # Try to fill email/password fields
                email_inputs = await page.query_selector_all("input[type='email'], input[name*='email' i], input[id*='email' i]")
                password_inputs = await page.query_selector_all("input[type='password']")

                if email_inputs and password_inputs:
                    logger.info("%s: Attempting login with .env credentials...", self.platform)
                    await email_inputs[0].fill(email)
                    await password_inputs[0].fill(password)

                    # Look for submit button
                    submit = await page.query_selector("button[type='submit'], button:has-text('Log in'), button:has-text('Sign in')")
                    if submit:
                        await submit.click()
                    else:
                        await password_inputs[0].press("Enter")

                    # Wait for nav + check
                    try:
                        await page.wait_for_load_state("networkidle", timeout=30000)
                    except:
                        pass
                    await page.wait_for_timeout(4000)

                    if await self.check_fn(page):
                        logger.info("%s Auth: ✅ Logged in with .env credentials", self.platform)
                        save_cookies(context, self.user_data_dir)
                        return context, page

                await page.close()
                await context.close()
            except Exception as e:
                logger.warning("%s Stage 2 error: %s", self.platform, e)
                try:
                    await page.close()
                    await context.close()
                except:
                    pass

        # Stage 3: Manual login (headless=False)
        logger.info("%s Auth [Stage 3]: Opening visible browser for manual login...", self.platform)
        context = await launch_context_fn(playwright, headless=False)
        page = await context.new_page()

        try:
            await page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
            logger.info("🔔 %s: Log in manually in the browser window. Timeout: %ds", self.platform, CHALLENGE_TIMEOUT)

            deadline = time.time() + CHALLENGE_TIMEOUT
            last_log = 0
            while time.time() < deadline:
                now = int(time.time())
                if now - last_log >= 10:
                    logger.info("%s Auth: ⏳ Waiting... %ds remaining", self.platform, int(deadline - time.time()))
                    last_log = now

                if await self.check_fn(page):
                    logger.info("%s Auth: ✅ Manual login successful", self.platform)
                    save_cookies(context, self.user_data_dir)
                    return context, page

                await page.wait_for_timeout(2000)

            logger.error("%s Auth: ❌ Manual login timeout (%ds)", self.platform, CHALLENGE_TIMEOUT)
            await page.close()
            await context.close()
            return None, None

        except Exception as e:
            logger.error("%s Stage 3 error: %s", self.platform, e)
            try:
                await page.close()
                await context.close()
            except:
                pass
            return None, None
