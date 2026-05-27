"""Open job URL in Chrome with remote debugging enabled so Claude can control it via DevTools MCP."""

import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from logger import get_logger

logger = get_logger("apply.chrome")

CHROME_DEBUG_PORT = 9222

# macOS Chrome path; falls back to PATH lookup on other platforms
_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium-browser",
    "chromium",
]


def _find_chrome() -> Optional[str]:
    import shutil
    for path in _CHROME_PATHS:
        if Path(path).exists() or shutil.which(path):
            return path
    return None


def _is_chrome_process_running() -> bool:
    try:
        result = subprocess.run(["pgrep", "-f", "Google Chrome"], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def _kill_chrome() -> None:
    try:
        subprocess.run(["pkill", "-f", "Google Chrome"], capture_output=True)
        import time as _t
        _t.sleep(1.5)
    except Exception:
        pass


def _launch_debug_chrome(url: str) -> bool:
    """Launch Chrome with remote debugging port. Kills existing Chrome first on macOS."""
    chrome = _find_chrome()
    if not chrome:
        logger.warning("Chrome binary not found; falling back to webbrowser")
        return False

    if _is_chrome_process_running():
        logger.info("Existing Chrome running without debug port — restarting")
        _kill_chrome()

    cmd = [chrome, f"--remote-debugging-port={CHROME_DEBUG_PORT}", "--no-first-run", "--no-default-browser-check"]
    if url:
        cmd.append(url)
    logger.info("Launching Chrome (debug port %d)", CHROME_DEBUG_PORT)
    try:
        subprocess.Popen(cmd)
        return True
    except Exception as e:
        logger.error("Chrome launch failed: %s", e)
        return False


def _is_chrome_debug_running() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://localhost:{CHROME_DEBUG_PORT}/json", timeout=1)
        return True
    except Exception:
        return False


def _open_tab_in_existing_chrome(url: str) -> bool:
    """Open a new tab in the already-running Chrome debug instance."""
    import urllib.request, urllib.error, json
    try:
        data = json.dumps({"url": url}).encode()
        req = urllib.request.Request(
            f"http://localhost:{CHROME_DEBUG_PORT}/json/new",
            data=data,
            method="PUT",
        )
        urllib.request.urlopen(req, timeout=3)
        logger.info("Opened new tab in existing Chrome: %s", url)
        return True
    except Exception as e:
        logger.warning("Failed to open tab in existing Chrome: %s", e)
        return False


def launch_and_stage(
    job_url: str,
    resume_path: Optional[Path] = None,
    job: Optional[dict] = None,
) -> dict:
    """
    Open job URL in Chrome. Prefers attaching to an existing Chrome instance
    (with logged-in session) via debug port. Falls back to launching a new Chrome
    with remote debugging, then webbrowser.open as last resort.
    """
    company = (job or {}).get("Company", "?")
    role = (job or {}).get("Role", "?")
    logger.info("Opening application URL for %s @ %s: %s", role, company, job_url)

    if not _is_chrome_debug_running():
        logger.info("Chrome not on debug port — launching now")
        launched = _launch_debug_chrome("")
        if not launched:
            logger.info("Chrome binary not found; falling back to webbrowser.open")
            try:
                webbrowser.open(job_url)
            except Exception as e:
                logger.error("webbrowser.open failed: %s", e)
                return {"status": "failed", "reason": str(e), "staged_fields": []}
            return {"status": "staged", "staged_fields": [], "resume_uploaded": False, "debug_port": None, "reason": "Opened via system browser"}
        # Wait up to 20s for Chrome debug port
        import time as _time
        for attempt in range(40):
            _time.sleep(0.5)
            if _is_chrome_debug_running():
                logger.info("Chrome ready after %.1fs", (attempt + 1) * 0.5)
                break
        else:
            logger.warning("Chrome launched but debug port not ready; opening via webbrowser")
            webbrowser.open(job_url)
            return {"status": "staged", "staged_fields": [], "resume_uploaded": False, "debug_port": None, "reason": "Chrome debug port not ready; opened via system browser"}

    logger.info("Chrome ready on port %d — opening tab for %s @ %s", CHROME_DEBUG_PORT, role, company)
    _open_tab_in_existing_chrome(job_url)
    return {
        "status": "staged",
        "staged_fields": [],
        "resume_uploaded": False,
        "debug_port": CHROME_DEBUG_PORT,
        "reason": f"Opened in Chrome (debug port {CHROME_DEBUG_PORT})",
    }
