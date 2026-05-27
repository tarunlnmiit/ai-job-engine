"""
Generic job application automation using Playwright.

Opens Chrome with remote debugging (port 9222) so Claude can also control
the same session via chrome-devtools-mcp if the automation gets stuck.

Flow:
  apply_job() → navigates → finds Apply button → clicks → fills form
              → returns "applied" | "needs_input" | "manual_required" | "failed"

On "needs_input": Streamlit shows a dialog, user provides answer, caller
passes it back via extra_inputs on the next call. Browser stays open between
calls (persistent context) so we resume on the current page.
"""

import asyncio
import re
from pathlib import Path
from typing import Optional
from logger import get_logger

logger = get_logger("apply.auto")

CHROME_DEBUG_PORT = 9222
BROWSER_SESSION_DIR = Path("data/browser_session")

# ---------------------------------------------------------------------------
# Candidate profile — used to pre-fill form fields
# ---------------------------------------------------------------------------
PROFILE: dict[str, str] = {
    "first_name": "Tarun",
    "last_name": "Gupta",
    "full_name": "Tarun Gupta",
    "email": "tarungupta.medium@gmail.com",
    "phone": "+91-9876543210",
    "linkedin": "https://www.linkedin.com/in/tarunlnmiit",
    "website": "https://tarunlnmiit.github.io",
    "city": "New Delhi",
    "country": "India",
    "years_experience": "5",
    "current_title": "Senior Software Engineer",
    "notice_period": "Immediate",
}

# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------
APPLY_SELECTORS = [
    # LinkedIn
    "button[aria-label*='Easy Apply']",
    ".jobs-apply-button",
    # Greenhouse
    "#apply_button",
    "a#apply",
    # Lever
    ".template-btn-submit",
    # Workday
    "a[data-automation-id='applyNowButton']",
    # Generic text matches (Playwright :text is exact; use has-text)
    "button:has-text('Easy Apply')",
    "button:has-text('Apply Now')",
    "button:has-text('Apply now')",
    "a:has-text('Apply Now')",
    "a:has-text('Apply now')",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
]

NEXT_SELECTORS = [
    "button[aria-label*='Continue to next step']",
    "button[aria-label*='Continue']",
    "button[aria-label*='Next']",
    "button[aria-label*='Review']",
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "button:has-text('Review')",
]

SUBMIT_SELECTORS = [
    "button[aria-label*='Submit application']",
    "button[aria-label*='Submit']",
    "button:has-text('Submit application')",
    "button:has-text('Submit Application')",
    "button:has-text('Submit')",
    "input[type='submit']",
    "[type='submit']",
]

SUCCESS_SELECTORS = [
    "text=Application submitted",
    "text=Application sent",
    "text=You've applied",
    "text=You applied",
    "text=Successfully applied",
    "text=Your application has been submitted",
    "text=Thanks for applying",
    "text=application was submitted",
    ".artdeco-inline-feedback--success",        # LinkedIn
    "[data-testid*='confirmation']",
    ".application-confirmation",
]

