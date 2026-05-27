"""SQLite job cache database."""

import sqlite3
import json
from typing import Optional, List
import os
from logger import get_logger

logger = get_logger("tracker.db")


class JobCache:
    """SQLite cache for job data."""

    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        logger.debug("JobCache initializing — db_path=%s", db_path)
        self._init_db()

    def _init_db(self):
        """Initialize database schema and handle migrations."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                salary TEXT,
                description TEXT,
                skills_required TEXT,
                platform TEXT,
                application_url TEXT,
                is_remote BOOLEAN,
                is_easy_apply BOOLEAN,
                score REAL,
                status TEXT,
                date_found TEXT,
                date_applied TEXT,
                matching_skills TEXT,
                missing_skills TEXT,
                notes TEXT,
                contact_info TEXT,
                linkedin_network_match TEXT,
                insert_ts TEXT,
                applied_ts TEXT
            )
        """)
        
        # Migration: Add columns if they don't exist
        c.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in c.fetchall()]
        
        if "insert_ts" not in columns:
            logger.info("Migrating DB: Adding insert_ts column")
            c.execute("ALTER TABLE jobs ADD COLUMN insert_ts TEXT")
        if "applied_ts" not in columns:
            logger.info("Migrating DB: Adding applied_ts column")
            c.execute("ALTER TABLE jobs ADD COLUMN applied_ts TEXT")
        if "desc_fetch_error" not in columns:
            logger.info("Migrating DB: Adding desc_fetch_error column")
            c.execute("ALTER TABLE jobs ADD COLUMN desc_fetch_error TEXT")

        conn.commit()
        conn.close()

    def add_job(self, job: dict) -> bool:
        """Add or update job in cache."""
        logger.debug("add_job: id=%s title='%s' score=%s", job.get("id"), job.get("title"), job.get("score"))
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            c.execute("""
                INSERT OR REPLACE INTO jobs
                (id, title, company, location, salary, description, skills_required,
                 platform, application_url, is_remote, is_easy_apply, score, status,
                 date_found, date_applied, matching_skills, missing_skills, notes,
                 contact_info, linkedin_network_match, insert_ts, applied_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.get("id"),
                job.get("title"),
                job.get("company"),
                job.get("location"),
                job.get("salary"),
                job.get("description"),
                json.dumps(job.get("skills_required", [])),
                job.get("platform"),
                job.get("application_url"),
                job.get("is_remote", False),
                job.get("is_easy_apply", False),
                job.get("score"),
                job.get("status", "new"),
                job.get("date_found"),
                job.get("date_applied"),
                json.dumps(job.get("matching_skills", [])),
                json.dumps(job.get("missing_skills", [])),
                job.get("notes"),
                job.get("contact_info"),
                job.get("linkedin_network_match"),
                job.get("insert_ts"),
                job.get("applied_ts"),
            ))

            conn.commit()
            conn.close()
            logger.debug("add_job success: id=%s", job.get("id"))
            return True
        except Exception as e:
            logger.error("Error adding job to cache: %s", e)
            return False

    def get_job(self, job_id: str) -> Optional[dict]:
        """Retrieve job from cache."""
        logger.debug("get_job: id=%s", job_id)
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = c.fetchone()
            conn.close()
            result = self._row_to_dict(row) if row else None
            logger.debug("get_job result: %s", "found" if result else "not found")
            return result
        except Exception as e:
            logger.error("Error retrieving job %s: %s", job_id, e)
            return None

    def get_all_jobs(self, status: Optional[str] = None) -> List[dict]:
        """Retrieve all jobs or jobs with specific status."""
        logger.debug("get_all_jobs: status=%s", status)
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            if status:
                c.execute("SELECT * FROM jobs WHERE status = ?", (status,))
            else:
                c.execute("SELECT * FROM jobs")

            rows = c.fetchall()
            conn.close()
            logger.debug("get_all_jobs: %d rows returned", len(rows))
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error("Error retrieving jobs: %s", e)
            return []

    def get_unique_platforms(self) -> List[str]:
        """Retrieve a list of unique platforms from the jobs database."""
        logger.debug("get_unique_platforms")
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT DISTINCT platform FROM jobs WHERE platform IS NOT NULL AND platform != ''")
            rows = c.fetchall()
            conn.close()
            platforms = sorted([row[0] for row in rows])
            logger.debug("get_unique_platforms: found %d platforms", len(platforms))
            return platforms
        except Exception as e:
            logger.error("Error retrieving unique platforms: %s", e)
            return []

    def delete_jobs_by_platform(self, platform: str) -> bool:
        """Delete all jobs for a specific platform from cache."""
        logger.info("Deleting all jobs for platform: %s", platform)
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM jobs WHERE platform = ?", (platform,))
            count = conn.total_changes
            conn.commit()
            conn.close()
            logger.info("Deleted %d jobs for %s", count, platform)
            return True
        except Exception as e:
            logger.error("Error deleting jobs for platform %s: %s", platform, e)
            return False

    def delete_jobs_by_ids(self, job_ids: List[str]) -> bool:
        """Delete specific jobs by their IDs from cache."""
        logger.info("Deleting %d jobs by IDs", len(job_ids))
        if not job_ids:
            return True
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            placeholders = ",".join(["?"] * len(job_ids))
            c.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
            count = conn.total_changes
            conn.commit()
            conn.close()
            logger.info("Deleted %d jobs", count)
            return True
        except Exception as e:
            logger.error("Error deleting jobs by IDs: %s", e)
            return False

    def get_jobs_without_description(
        self,
        include_perm_failed: bool = False,
        include_no_desc: bool = False,
    ) -> List[dict]:
        """Jobs with missing or very short descriptions."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            base = "SELECT * FROM jobs WHERE (description IS NULL OR TRIM(description) = '' OR LENGTH(description) < 100)"
            excluded = []
            if not include_perm_failed:
                excluded.append("perm_failed")
            if not include_no_desc:
                excluded.append("no_desc")
            if excluded:
                placeholders = ",".join("?" * len(excluded))
                base += f" AND (desc_fetch_error IS NULL OR desc_fetch_error NOT IN ({placeholders}))"
                c.execute(base, excluded)
            else:
                c.execute(base)
            rows = c.fetchall()
            conn.close()
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error("Error retrieving jobs without description: %s", e)
            return []

    def mark_desc_fetch_error(self, job_id: str, error: str) -> bool:
        """Persist a permanent fetch error so the job is skipped on future runs."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE jobs SET desc_fetch_error = ? WHERE id = ?", (error, job_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("Error marking fetch error for job %s: %s", job_id, e)
            return False

    def clear_desc_fetch_error(self, job_id: str) -> bool:
        """Clear a persisted fetch error to allow retrying."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE jobs SET desc_fetch_error = NULL WHERE id = ?", (job_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("Error clearing fetch error for job %s: %s", job_id, e)
            return False

    def update_description(self, job_id: str, description: str) -> bool:
        """Update description for a single job."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE jobs SET description = ? WHERE id = ?", (description, job_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("Error updating description for job %s: %s", job_id, e)
            return False

    def get_jobs_grouped_by_company(self, status: Optional[str] = None) -> dict[str, list[dict]]:
        """Return jobs from DB grouped by company name."""
        jobs = self.get_all_jobs(status=status)
        grouped: dict[str, list[dict]] = {}
        for job in jobs:
            company = job.get("company") or "Unknown"
            grouped.setdefault(company, []).append(job)
        return grouped

    def clear_all(self) -> bool:
        """Delete all jobs from cache."""
        logger.warning("Clearing all jobs from database")
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM jobs")
            count = conn.total_changes
            conn.commit()
            conn.close()
            logger.warning("Cleared %d jobs from database", count)
            return True
        except Exception as e:
            logger.error("Error clearing database: %s", e)
            return False

    def _row_to_dict(self, row) -> dict:
        """Convert database row to dictionary."""
        return {
            "id": row[0],
            "title": row[1],
            "company": row[2],
            "location": row[3],
            "salary": row[4],
            "description": row[5],
            "skills_required": json.loads(row[6] or "[]"),
            "platform": row[7],
            "application_url": row[8],
            "is_remote": row[9],
            "is_easy_apply": row[10],
            "score": row[11],
            "status": row[12],
            "date_found": row[13],
            "date_applied": row[14],
            "matching_skills": json.loads(row[15] or "[]"),
            "missing_skills": json.loads(row[16] or "[]"),
            "notes": row[17],
            "contact_info": row[18],
            "linkedin_network_match": row[19],
            "insert_ts": row[20] if len(row) > 20 else None,
            "applied_ts": row[21] if len(row) > 21 else None,
            "desc_fetch_error": row[22] if len(row) > 22 else None,
        }
