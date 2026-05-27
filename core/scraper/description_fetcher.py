"""Fetch missing job descriptions by visiting application URLs."""

import re
import subprocess
import shutil
from typing import Optional, Tuple
from logger import get_logger

logger = get_logger("scraper.description_fetcher")

_SKIP_PLATFORMS = {"linkedin", "naukri", "instahyre"}

_EXTRACT_PROMPT = """Extract the job description from this HTML page.
Return ONLY the job description text: responsibilities, requirements, about the role, qualifications.
No HTML tags. No JSON. Plain text only.
If no job description is found, return exactly: NO_DESCRIPTION_FOUND

HTML:
{html}"""

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

_PERM_FAIL_CODES = {404, 410, 403, 401}
_MIN_USEFUL_LEN = 500


def _fetch_html_requests(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str], bool]:
    """Fetch via requests. Returns (html, error_msg, is_permanent_failure)."""
    try:
        import requests
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if 200 <= resp.status_code < 300:
            return resp.text, None, False
        is_perm = resp.status_code in _PERM_FAIL_CODES
        return None, f"HTTP {resp.status_code}", is_perm
    except Exception as e:
        return None, str(e), False


def _fetch_html_playwright(url: str, timeout: int = 20) -> Tuple[Optional[str], Optional[str], bool]:
    """Fetch via headless Chromium, waits for network idle."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page(
                user_agent=_HEADERS["User-Agent"],
                extra_http_headers={"Accept-Language": _HEADERS["Accept-Language"]},
            )
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                if resp and resp.status in _PERM_FAIL_CODES:
                    browser.close()
                    return None, f"HTTP {resp.status}", True
                html = page.content()
            except PWTimeout:
                html = page.content()
            finally:
                browser.close()
        return html, None, False
    except Exception as e:
        return None, f"playwright: {e}", False


def _fetch_html(url: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str], bool]:
    """Fetch page HTML, falling back to Playwright for JS-rendered pages."""
    html, err, is_perm = _fetch_html_requests(url, timeout)

    # Hard failure (network error or permanent HTTP error) — no point trying Playwright
    if html is None and is_perm:
        return html, err, is_perm

    # Sparse or missing body — JS-rendered or empty 2xx; try Playwright
    visible_len = len(_extract_visible_text(html)) if html else 0
    if visible_len < _MIN_USEFUL_LEN:
        logger.debug("requests sparse (len=%d), trying Playwright for %s", visible_len, url)
        pw_html, pw_err, pw_perm = _fetch_html_playwright(url, timeout)
        if pw_html:
            return pw_html, None, False
        logger.debug("Playwright also failed for %s: %s", url, pw_err)
        # Both methods failed or returned empty — normalise to None so callers
        # get a clean (None, reason, is_perm) instead of ("", None, False)
        if not html:
            return None, err or pw_err, is_perm or pw_perm

    return html, err, is_perm


def _extract_visible_text(html: str) -> str:
    """Strip scripts/styles and return visible text, truncated to 8000 chars."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l for l in text.splitlines() if l.strip()]
        return "\n".join(lines)[:8000]
    except Exception:
        return html[:8000]


def _call_claude(text: str, model: str = "claude-haiku-4-5-20251001") -> Optional[str]:
    """Use Claude CLI subprocess to extract description from page text."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        logger.error("claude CLI not found")
        return None

    prompt = _EXTRACT_PROMPT.format(html=text)
    try:
        result = subprocess.run(
            [claude_bin, "-p", prompt, "--model", model],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("Claude exited %d: %s", result.returncode, result.stderr[:200])
            return None
        output = _ANSI_RE.sub('', result.stdout).strip()
        if not output:
            logger.warning("Claude returned empty output (stderr: %s)", result.stderr[:200])
            return None
        if output == "NO_DESCRIPTION_FOUND":
            logger.warning("Claude: NO_DESCRIPTION_FOUND (input_len=%d)", len(text))
            return None
        return output
    except subprocess.TimeoutExpired:
        logger.warning("Claude timed out for description extraction")
        return None
    except Exception as e:
        logger.error("Claude subprocess error: %s", e)
        return None


def fetch_description(job: dict) -> Tuple[Optional[str], str]:
    """
    Fetch description for a job by visiting its URL.
    Returns (description_text, status) where status is one of:
      'ok', 'skipped', 'no_url', 'fetch_failed', 'perm_failed', 'extract_failed'
    'perm_failed' = HTTP 4xx that won't recover (404, 410, 403, 401).
    """
    platform = (job.get("platform") or "").lower()
    if platform in _SKIP_PLATFORMS:
        return None, "skipped"

    url = job.get("application_url") or ""
    if not url or not url.startswith("http"):
        return None, "no_url"

    html, err, is_perm = _fetch_html(url)
    if not html:
        logger.warning("Failed to fetch %s: %s", url, err)
        return None, "perm_failed" if is_perm else "fetch_failed"

    visible = _extract_visible_text(html)
    if len(visible) < 200:
        logger.warning("Page too sparse to extract: %s (visible_len=%d)", url, len(visible))
        return None, "fetch_failed"

    description = _call_claude(visible)
    if description:
        return description, "ok"

    # Claude got content but found no job description — likely JS shell with nav text.
    # Retry once with Playwright to get the fully-rendered page.
    logger.debug("No description from requests HTML, retrying with Playwright: %s", url)
    pw_html, pw_err, pw_perm = _fetch_html_playwright(url)
    if pw_html:
        pw_visible = _extract_visible_text(pw_html)
        if len(pw_visible) >= 200:
            description = _call_claude(pw_visible)
            if description:
                return description, "ok"
            # Playwright got real content but still no job description found
            logger.warning("No job description found (post-Playwright) for %s", url)
            return None, "no_desc"

    logger.warning("Extraction failed for %s", url)
    return None, "extract_failed"
