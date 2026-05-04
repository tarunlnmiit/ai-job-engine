import os
import time
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from logger import get_logger
logger = get_logger("ai.resume_tailor")

try:
    from groq import Groq
    from core.ai.client_manager import get_groq_client
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

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
    """Tailor resume to a job description using Groq (Llama 3)."""
    if not GROQ_AVAILABLE:
        logger.warning("Groq SDK not installed — resume tailoring unavailable")
        return None

    client = get_groq_client()
    if not client:
        logger.warning("No Groq API keys found — cannot tailor resume")
        return None

    logger.info("Tailoring resume — missing keywords: %s", missing_keywords)
    logger.debug("Resume length: %d chars, JD length: %d chars", len(resume_text), len(job_description))

    prompt = TAILOR_PROMPT.format(
        resume_text=resume_text,
        job_description=job_description,
        missing_keywords=", ".join(missing_keywords)
    )
    logger.debug("Tailor prompt length: %d chars", len(prompt))

    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    try:
        logger.debug("Calling Groq (%s) for resume tailoring", model_name)
        t0 = time.time()
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=model_name,
        )
        elapsed = time.time() - t0
        text = chat_completion.choices[0].message.content.strip()
        logger.info("Resume tailored in %.2fs — output length: %d chars", elapsed, len(text))
        return text
    except Exception as e:
        if "429" in str(e) or "rate_limit_exceeded" in str(e).lower():
            logger.warning("Groq rate limited — waiting 30s before retry")
            time.sleep(30)
            return tailor_resume(resume_text, job_description, missing_keywords)
        else:
            logger.error("Error tailoring resume: %s", e)
            return None
