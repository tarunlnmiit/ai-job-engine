"""ATS (Applicant Tracking System) keyword analysis."""

import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

ATS_PROMPT = """
Analyze the following resume and job description for ATS compatibility.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Return ONLY valid JSON (no markdown):
{{
  "ats_score": <0-100>,
  "missing_keywords": ["keyword1", "keyword2"],
  "formatting_issues": ["issue1", "issue2"],
  "recommendations": ["recommendation1", "recommendation2"]
}}
"""


def check_ats_compatibility(resume_text: str, job_description: str) -> Optional[dict]:
    """Check resume ATS compatibility."""
    if not GEMINI_AVAILABLE:
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    genai.configure(api_key=api_key)
    model = genai.Client().models.generate_content

    prompt = ATS_PROMPT.format(
        resume_text=resume_text,
        job_description=job_description
    )

    try:
        response = model(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json")
        return json.loads(text)
    except Exception as e:
        print(f"Error checking ATS: {e}")
        return None
