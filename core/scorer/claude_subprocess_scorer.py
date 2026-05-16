"""Score jobs via Claude subprocess (claude -p) with session limit tracking."""

import subprocess
import json
import time
import re
import os
from typing import Optional, List, Tuple
from logger import get_logger

logger = get_logger("scorer.claude_subprocess")

BATCH_SCORE_PROMPT = """
YOU RECRUITER. YOU ATS.

ME SKILLS:
{resume_text}

HUNT JOBS:
{jobs_json}

MATCH JOB TO ME. NO TALK. ONLY JSON LIST.
JSON MUST BE:
[
  {{
    "id": "JOB ID",
    "score": 0-100,
    "matching_skills": ["HAVE"],
    "missing_skills": ["NO HAVE"],
    "recommendation": "SAY WHY"
  }}
]
"""


def parse_usage_limit_error(stderr: str) -> Optional[str]:
    """Parse Claude usage limit error to extract retry time. Returns retry_time str or None."""
    match = re.search(
        r"Claude AI usage limit reached, please try again after (\d{1,2}):(\d{2})([ap]m)",
        stderr,
        re.IGNORECASE
    )
    if match:
        hour, minute, period = match.groups()
        return f"{hour}:{minute}{period}"
    return None


def score_batch_claude_subprocess(resume_text: str, jobs: List[dict], model: str = "claude-sonnet-4-6") -> Tuple[List[dict], Optional[str]]:
    """
    Score batch of jobs via Claude subprocess.
    Returns (results, retry_time_str or None if limit hit).
    """
    if not jobs:
        return [], None

    jobs_to_send = [
        {"id": j.get("id"), "description": j.get("description", "")[:1500]}
        for j in jobs
    ]

    prompt = BATCH_SCORE_PROMPT.format(
        resume_text=resume_text,
        jobs_json=json.dumps(jobs_to_send)
    )

    try:
        # Check claude CLI available
        subprocess.run(["claude", "--version"], capture_output=True, check=True, timeout=5)
    except Exception as e:
        logger.error("Claude CLI unavailable: %s", e)
        return [], None

    for attempt in range(2):
        try:
            logger.info("⚡ Claude subprocess (%s) — batch %d jobs (attempt %d/2)...", model, len(jobs), attempt + 1)
            t0 = time.time()

            result = subprocess.run(
                ["claude", "-p", prompt, "--model", model],
                capture_output=True,
                text=True,
                timeout=300
            )
            elapsed = time.time() - t0

            # Check for usage limit error
            if result.returncode != 0:
                stderr_text = result.stderr or ""
                stdout_text = result.stdout or ""
                retry_time = parse_usage_limit_error(stderr_text)
                if retry_time:
                    logger.warning("Claude usage limit reached — retry after %s", retry_time)
                    return [], retry_time
                logger.error("Claude subprocess failed (rc=%d)", result.returncode)
                if stderr_text:
                    logger.error("  stderr: %s", stderr_text)
                if stdout_text:
                    logger.error("  stdout: %s", stdout_text)
                if not stderr_text and not stdout_text:
                    logger.error("  (no output captured)")
                logger.error("  prompt size: %d chars", len(prompt))
                if attempt < 1:
                    time.sleep(5)
                continue

            text = result.stdout.strip()
            logger.info("✅ Claude subprocess done in %.2fs — %d chars", elapsed, len(text))

            # Clean ANSI codes
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            text = ansi_escape.sub('', text)

            # Extract JSON
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            start_idx = text.find('[')
            end_idx = text.rfind(']')
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx + 1]

            results = json.loads(text)
            if isinstance(results, list):
                logger.info("Claude parsed %d scored results", len(results))
                return results, None
            return [], None

        except subprocess.TimeoutExpired:
            logger.error("Claude subprocess timeout (attempt %d/2)", attempt + 1)
            if attempt < 1:
                time.sleep(5)
        except json.JSONDecodeError as e:
            logger.error("Claude JSON parse failed (attempt %d/2): %s", attempt + 1, e)
            if attempt < 1:
                time.sleep(5)
        except Exception as e:
            logger.error("Claude subprocess error (attempt %d/2): %s", attempt + 1, e)
            if attempt < 1:
                time.sleep(5)

    logger.warning("Claude subprocess exhausted retries")
    return [], None
