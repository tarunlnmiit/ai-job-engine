import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

from logger import get_logger
logger = get_logger("ai.role_expander")

try:
    import google.genai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

EXPAND_PROMPT = """You are a job search expert.

Given a target role and years of experience, return a JSON list of similar/equivalent job titles that recruiters commonly use for the same or adjacent positions. Include:
- Alternate naming conventions (e.g. "Data Scientist" → "ML Engineer", "AI Researcher")
- Seniority variants appropriate for {experience} years of experience
- Adjacent roles where skills heavily overlap
- Common abbreviations or industry-specific names

Target Role: {role}
Years of Experience: {experience}

Return ONLY a valid JSON array of strings, no markdown, no explanation:
["title1", "title2", "title3", ...]

Include 5-10 titles. Include the original role. Keep titles concise and job-board-friendly."""


def expand_roles_gemini(role: str, experience: int) -> list[str] | None:
    logger.debug("Gemini available=%s", GEMINI_AVAILABLE)
    if not GEMINI_AVAILABLE:
        logger.debug("Gemini SDK not installed — skipping")
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping Gemini role expansion")
        return None

    logger.info("Calling Gemini (gemini-3-flash-preview) for role='%s' exp=%d", role, experience)
    t0 = time.time()

    try:
        client = genai.Client(api_key=api_key)
        prompt = EXPAND_PROMPT.format(role=role, experience=experience)
        logger.debug("Prompt length: %d chars", len(prompt))

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        elapsed = time.time() - t0
        text = response.text.strip()
        logger.debug("Gemini responded in %.2fs — raw: %s", elapsed, text[:200])

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            logger.debug("Stripped markdown fences — cleaned: %s", text[:200])

        titles = json.loads(text)
        logger.info("Gemini expanded to %d titles: %s", len(titles), titles)
        return titles

    except json.JSONDecodeError as e:
        logger.error("Gemini JSON parse failed: %s — raw text: %s", e, text[:300])
        return None
    except Exception as e:
        logger.error("Gemini role expansion error: %s", e)
        return None


def expand_roles_ollama(role: str, experience: int) -> list[str] | None:
    logger.debug("Ollama available=%s", OLLAMA_AVAILABLE)
    if not OLLAMA_AVAILABLE:
        logger.debug("Ollama not installed — skipping")
        return None

    logger.info("Calling Ollama (gemma4:e4b) for role='%s' exp=%d", role, experience)
    t0 = time.time()

    try:
        prompt = EXPAND_PROMPT.format(role=role, experience=experience)
        logger.debug("Prompt length: %d chars", len(prompt))

        response = ollama.generate(model="gemma4:e4b", prompt=prompt, stream=False)
        elapsed = time.time() - t0
        text = response["response"].strip()
        logger.debug("Ollama responded in %.2fs — raw: %s", elapsed, text[:200])

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            logger.debug("Stripped markdown fences — cleaned: %s", text[:200])

        titles = json.loads(text)
        logger.info("Ollama expanded to %d titles: %s", len(titles), titles)
        return titles

    except json.JSONDecodeError as e:
        logger.error("Ollama JSON parse failed: %s — raw text: %s", e, text[:300])
        return None
    except Exception as e:
        logger.error("Ollama role expansion error: %s", e)
        return None


def expand_roles(role: str, experience: int) -> list[str]:
    """Return similar job titles for role + experience. Gemini → Ollama fallback."""
    logger.info("expand_roles called: role='%s' experience=%d", role, experience)

    titles = expand_roles_gemini(role, experience)
    if titles:
        logger.info("Using Gemini result — %d titles", len(titles))
        return titles

    logger.info("Gemini failed — falling back to Ollama")
    titles = expand_roles_ollama(role, experience)
    if titles:
        logger.info("Using Ollama result — %d titles", len(titles))
        return titles

    logger.warning("Both engines failed — returning original role only: ['%s']", role)
    return [role]
