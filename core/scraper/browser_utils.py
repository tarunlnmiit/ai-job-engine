import os
import requests
from playwright.sync_api import sync_playwright, BrowserContext
from playwright.async_api import async_playwright, BrowserContext as AsyncBrowserContext
import logging

logger = logging.getLogger(__name__)

def get_browser_context(p, headless=False) -> BrowserContext:
    """
    Returns a playwright sync browser context.
    Attempts to connect to an existing Chrome instance on port 9222 first.
    """
    try:
        # Check if Chrome is running on port 9222
        resp = requests.get("http://localhost:9222/json/version", timeout=2)
        if resp.status_code == 200:
            logger.info("Connecting to existing Chrome instance on port 9222...")
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            # Connect usually returns a browser with contexts already present
            if browser.contexts:
                return browser.contexts[0]
            return browser.new_context()
    except Exception as e:
        logger.debug(f"Could not connect to existing Chrome: {e}")

    # Fallback: Launch a new persistent context
    logger.info("Launching new persistent Chrome context...")
    user_data_dir = os.path.join(os.getcwd(), "chrome_user_data")
    return p.chromium.launch_persistent_context(
        user_data_dir,
        headless=headless,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled"
        ],
        ignore_default_args=["--enable-automation"]
    )

async def get_async_browser_context(p, headless=False) -> AsyncBrowserContext:
    """
    Returns a playwright async browser context.
    Attempts to connect to an existing Chrome instance on port 9222 first.
    """
    try:
        # Check if Chrome is running on port 9222
        # Use a simple check or just try to connect
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        logger.info("Connected to existing Chrome instance on port 9222 (Async)")
        if browser.contexts:
            return browser.contexts[0]
        return await browser.new_context()
    except Exception as e:
        logger.debug(f"Could not connect to existing Chrome (Async): {e}")

    # Fallback
    logger.info("Launching new persistent Chrome context (Async)...")
    user_data_dir = os.path.join(os.getcwd(), "chrome_user_data")
    return await p.chromium.launch_persistent_context(
        user_data_dir,
        headless=headless,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled"
        ],
        ignore_default_args=["--enable-automation"]
    )
