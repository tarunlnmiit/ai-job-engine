import os
import time
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from logger import get_logger
logger = get_logger("ai.resume_tailor")

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

TAILOR_PROMPT = """
You are an expert resume writer and ATS optimization specialist.

ORIGINAL RESUME:
{resume_text}

TARGET JOB DESCRIPTION:
{job_description}

MISSING KEYWORDS:
{missing_keywords}

Task:
1. Rewrite the resume to naturally incorporate the missing keywords
2. Reorder bullet points to prioritize most relevant experience first
3. Adjust the summary/objective section to match this role
4. Keep ALL facts accurate — never fabricate experience or skills
5. Maintain professional tone and ATS-friendly formatting
6. Return the complete modified resume as plain text with clear section headers

RULES:
- Never add fake experience or skills
- Keep the same structure but optimize content
- Use action verbs from the JD
- Quantify achievements where possible
- Maintain readability
"""


def tailor_resume(
    resume_text: str, job_description: str, missing_keywords: list[str]
) -> Optional[str]:
    """Tailor resume to a job description using Gemini Flash."""
    if not GEMINI_AVAILABLE:
        logger.warning("Gemini SDK not installed — resume tailoring unavailable")
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — cannot tailor resume")
        return None

    logger.info("Tailoring resume — missing keywords: %s", missing_keywords)
    logger.debug("Resume length: %d chars, JD length: %d chars", len(resume_text), len(job_description))

    genai.configure(api_key=api_key)
    model = genai.Client().models.generate_content

    prompt = TAILOR_PROMPT.format(
        resume_text=resume_text,
        job_description=job_description,
        missing_keywords=", ".join(missing_keywords)
    )
    logger.debug("Tailor prompt length: %d chars", len(prompt))

    try:
        logger.debug("Calling Gemini (gemini-3-flash-preview) for resume tailoring")
        t0 = time.time()
        response = model(
            model="gemini-3-flash-preview",
            contents=prompt
        )
        elapsed = time.time() - t0
        logger.info("Resume tailored in %.2fs — output length: %d chars", elapsed, len(response.text))
        return response.text
    except Exception as e:
        if "429" in str(e):
            logger.warning("Gemini rate limited — waiting 60s before retry")
            time.sleep(60)
            return tailor_resume(resume_text, job_description, missing_keywords)
        else:
            logger.error("Error tailoring resume: %s", e)
            return None