# Map label/name keywords to PROFILE keys
_FIELD_KEY_MAP = {
    "first": "first_name",
    "fname": "first_name",
    "last": "last_name",
    "lname": "last_name",
    "name": "full_name",
    "email": "email",
    "phone": "phone",
    "mobile": "phone",
    "tel": "phone",
    "linkedin": "linkedin",
    "website": "website",
    "portfolio": "website",
    "city": "city",
    "location": "city",
    "country": "country",
    "experience": "years_experience",
    "years": "years_experience",
    "title": "current_title",
    "position": "current_title",
    "notice": "notice_period",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile_value_for(label: str, name: str, placeholder: str) -> Optional[str]:
    """Return a profile value that best matches this field's label/name/placeholder."""
    text = f"{label} {name} {placeholder}".lower()
    # Normalize: remove special chars
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    for keyword, profile_key in _FIELD_KEY_MAP.items():
        if keyword in text:
            return PROFILE.get(profile_key)
    return None


async def _get_field_label(page, el) -> str:
    """Try to find the human-readable label for an input element."""
    try:
        # Check aria-label
        aria = await el.get_attribute("aria-label") or ""
        if aria.strip():
            return aria.strip()
        # Check associated <label> via id
        el_id = await el.get_attribute("id") or ""
        if el_id:
            label_el = await page.query_selector(f"label[for='{el_id}']")
            if label_el:
                return (await label_el.inner_text()).strip()
        # Check placeholder
        ph = await el.get_attribute("placeholder") or ""
        if ph.strip():
            return ph.strip()
        # Check name
        name = await el.get_attribute("name") or ""
        return name.strip()
    except Exception:
        return ""


async def _is_success(page) -> bool:
    for sel in SUCCESS_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                logger.info("Success signal found: %s", sel)
                return True
        except Exception:
            pass
    return False


async def _click_first(page, selectors: list[str], label: str = "") -> bool:
    """Click the first matching selector. Returns True if clicked."""
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                logger.info("Clicking %s via: %s", label or "button", sel)
                await el.click()
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Form filler
# ---------------------------------------------------------------------------

async def _fill_form_step(
    page,
    resume_path: Optional[Path],
    extra_inputs: dict,
) -> Optional[dict]:
    """
    Fill all visible form inputs on the current page step.

    Returns None if all fields satisfied, or a needs_input dict for the first
    required field that can't be auto-filled.
    """
    await page.wait_for_timeout(800)

    # --- File inputs (resume upload) ---
    file_inputs = await page.query_selector_all("input[type='file']")
    for fi in file_inputs:
        if resume_path and resume_path.exists():
            try:
                await fi.set_input_files(str(resume_path))
                logger.info("Uploaded resume: %s", resume_path.name)
            except Exception as e:
                logger.warning("Resume upload failed: %s", e)

    # --- Text / email / tel / number inputs ---
    text_inputs = await page.query_selector_all(
        "input[type='text'], input[type='email'], input[type='tel'], "
        "input[type='number'], input:not([type])"
    )
    for inp in text_inputs:
        try:
            visible = await inp.is_visible()
            enabled = await inp.is_enabled()
            if not visible or not enabled:
                continue

            current_val = await inp.input_value()
            if current_val.strip():
                continue  # Already filled (e.g. LinkedIn pre-fills)

            name = (await inp.get_attribute("name") or "").lower()
            ph = (await inp.get_attribute("placeholder") or "").lower()
            label = await _get_field_label(page, inp)
            label_lower = label.lower()

            # Check if user provided this in extra_inputs
            for key in (name, label_lower, label):
                if key and key in extra_inputs:
                    await inp.fill(extra_inputs[key])
                    logger.info("Filled '%s' from extra_inputs", label)
                    break
            else:
                value = _profile_value_for(label, name, ph)
                if value:
                    await inp.fill(value)
                    logger.info("Filled '%s' = '%s'", label, value[:20])
                else:
                    required = await inp.get_attribute("required")
                    aria_req = await inp.get_attribute("aria-required")
                    if required is not None or aria_req == "true":
                        logger.warning("Required field needs user input: '%s'", label)
                        return {
                            "status": "needs_input",
                            "field_name": name or label_lower or "unknown_field",
                            "label": label or name or "Unknown field",
                            "field_type": "text",
                            "hint": f"Required field on application form",
                            "page_url": page.url,
                        }
        except Exception as e:
            logger.debug("Field fill error (skipped): %s", e)

    # --- Textareas (cover letters, etc.) ---
    textareas = await page.query_selector_all("textarea")
    for ta in textareas:
        try:
            visible = await ta.is_visible()
            if not visible:
                continue
            current_val = await ta.input_value()
            if current_val.strip():
                continue

            name = (await ta.get_attribute("name") or "").lower()
            label = await _get_field_label(page, ta)
            label_lower = label.lower()

            for key in (name, label_lower, label):
                if key and key in extra_inputs:
                    await ta.fill(extra_inputs[key])
                    logger.info("Filled textarea '%s' from extra_inputs", label)
                    break
            else:
                required = await ta.get_attribute("required")
                aria_req = await ta.get_attribute("aria-required")
                if required is not None or aria_req == "true":
                    logger.warning("Required textarea needs user input: '%s'", label)
                    return {
                        "status": "needs_input",
                        "field_name": name or label_lower or "textarea_field",
                        "label": label or name or "Text field",
                        "field_type": "textarea",
                        "hint": "This may be a cover letter or custom question",
                        "page_url": page.url,
                    }
        except Exception as e:
            logger.debug("Textarea fill error (skipped): %s", e)

    # --- Selects ---
    selects = await page.query_selector_all("select")
    for sel_el in selects:
        try:
            visible = await sel_el.is_visible()
            if not visible:
                continue
            name = (await sel_el.get_attribute("name") or "").lower()
            label = await _get_field_label(page, sel_el)
            label_lower = label.lower()
            for key in (name, label_lower):
                if key and key in extra_inputs:
                    await sel_el.select_option(label=extra_inputs[key])
                    logger.info("Selected '%s' for '%s'", extra_inputs[key], label)
                    break
        except Exception as e:
            logger.debug("Select fill error (skipped): %s", e)

    return None  # All fields handled


# ---------------------------------------------------------------------------
# Main async apply coroutine
# ---------------------------------------------------------------------------

def _is_chrome_debug_running() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://localhost:{CHROME_DEBUG_PORT}/json", timeout=1)
        return True
    except Exception:
        return False


def _is_chrome_process_running() -> bool:
    """Check if any Chrome process is running (with or without debug port)."""
    import subprocess
    try:
        result = subprocess.run(["pgrep", "-f", "Google Chrome"], capture_output=True)
        return result.returncode == 0
    except Exception:
        return False


def _kill_chrome() -> None:
    import subprocess
    try:
        subprocess.run(["pkill", "-f", "Google Chrome"], capture_output=True)
        import time as _t
        _t.sleep(1.5)
    except Exception:
        pass


def _launch_chrome_with_debug() -> bool:
    """Launch Chrome with remote debugging port. Kills existing Chrome first on macOS (single-instance)."""
    import shutil, subprocess
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome",
        "chromium-browser",
        "chromium",
    ]
    chrome = next((p for p in chrome_paths if Path(p).exists() or shutil.which(p)), None)
    if not chrome:
        logger.warning("Chrome binary not found")
        return False

    # macOS Chrome is single-instance — kill existing first so debug port takes effect
    if _is_chrome_process_running():
        logger.info("Existing Chrome running without debug port — restarting with debug port")
        _kill_chrome()

    cmd = [
        chrome,
        f"--remote-debugging-port={CHROME_DEBUG_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    logger.info("Launching Chrome with debug port %d", CHROME_DEBUG_PORT)
    try:
        subprocess.Popen(cmd)
        return True
    except Exception as e:
        logger.error("Chrome launch failed: %s", e)
        return False


async def _run_apply(
    job_url: str,
    resume_path: Optional[Path],
    job: dict,
    extra_inputs: dict,
) -> dict:
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        return {"status": "failed", "reason": "playwright not installed — run: pip install playwright && playwright install chromium"}

    company = job.get("Company", "?")
    role = job.get("Role", "?")
    BROWSER_SESSION_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("auto_apply: starting for %s @ %s — %s", role, company, job_url)

    try:
        async with async_playwright() as p:
            if not _is_chrome_debug_running():
                logger.info("Chrome not running with debug port — launching it now")
                launched = _launch_chrome_with_debug()
                if not launched:
                    return {"status": "failed", "reason": "Chrome not found. Install Google Chrome."}
                # Wait up to 20s for Chrome to start accepting CDP connections
                import asyncio as _asyncio
                for attempt in range(40):
                    await _asyncio.sleep(0.5)
                    if _is_chrome_debug_running():
                        logger.info("Chrome debug port ready after %.1fs", (attempt + 1) * 0.5)
                        break
                else:
                    return {"status": "failed", "reason": f"Chrome launched but not reachable on port {CHROME_DEBUG_PORT} after 20s"}

            logger.info("Attaching to Chrome on debug port %d", CHROME_DEBUG_PORT)
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()

            # Check if we're resuming (page already on application form)
            current_url = page.url
            is_fresh = (
                current_url in ("about:blank", "chrome://newtab/", "")
                or current_url != job_url
            )

            if is_fresh or "__resume" not in extra_inputs:
                logger.info("Navigating to: %s", job_url)
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Check for instant success (already applied page)
                if await _is_success(page):
                    logger.info("Job already shows success state on load")
                    return {"status": "applied", "reason": "Already applied (success state detected on load)"}

                # Find and click Apply button
                logger.info("Looking for Apply button")
                clicked = await _click_first(page, APPLY_SELECTORS, "Apply")
                if not clicked:
                    logger.warning("No Apply button found; page open for manual interaction")
                    return {
                        "status": "needs_input",
                        "field_name": "__no_apply_button",
                        "label": "Apply button not found automatically",
                        "field_type": "confirm",
                        "hint": (
                            "The browser is open. Please click the Apply button manually, "
                            "then click **Continue** below to resume form filling."
                        ),
                        "page_url": page.url,
                    }

                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(1500)
            else:
                logger.info("Resuming on current page: %s", current_url)

            # Multi-step form loop
            max_steps = 10
            for step in range(max_steps):
                logger.info("Form step %d / max %d", step + 1, max_steps)

                if await _is_success(page):
                    logger.info("Application submitted successfully at step %d", step + 1)
                    return {"status": "applied", "reason": "Application submitted successfully"}

                # Fill all visible fields
                needs_input = await _fill_form_step(page, resume_path, extra_inputs)
                if needs_input:
                    needs_input["__resume"] = True  # signal for resume
                    return needs_input

                await page.wait_for_timeout(500)

                # Try Submit first, then Next/Continue
                submitted = await _click_first(page, SUBMIT_SELECTORS, "Submit")
                if submitted:
                    await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(2000)
                    if await _is_success(page):
                        logger.info("Submitted and success confirmed")
                        return {"status": "applied", "reason": "Application submitted successfully"}
                    # May be a confirmation step — continue loop
                    continue

                advanced = await _click_first(page, NEXT_SELECTORS, "Next/Continue")
                if advanced:
                    await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(1500)
                    continue

                # No button found — check success again or give up
                if await _is_success(page):
                    return {"status": "applied", "reason": "Application submitted successfully"}

                logger.warning("No Submit/Next button found at step %d; page: %s", step + 1, page.url)
                return {
                    "status": "needs_input",
                    "field_name": "__no_next_button",
                    "label": "Form navigation button not found",
                    "field_type": "confirm",
                    "hint": (
                        "The automation couldn't find a Next or Submit button. "
                        "Please advance the form manually, then click **Continue** below."
                    ),
                    "page_url": page.url,
                }

            logger.warning("Reached max form steps (%d) without completion", max_steps)
            return {
                "status": "manual_required",
                "reason": f"Reached maximum form steps ({max_steps}). Please complete manually.",
            }

    except Exception as e:
        logger.error("auto_apply error for %s @ %s: %s", role, company, e, exc_info=True)
        return {"status": "failed", "reason": str(e)}


# ---------------------------------------------------------------------------
# Synchronous wrapper (called from Streamlit threads)
# ---------------------------------------------------------------------------

def apply_job(
    job_url: str,
    resume_path: Optional[Path] = None,
    job: Optional[dict] = None,
    extra_inputs: Optional[dict] = None,
) -> dict:
    """
    Synchronous wrapper for Streamlit thread usage.

    extra_inputs: dict of {field_name: user_answer} for resuming after needs_input.
                  Pass {"__resume": True} to skip re-navigation and continue on current page.
    """
    job = job or {}
    extra_inputs = extra_inputs or {}
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(
            _run_apply(job_url, resume_path, job, extra_inputs)
        )
    except Exception as e:
        logger.error("apply_job sync wrapper error: %s", e)
        return {"status": "failed", "reason": str(e)}
