import json
import os
from typing import List, Dict, Tuple
from logger import get_logger

logger = get_logger("ai.deduplicator")

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

DEDUPE_PROMPT = """
You are an expert recruitment assistant. Analyze these two job postings and determine if they are the SAME job opportunity.
They might be from different platforms or have slightly different titles, but represent the same role at the same company.

JOB A:
Title: {title_a}
Company: {company_a}
Location: {location_a}
Snippet: {desc_a}

JOB B:
Title: {title_b}
Company: {company_b}
Location: {location_b}
Snippet: {desc_b}

Are these the same job? Return ONLY valid JSON:
{{
  "is_duplicate": true/false,
  "confidence": 0-100,
  "reason": "Brief explanation"
}}
"""

class Deduplicator:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if GEMINI_AVAILABLE and self.api_key else None

    def find_duplicates(self, new_jobs: List[Dict], existing_jobs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Processes new jobs against existing ones.
        Returns (clean_jobs, duplicate_flags).
        """
        clean_jobs = []
        duplicate_flags = []
        
        all_known_jobs = existing_jobs + clean_jobs
        
        for new_job in new_jobs:
            is_dup = False
            potential_match = None
            
            for existing in all_known_jobs:
                # Heuristic 1: Identical ID
                if new_job.get("id") == existing.get("id"):
                    is_dup = True
                    potential_match = existing
                    break
                
                # Heuristic 2: Title + Company + Location exact match
                if (new_job.get("title") == existing.get("title") and 
                    new_job.get("company") == existing.get("company") and 
                    new_job.get("location") == existing.get("location")):
                    is_dup = True
                    potential_match = existing
                    break
                
                # Heuristic 3: Fuzzy match (Title contains title, etc.) - use LLM if ambiguous
                if (new_job.get("company") == existing.get("company") and 
                    (new_job.get("title").lower() in existing.get("title").lower() or 
                     existing.get("title").lower() in new_job.get("title").lower())):
                    
                    # Call LLM for final check
                    if self.client:
                        logger.info("Potential duplicate detected (%s @ %s) - asking AI...", new_job.get("title"), new_job.get("company"))
                        if self._is_duplicate_ai(new_job, existing):
                            is_dup = True
                            potential_match = existing
                            break
            
            if is_dup:
                logger.info("Duplicate found: %s @ %s", new_job.get("title"), new_job.get("company"))
                # Keep the latest (date_found is added later in Search.py, so we use list order or assume new is latest)
                # But here we just flag it so Search.py can decide.
                new_job["duplicate_of"] = potential_match.get("id")
                duplicate_flags.append(new_job)
            else:
                clean_jobs.append(new_job)
                all_known_jobs.append(new_job)
                
        return clean_jobs, duplicate_flags

    def _is_duplicate_ai(self, job_a: Dict, job_b: Dict) -> bool:
        """Use Gemini to confirm if two jobs are duplicates."""
        if not self.client:
            return False
            
        try:
            prompt = DEDUPE_PROMPT.format(
                title_a=job_a.get("title"), company_a=job_a.get("company"), 
                location_a=job_a.get("location"), desc_a=job_a.get("description", "")[:500],
                title_b=job_b.get("title"), company_b=job_b.get("company"), 
                location_b=job_b.get("location"), desc_b=job_b.get("description", "")[:500]
            )
            
            model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
            
            res = json.loads(text)
            return res.get("is_duplicate", False) and res.get("confidence", 0) >= 95
        except Exception as e:
            logger.error("Deduplication AI error: %s", e)
            return False
