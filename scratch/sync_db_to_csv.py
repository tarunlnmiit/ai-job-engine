import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.tracker.db import JobCache
from core.tracker.csv_tracker import CSVTracker

def sync_db_to_csv():
    db = JobCache()
    tracker = CSVTracker()
    
    jobs = db.get_all_jobs()
    print(f"Read {len(jobs)} jobs from SQLite Database.")
    
    csv_jobs = tracker.get_all_jobs()
    csv_ids = {str(j.get("Job ID")) for j in csv_jobs}
    print(f"Read {len(csv_jobs)} jobs from CSV.")
    
    synced_count = 0
    for job in jobs:
        job_id = str(job.get("id"))
        # If it's not in CSV, or if we want to overwrite to ensure correctness
        if tracker.update_job(job):
            synced_count += 1
            
    print(f"\nDone! Processed and updated {synced_count} jobs to CSV.")

if __name__ == "__main__":
    sync_db_to_csv()
