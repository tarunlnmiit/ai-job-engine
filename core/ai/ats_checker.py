"""ATS (Applicant Tracking System) keyword analysis."""

import os
import json
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from groq import Groq
    from core.ai.client_manager import get_groq_client
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

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
    """Check resume ATS compatibility using Groq."""
    if not GROQ_AVAILABLE:
        return None

    client = get_groq_client()
    if not client:
        return None

    prompt = ATS_PROMPT.format(
        resume_text=resume_text,
        job_description=job_description
    )

    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=model_name,
            response_format={"type": "json_object"}
        )
        text = chat_completion.choices[0].message.content.strip()
        return json.loads(text)
    except Exception as e:
        print(f"Error checking ATS: {e}")
        return None
