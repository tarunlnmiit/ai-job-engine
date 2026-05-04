import sys
import os
from pathlib import Path
from datetime import datetime
import ollama

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.scraper.hacker_news import HackerNewsScraper
from core.tracker.db import JobCache
from core.tracker.csv_tracker import CSVTracker
from core.resume.parser import ResumeParser
from core.ai.scorer import score_batch_ollama

def process_hn():
    print("Scraping Hacker News...")
    scraper = HackerNewsScraper()
    jobs = scraper.search(role="Data Scientist", location="")
    jobs += scraper.search(role="AI Engineer", location="")
    
    print(f"Found {len(jobs)} jobs. Parsing resume...")
    parser = ResumeParser()
    resume_path = None
    for ext in [".docx", ".pdf", ".txt"]:
        files = list(Path("resume").glob(f"*{ext}"))
        if files:
            resume_path = files[0]
            break
            
    if not resume_path:
        print("No resume found.")
        return
        
    resume_text = parser.parse(str(resume_path))
    db = JobCache()
    tracker = CSVTracker()
    
    jobs_dicts = [j.to_dict() if hasattr(j, 'to_dict') else j for j in jobs]
    
    print("Scoring with qwen2.5:14b...")
    
    # Process in chunks of 5
    for i in range(0, len(jobs_dicts), 5):
        chunk = jobs_dicts[i:i+5]
        print(f"Scoring chunk {i//5 + 1}...")
        results = score_batch_ollama(resume_text, chunk, "qwen2.5:14b")
        
        # Create a map of results by job ID for safe merging
        res_map = {r.get("id"): r for r in results if isinstance(r, dict)}
        
        # Merge scores
        for job in chunk:
            job_id = job.get("id")
            res = res_map.get(job_id, {})
            
            job["score"] = res.get("score", 0)
            job["matching_skills"] = res.get("matching_skills", [])
            job["missing_skills"] = res.get("missing_skills", [])
                
            job["insert_ts"] = datetime.now().isoformat()
            job["status"] = "new"
            db.add_job(job)
            tracker.update_job(job)
            
    print("Done! Hacker News jobs have been added to your database.")

if __name__ == "__main__":
    process_hn()
