import sys
import os
from pathlib import Path
import pandas as pd
import json

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.tracker.db import JobCache

def sync_csv_to_db():
    csv_path = "data/jobs_tracker.csv"
    if not os.path.exists(csv_path):
        print("CSV not found.")
        return

    db = JobCache()
    df = pd.read_csv(csv_path)
    
    print(f"Read {len(df)} jobs from CSV.")
    
    synced_count = 0
    for _, row in df.iterrows():
        job_id = str(row["Job ID"])
        
        # Check if job exists in DB
        if db.get_job(job_id):
            continue
            
        # Convert CSV row back to Job dict format
        # Note: CSV columns names: Job ID, Date Found, Date Applied, Platform, Company, Role, Location, Remote, Salary, Description, Score (%), Matching Skills, Missing Skills, Status, Application URL, Contact Person, Contact Email, LinkedIn Network Match, Notes, Insert TS, Applied TS
        
        # Parse list-like strings
        def parse_list(val):
            if pd.isna(val) or val == "": return []
            return [s.strip() for s in str(val).split(",")]

        job_dict = {
            "id": job_id,
            "title": row.get("Role", ""),
            "company": row.get("Company", ""),
            "location": row.get("Location", ""),
            "salary": row.get("Salary", "N/A"),
            "description": row.get("Description", ""),
            "platform": row.get("Platform", ""),
            "application_url": row.get("Application URL", ""),
            "is_remote": row.get("Remote") == "Yes",
            "is_easy_apply": False, # CSV doesn't track this explicitly
            "score": float(row.get("Score (%)", 0)),
            "status": row.get("Status", "new"),
            "date_found": row.get("Date Found", ""),
            "date_applied": row.get("Date Applied", ""),
            "matching_skills": parse_list(row.get("Matching Skills", "")),
            "missing_skills": parse_list(row.get("Missing Skills", "")),
            "notes": row.get("Notes", ""),
            "contact_info": row.get("Contact Person", ""),
            "linkedin_network_match": row.get("LinkedIn Network Match", ""),
            "insert_ts": row.get("Insert TS", ""),
            "applied_ts": row.get("Applied TS", ""),
        }
        
        if db.add_job(job_dict):
            synced_count += 1
            print(f"Synced: {job_id}")

    print(f"\nDone! Synced {synced_count} missing jobs to SQLite database.")

if __name__ == "__main__":
    sync_csv_to_db()
