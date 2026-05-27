"""CSV tracker for job applications."""

import os
import pandas as pd
from datetime import datetime
from logger import get_logger

logger = get_logger("tracker.csv")

COLUMNS = [
    "Job ID", "Date Found", "Date Applied", "Platform", "Company",
    "Role", "Location", "Remote", "Salary", "Description", "Score (%)",
    "Matching Skills", "Missing Skills", "Status",
    "Application URL", "Contact Person", "Contact Email",
    "LinkedIn Network Match", "Notes", "Insert TS", "Applied TS"
]


class CSVTracker:
    """CSV tracker for job applications."""

    def __init__(self, filepath: str = "data/jobs_tracker.csv"):
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    # Maps incoming job dict keys → CSV column names
    _KEY_TO_COL = {
        "date_found": "Date Found",
        "date_applied": "Date Applied",
        "platform": "Platform",
        "company": "Company",
        "title": "Role",
        "location": "Location",
        "is_remote": "Remote",
        "salary": "Salary",
        "description": "Description",
        "score": "Score (%)",
        "matching_skills": "Matching Skills",
        "missing_skills": "Missing Skills",
        "status": "Status",
        "application_url": "Application URL",
        "contact_person": "Contact Person",
        "contact_email": "Contact Email",
        "linkedin_network_match": "LinkedIn Network Match",
        "notes": "Notes",
        "insert_ts": "Insert TS",
        "applied_ts": "Applied TS",
    }

    def _coerce(self, key: str, val) -> str:
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        if key == "is_remote":
            return "Yes" if val else "No"
        return str(val) if val is not None else ""

    def update_job(self, job: dict) -> bool:
        """Add or update job in CSV tracker.

        For existing rows only updates the columns explicitly present in *job*,
        preserving all other field values. For new rows inserts a full row with
        empty defaults for any missing fields.
        """
        try:
            if os.path.exists(self.filepath):
                df = pd.read_csv(self.filepath, dtype=str)
            else:
                df = pd.DataFrame(columns=COLUMNS)

            job_id = str(job.get("id"))
            if not df.empty:
                df["Job ID"] = df["Job ID"].astype(str)

            if not df.empty and job_id in df["Job ID"].values:
                # Patch-only update: only touch columns present in the incoming dict
                idx = df[df["Job ID"] == job_id].index[0]
                for key, col in self._KEY_TO_COL.items():
                    if key in job:
                        df.at[idx, col] = self._coerce(key, job[key])
            else:
                # Full insert with defaults for missing fields
                row_data = {"Job ID": job_id}
                for key, col in self._KEY_TO_COL.items():
                    row_data[col] = self._coerce(key, job.get(key, ""))
                # Fallbacks for fields that aren't in _KEY_TO_COL
                if "salary" not in job:
                    row_data["Salary"] = "N/A"
                if "status" not in job:
                    row_data["Status"] = "new"
                df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)

            df.to_csv(self.filepath, index=False)
            return True
        except Exception as e:
            logger.error("Error updating CSV tracker: %s", e)
            return False

    def get_all_jobs(self) -> list[dict]:
        """Read all jobs from CSV."""
        if not os.path.exists(self.filepath):
            return []

        try:
            df = pd.read_csv(self.filepath, dtype=str)
            # Replace NaN with empty string
            df = df.fillna("")
            return df.to_dict("records")
        except Exception as e:
            logger.error("Error reading CSV tracker: %s", e)
            return []

    def delete_jobs_by_platform(self, platform: str) -> bool:
        """Delete all jobs for a specific platform from CSV."""
        if not os.path.exists(self.filepath):
            return True

        try:
            df = pd.read_csv(self.filepath)
            if "Platform" in df.columns:
                initial_count = len(df)
                df = df[df["Platform"] != platform]
                deleted_count = initial_count - len(df)
                df.to_csv(self.filepath, index=False)
                logger.info("Deleted %d jobs for %s from CSV", deleted_count, platform)
            return True
        except Exception as e:
            logger.error("Error deleting jobs for platform %s from CSV: %s", platform, e)
            return False

    def delete_jobs_by_ids(self, job_ids: list[str]) -> bool:
        """Delete specific jobs by their IDs from CSV."""
        if not os.path.exists(self.filepath) or not job_ids:
            return True
        try:
            df = pd.read_csv(self.filepath, dtype=str)
            initial_count = len(df)
            df = df[~df["Job ID"].isin(job_ids)]
            deleted_count = initial_count - len(df)
            df.to_csv(self.filepath, index=False)
            logger.info("Deleted %d jobs from CSV", deleted_count)
            return True
        except Exception as e:
            logger.error("Error deleting jobs by IDs from CSV: %s", e)
            return False

    def clear_all(self) -> bool:
        """Delete all jobs from CSV tracker."""
        logger.warning("Clearing all jobs from CSV tracker")
        try:
            if os.path.exists(self.filepath):
                df = pd.DataFrame(columns=COLUMNS)
                df.to_csv(self.filepath, index=False)
                logger.warning("Cleared all jobs from CSV tracker")
            return True
        except Exception as e:
            logger.error("Error clearing CSV tracker: %s", e)
            return False
