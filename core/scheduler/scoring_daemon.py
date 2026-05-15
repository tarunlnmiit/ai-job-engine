#!/usr/bin/env python3
"""
Daemon to score jobs via Claude subprocess.
Runs at 1 AM IST via cron. Scores in batches, saves after each batch.
Retries on session limit until 3 AM IST.
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logger import get_logger
from core.tracker.csv_tracker import CSVTracker
from core.tracker.db import JobCache
from core.resume.parser import ResumeParser
from core.ui.style import get_resume_path
from core.scorer.claude_subprocess_scorer import score_batch_claude_subprocess

logger = get_logger("scheduler.scoring_daemon")


def is_within_window(start_hour: int = 1, end_hour: int = 3) -> bool:
    """Check if current IST time is within the window (e.g., 1 AM to 3 AM)."""
    try:
        ist = ZoneInfo("Asia/Kolkata")
        now = datetime.now(ist)
        return start_hour <= now.hour < end_hour
    except Exception as e:
        logger.error("Failed to check time window: %s", e)
        return True  # Assume we're in window if can't determine


def run_scoring_daemon(resume_context: str = "EU", batch_size: int = None):
    """Score unscored jobs via Claude subprocess. Save after each batch."""
    logger.info("═══ SCORING DAEMON START (context=%s) ═══", resume_context)

    if batch_size is None:
        batch_size = int(os.getenv("CLAUDE_BATCH_SIZE", "25"))

    # Load resume
    resume_path = get_resume_path(mode="score", job_type=resume_context)
    if not resume_path or not os.path.exists(resume_path):
        logger.error("Resume not found for context '%s'", resume_context)
        return False

    logger.info("Loading resume: %s", resume_path)
    parser = ResumeParser()
    resume_text = parser.parse(str(resume_path))
    if not resume_text:
        logger.error("Failed to parse resume")
        return False

    # Load trackers
    tracker = CSVTracker()
    db = JobCache()

    # Get all jobs
    all_jobs = tracker.get_all_jobs()
    logger.info("Total jobs in tracker: %d", len(all_jobs))

    # Filter unscored
    def is_unscored(row):
        score = str(row.get("Score (%)", "")).strip()
        return score == "" or score == "0" or score == "0.0"

    unscored = [j for j in all_jobs if is_unscored(j)]
    logger.info("Unscored jobs: %d", len(unscored))

    if not unscored:
        logger.info("No unscored jobs — exiting")
        return True

    # Score in batches
    model = "claude-sonnet-4-6"
    total_saved = 0
    batch_num = 0

    for i in range(0, len(unscored), batch_size):
        batch_num += 1
        batch = unscored[i:i + batch_size]
        logger.info("─ Batch %d: %d jobs ─", batch_num, len(batch))

        # Prepare job objects
        jobs_to_score = [
            {
                "id": str(row["Job ID"]).strip(),
                "description": str(row.get("Description", "")),
                "title": str(row["Role"]),
                "company": str(row["Company"]),
                "location": str(row["Location"]),
                "platform": str(row["Platform"]),
            }
            for _, row in enumerate(batch)
        ]

        # Create ID mapping
        id_to_orig = {str(row["Job ID"]).strip(): row for _, row in enumerate(batch)}

        # Score via Claude subprocess
        results, retry_time = score_batch_claude_subprocess(resume_text, jobs_to_score, model)

        if retry_time:
            logger.warning("SESSION LIMIT REACHED — retry after %s", retry_time)

            # Check if we're still within 1-3 AM window
            if is_within_window(start_hour=1, end_hour=3):
                logger.info("Within 1-3 AM window — waiting 60s before retry...")
                time.sleep(60)
                logger.info("Retrying batch %d...", batch_num)
                # Retry this batch
                results, retry_time = score_batch_claude_subprocess(resume_text, jobs_to_score, model)
                if retry_time:
                    logger.error("Still rate limited after retry. Waiting 2 minutes...")
                    time.sleep(120)
                    # One more attempt
                    results, retry_time = score_batch_claude_subprocess(resume_text, jobs_to_score, model)
                    if retry_time:
                        logger.error("Rate limit persists after 2nd retry. Exiting window.")
                        logger.info("Daemon stopping. %d jobs scored total in %d batches.", total_saved, batch_num - 1)
                        return True
            else:
                logger.error("Outside 1-3 AM window. Exiting.")
                logger.info("Daemon stopping. %d jobs scored total in %d batches.", total_saved, batch_num - 1)
                return True

        if not results:
            logger.warning("Batch %d returned no results — skipping", batch_num)
            continue

        # Save results
        saved_count = 0
        for res in results:
            jid = str(res.get("id", "")).strip()
            orig_row = id_to_orig.get(jid)
            if not orig_row:
                continue

            try:
                score = int(float(res.get("score", 0)))
                update_data = {
                    "id": jid,
                    "title": orig_row.get("Role"),
                    "company": orig_row.get("Company"),
                    "location": orig_row.get("Location"),
                    "platform": orig_row.get("Platform"),
                    "description": orig_row.get("Description"),
                    "application_url": orig_row.get("Application URL"),
                    "date_found": orig_row.get("Date Found"),
                    "salary": orig_row.get("Salary"),
                    "is_remote": orig_row.get("Remote") == "Yes",
                    "notes": orig_row.get("Notes"),
                    "score": score,
                    "matching_skills": res.get("matching_skills", []),
                    "missing_skills": res.get("missing_skills", []),
                    "recommendation": res.get("recommendation", ""),
                    "status": orig_row.get("Status", "new"),
                }
                db.add_job(update_data)
                tracker.update_job(update_data)
                saved_count += 1
                total_saved += 1
            except Exception as e:
                logger.error("Save failed for job %s: %s", jid, e)

        logger.info("Batch %d saved: %d/%d jobs", batch_num, saved_count, len(results))
        time.sleep(2)  # Cooldown between batches

    logger.info("═══ DAEMON COMPLETE: %d jobs scored in %d batches ═══", total_saved, batch_num)
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Score unscored jobs via Claude subprocess")
    parser.add_argument("--context", default="EU", help="Resume context (default: EU)")
    parser.add_argument("--batch-size", type=int, help="Override batch size (default: CLAUDE_BATCH_SIZE env)")
    args = parser.parse_args()

    success = run_scoring_daemon(resume_context=args.context, batch_size=args.batch_size)
    sys.exit(0 if success else 1)
