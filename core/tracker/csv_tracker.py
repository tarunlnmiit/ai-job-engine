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

    def update_job(self, job: dict) -> bool:
        """Add or update job in CSV tracker."""
        try:
            # Load or create DataFrame
            if os.path.exists(self.filepath):
                df = pd.read_csv(self.filepath, dtype=str)
            else:
                df = pd.DataFrame(columns=COLUMNS)

            # Check if job exists by ID
            job_id = str(job.get("id"))
            
            # Convert Job ID column to string for consistent comparison
            if not df.empty:
                df["Job ID"] = df["Job ID"].astype(str)

            # Prepare row data
            row_data = {
                "Job ID": str(job_id),
                "Date Found": str(job.get("date_found", "")),
                "Date Applied": str(job.get("date_applied", "")),
                "Platform": str(job.get("platform", "")),
                "Company": str(job.get("company", "")),
                "Role": str(job.get("title", "")),
                "Location": str(job.get("location", "")),
                "Remote": "Yes" if job.get("is_remote") else "No",
                "Salary": str(job.get("salary", "N/A")),
                "Description": str(job.get("description", "")),
                "Score (%)": str(job.get("score", "")),
                "Matching Skills": ", ".join(job.get("matching_skills", [])) if isinstance(job.get("matching_skills"), list) else str(job.get("matching_skills", "")),
                "Missing Skills": ", ".join(job.get("missing_skills", [])) if isinstance(job.get("missing_skills"), list) else str(job.get("missing_skills", "")),
                "Status": str(job.get("status", "new")),
                "Application URL": str(job.get("application_url", "")),
                "Contact Person": str(job.get("contact_person", "")),
                "Contact Email": str(job.get("contact_email", "")),
                "LinkedIn Network Match": str(job.get("linkedin_network_match", "")),
                "Notes": str(job.get("notes", "")),
                "Insert TS": str(job.get("insert_ts", "")),
                "Applied TS": str(job.get("applied_ts", "")),
            }

            if not df.empty and job_id in df["Job ID"].values:
                # Update existing row
                idx = df[df["Job ID"] == job_id].index[0]
                for col, val in row_data.items():
                    df.at[idx, col] = val
            else:
                # Append new row
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
