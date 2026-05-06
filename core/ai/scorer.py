import os
import json
import time
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

from logger import get_logger
logger = get_logger("ai.scorer")

try:
    from core.ai.client_manager import get_groq_client
    GROQ_AVAILABLE = False
except ImportError:
    GROQ_AVAILABLE = False

try:
    from core.ai.client_manager import get_nim_config
    NIM_AVAILABLE = True
except ImportError:
    NIM_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = False
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

SCORE_PROMPT = """
YOU RECRUITER. YOU ATS. 

ME SKILLS:
{resume_text}

ONE JOB:
{job_description}

MATCH JOB TO ME. NO TALK. ONLY JSON.
JSON MUST BE:
{{
  "score": 0-100,
  "matching_skills": ["HAVE"],
  "missing_skills": ["NO HAVE"],
  "experience_match": "strong|partial|weak",
  "salary_fit": "above|within|below|unknown",
  "recommendation": "SAY WHY",
  "ats_keywords_present": ["GOOD WORDS"],
  "ats_keywords_missing": ["MISSING WORDS"]
}}
"""


BATCH_SCORE_PROMPT = """
YOU RECRUITER. YOU ATS.

ME SKILLS:
{resume_text}

HUNT JOBS:
{jobs_json}

MATCH JOB TO ME. NO TALK. ONLY JSON LIST.
JSON MUST BE:
[
  {{
    "id": "JOB ID",
    "score": 0-100,
    "matching_skills": ["HAVE"],
    "missing_skills": ["NO HAVE"],
    "experience_match": "strong|partial|weak",
    "recommendation": "SAY WHY"
  }}
]
"""

try:
    with open(os.path.join(os.path.dirname(__file__), "parsed_resume_skills.json"), "r") as f:
        PRE_PARSED_SKILLS = f.read()
except FileNotFoundError:
    logger.warning("parsed_resume_skills.json not found, falling back to raw resume_text if provided")
    PRE_PARSED_SKILLS = None



_GROQ_EXHAUSTED = True


def score_job_groq(resume_text: str, job_description: str, retries: int = 1) -> Optional[dict]:
    """Score using Groq (Llama 3)."""
    if not GROQ_AVAILABLE:
        logger.debug("Groq SDK not installed — skipping")
        return None

    logger.debug("Initializing Groq client for scoring")
    client = get_groq_client()
    if not client:
        logger.warning("No Groq API keys found — skipping Groq scoring")
        return None

    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    prompt = SCORE_PROMPT.format(
        resume_text=actual_resume_data,
        job_description=job_description
    )
    logger.debug("Score prompt length: %d chars", len(prompt))

    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    for attempt in range(retries):
        try:
            logger.debug("Groq score request attempt %d/%d using %s", attempt + 1, retries, model_name)
            t0 = time.time()
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
            elapsed = time.time() - t0
            text = chat_completion.choices[0].message.content.strip()
            logger.debug("Groq responded in %.2fs — raw length: %d chars", elapsed, len(text))

            result = json.loads(text)
            logger.debug("Groq score: %s | matching: %s | missing: %s",
                         result.get("score"), result.get("matching_skills"), result.get("missing_skills"))
            return result
        except Exception as e:
            if "429" in str(e) or "rate_limit_exceeded" in str(e).lower():
                logger.warning("Groq rate limited — flipping global exhaustion switch")
                global _GROQ_EXHAUSTED
                _GROQ_EXHAUSTED = True
                return None
            elif "401" in str(e) or "403" in str(e) or "authentication_error" in str(e).lower():
                logger.error("Groq API Key is invalid or has insufficient permissions: %s", e)
                logger.info("TIP: Check your GROQ_API_KEY in the .env file.")
                return None
            else:
                logger.error("Groq scoring error (attempt %d/%d): %s", attempt + 1, retries, e)
                if attempt < retries - 1:
                    time.sleep(2)

    return None


_FASTEST_OLLAMA_MODEL = None

def benchmark_ollama_models() -> Optional[str]:
    """Identify the fastest available Ollama model once."""
    global _FASTEST_OLLAMA_MODEL
    if _FASTEST_OLLAMA_MODEL:
        return _FASTEST_OLLAMA_MODEL
        
    # Check for forced model in .env
    env_model = os.getenv("OLLAMA_MODEL")
    if env_model:
        logger.info("Using OLLAMA_MODEL from .env: %s", env_model)
        _FASTEST_OLLAMA_MODEL = env_model
        return _FASTEST_OLLAMA_MODEL
        
    if not OLLAMA_AVAILABLE:
        return None
        
    try:
        models_info = ollama.list()
        # Handle different versions of ollama-python response
        raw_models = getattr(models_info, 'models', []) if not isinstance(models_info, list) else models_info
        
        model_names = []
        for m in raw_models:
            if hasattr(m, 'model'): # Object format
                model_names.append(m.model)
            elif isinstance(m, dict): # Dict format
                model_names.append(m.get('model') or m.get('name'))
        
        model_names = [n for n in model_names if n]
        if not model_names:
            return None
            
        logger.info("Benchmarking Ollama models to find the fastest: %s", model_names)
        
        results = []
        with ThreadPoolExecutor(max_workers=len(model_names)) as executor:
            def time_model(name):
                try:
                    t0 = time.time()
                    ollama.generate(model=name, prompt="respond with just 'ok'", stream=False)
                    return name, time.time() - t0
                except:
                    return name, float('inf')
            
            futures = [executor.submit(time_model, m) for m in model_names]
            for f in as_completed(futures):
                results.append(f.result())
        
        # Sort by time and pick best
        results.sort(key=lambda x: x[1])
        _FASTEST_OLLAMA_MODEL = results[0][0]
        logger.info("Ollama benchmark complete. Fastest model: %s (%.2fs)", _FASTEST_OLLAMA_MODEL, results[0][1])
        return _FASTEST_OLLAMA_MODEL
    except Exception as e:
        logger.error("Ollama benchmarking failed: %s", e)
        return None

def score_batch_ollama(resume_text: str, jobs: list[dict], model_name: str) -> list[dict]:
    """Score a batch of jobs using local Ollama with batching support."""
    if not OLLAMA_AVAILABLE:
        return []
        
    try:
        # Construct a batch prompt similar to Gemini's
        job_list_str = ""
        for i, job in enumerate(jobs):
            job_list_str += f"\n--- JOB {i+1} (ID: {job.get('id')}) ---\n{job.get('description', '')}\n"

        actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
        prompt = BATCH_SCORE_PROMPT.format(resume_text=actual_resume_data, jobs_json=job_list_str)
        
        logger.info("⚡ Calling local Ollama Batch (%s) for %d jobs...", model_name, len(jobs))
        t0 = time.time()
        # Explicitly set num_ctx to handle large batches (Qwen 2.5 supports up to 128k)
        response = ollama.generate(
            model=model_name, 
            prompt=prompt, 
            stream=False,
            options={"num_ctx": 32768}
        )
        elapsed = time.time() - t0
        logger.info("✅ Ollama Batch complete in %.2fs", elapsed)
        text = response['response'].strip()
        
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"): text = text[4:]
            
        results = json.loads(text)
        if isinstance(results, dict) and "jobs" in results:
            results = results["jobs"]
        
        return results if isinstance(results, list) else []
    except Exception as e:
        logger.error("Ollama batch scoring failed: %s", e)
        return []

def score_job_ollama_best(resume_text: str, job_description: str) -> Optional[dict]:
    """Score using the fastest benchmarked Ollama model."""
    model_name = benchmark_ollama_models()
    if not model_name:
        return None
        
    try:
        logger.debug("Scoring with fastest Ollama model: %s", model_name)
        actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
        prompt = SCORE_PROMPT.format(resume_text=actual_resume_data, job_description=job_description)
        response = ollama.generate(model=model_name, prompt=prompt, stream=False)
        text = response['response'].strip()
        
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"): text = text[4:]
            
        return json.loads(text)
    except Exception as e:
        logger.error("Ollama fallback failed with %s: %s", model_name, e)
        return None


def score_job(resume_text: str, job_description: str, retries: int = 1) -> Optional[dict]:
    """Score job against resume. Try Gemini first (once), then the best Ollama fallback."""
    global _GROQ_EXHAUSTED
    logger.debug("score_job called — resume length: %d chars", len(resume_text))
    
    # 1. Try Groq (Fail Fast) - Only if not already exhausted
    if not _GROQ_EXHAUSTED:
        result = score_job_groq(resume_text, job_description, retries)
        if result:
            return result
    else:
        logger.debug("Skipping Groq as it is already marked as exhausted/rate-limited")

    # 2. Best Ollama Fallback
    logger.info("Attempting best Ollama fallback")
    return score_job_ollama_best(resume_text, job_description)


def score_batch_groq(resume_text: str, jobs: list[dict], retries: int = 3) -> list[dict]:
    """Score a batch of jobs together using Groq."""
    global _GROQ_EXHAUSTED
    if not GROQ_AVAILABLE:
        return []

    client = get_groq_client()
    if not client:
        return []
    
    # Prepare jobs for the prompt (only id and description to save tokens)
    jobs_to_send = [
        {"id": j.get("id"), "description": j.get("description", "")[:2000]}
        for j in jobs
    ]
    
    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    prompt = BATCH_SCORE_PROMPT.format(
        resume_text=actual_resume_data,
        jobs_json=json.dumps(jobs_to_send)
    )

    model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    for attempt in range(retries):
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
            
            results = json.loads(text)
            if isinstance(results, list):
                return results
            elif isinstance(results, dict) and "jobs" in results:
                return results["jobs"]
            return []
        except Exception as e:
            if "429" in str(e) or "rate_limit_exceeded" in str(e).lower():
                _GROQ_EXHAUSTED = True
                raise e
            logger.error("Groq batch scoring error: %s", e)
            time.sleep(2)
    
    return []

def score_batch_nim(resume_text: str, jobs: list[dict]) -> list[dict]:
    """Score a batch of jobs using NVIDIA NIM (streaming SSE)."""
    if not NIM_AVAILABLE:
        logger.debug("NIM client not available — skipping")
        return []
    import requests as req

    api_key, base_url = get_nim_config()
    if not api_key:
        return []

    model_name = os.getenv("NIM_MODEL", "mistralai/mistral-large-3-675b-instruct-2512")
    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    prompt = BATCH_SCORE_PROMPT.format(
        resume_text=actual_resume_data,
        jobs_json=json.dumps(jobs, indent=2)
    )

    invoke_url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.15,
        "top_p": 1.00,
        "frequency_penalty": 0.00,
        "presence_penalty": 0.00,
        "stream": True,
    }

    for attempt in range(2):
        try:
            logger.info("⚡ Calling NVIDIA NIM (%s) for batch of %d jobs (streaming, attempt %d/2)...", model_name, len(jobs), attempt + 1)
            t0 = time.time()
            response = req.post(invoke_url, headers=headers, json=payload, stream=True, timeout=300)
            response.raise_for_status()

            # Accumulate streamed content from SSE chunks
            full_content = []
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content_piece = delta.get("content", "")
                        if content_piece:
                            full_content.append(content_piece)
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

            elapsed = time.time() - t0
            text = "".join(full_content).strip()
            logger.info("✅ NVIDIA NIM streaming complete in %.2fs — response length: %d chars", elapsed, len(text))

            # Clean up markdown fences if present
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            # Find JSON array boundaries
            start_idx = text.find('[')
            end_idx = text.rfind(']')
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx+1]

            results = json.loads(text)
            if isinstance(results, list):
                return results
            elif isinstance(results, dict):
                # Model may wrap in "jobs", "matches", "results", etc.
                for key in results:
                    if isinstance(results[key], list):
                        return results[key]
            return []
        except Exception as e:
            logger.error("NVIDIA NIM batch scoring error (attempt %d/2): %s", attempt + 1, e)
            if attempt < 1:
                time.sleep(2)
    return []



def score_batch_claude(resume_text: str, jobs: list[dict], retries: int = 3) -> list[dict]:
    """Score a batch of jobs together using Anthropic Claude."""
    if not ANTHROPIC_AVAILABLE:
        logger.debug("Anthropic SDK not installed — skipping")
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or "your_anthropic_api_key" in api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping Claude scoring")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    
    # Prepare jobs for the prompt (truncate descriptions to fit 100 jobs in context)
    jobs_to_send = [
        {"id": j.get("id"), "description": j.get("description", "")[:1500]}
        for j in jobs
    ]
    
    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    prompt = BATCH_SCORE_PROMPT.format(
        resume_text=actual_resume_data,
        jobs_json=json.dumps(jobs_to_send)
    )

    model_name = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
    for attempt in range(retries):
        try:
            logger.info("Calling Anthropic Claude (%s) for batch of %d jobs...", model_name, len(jobs))
            t0 = time.time()
            response = client.messages.create(
                model=model_name,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            elapsed = time.time() - t0
            logger.info("Claude Batch complete in %.2fs", elapsed)
            
            text = response.content[0].text.strip()
            
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            
            results = json.loads(text)
            if isinstance(results, list):
                return results
            elif isinstance(results, dict) and "jobs" in results:
                return results["jobs"]
            return []
        except Exception as e:
            logger.error("Claude batch scoring error (attempt %d/%d): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(2)
    
    return []


def score_batch_claudecode(resume_text: str, jobs: list[dict], retries: int = 2) -> list[dict]:
    """Score a batch of jobs using the Claude Code CLI tool (uses Claude Pro subscription)."""
    import subprocess
    import tempfile
    
    # Check if claude CLI is available
    try:
        subprocess.run(["claude", "--version"], capture_output=True, check=True)
    except:
        logger.debug("Claude CLI not found or failed — skipping")
        return []

    # Prepare jobs for the prompt
    jobs_to_send = [
        {"id": j.get("id"), "description": j.get("description", "")[:1500]}
        for j in jobs
    ]
    
    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(jobs_to_send, f)
        temp_path = f.name

    try:
        prompt = f"""
        ACT AS AN ATS SYSTEM AND EXPERT RECRUITER.
        
        CANDIDATE SKILLS:
        {actual_resume_data}
        
        JOBS TO SCORE (FROM FILE {temp_path}):
        Analyze each job in the provided JSON file against my skills.
        
        RETURN ONLY VALID JSON LIST OF OBJECTS (NO MARKDOWN, NO EXPLANATION):
        [
          {{
            "id": "job_id",
            "score": 0-100,
            "matching_skills": [],
            "missing_skills": [],
            "recommendation": "Short summary"
          }}
        ]
        """
        
        for attempt in range(retries):
            try:
                logger.info("⚡ Calling Claude Code CLI for batch of %d jobs...", len(jobs))
                t0 = time.time()
                # Use --print for non-interactive output
                result = subprocess.run(
                    ["claude", "-p", prompt, "--print"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                elapsed = time.time() - t0
                logger.info("✅ Claude Code CLI complete in %.2fs", elapsed)
                
                text = result.stdout.strip()
                
                # Clean up ANSI escape codes if present
                import re
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                text = ansi_escape.sub('', text)
                
                # Extract JSON if wrapped in markdown
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                
                # Find the first '[' and last ']' to extract the JSON array
                start_idx = text.find('[')
                end_idx = text.rfind(']')
                if start_idx != -1 and end_idx != -1:
                    text = text[start_idx:end_idx+1]

                results = json.loads(text)
                if isinstance(results, list):
                    return results
                return []
            except Exception as e:
                logger.error("Claude CLI scoring error (attempt %d/%d): %s", attempt + 1, retries, e)
                if attempt < retries - 1:
                    time.sleep(5)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return []


def score_batch(resume_text: str, jobs: list[dict], batch_size: int = 50, max_workers: int = 1, on_chunk_complete=None) -> list[dict]:
    """Score multiple jobs using NVIDIA NIM (Mistral) as the primary scorer."""
    scored_jobs_map = {}
    best_ollama = benchmark_ollama_models()
    
    # 1. Score all jobs via NVIDIA NIM (Mistral)
    nim_batch_size = int(os.getenv("NIM_BATCH_SIZE", "5"))
    logger.info("Starting NVIDIA NIM batch scoring — %d jobs in chunks of %d", len(jobs), nim_batch_size)
    
    chunks = [jobs[i:i + nim_batch_size] for i in range(0, len(jobs), nim_batch_size)]
    for chunk in chunks:
        try:
            results = score_batch_nim(resume_text, chunk)
            if results:
                for res in results:
                    scored_jobs_map[res.get("id")] = res
                if on_chunk_complete:
                    on_chunk_complete(results)
        except Exception as e:
            logger.error("NVIDIA NIM batch failed for a chunk: %s", e)

    # 2. Fallback: Ollama for any remaining unscored jobs
    unscored_jobs = [j for j in jobs if j.get("id") not in scored_jobs_map]
    if unscored_jobs and best_ollama:
        logger.info("Fallback: Scoring %d remaining jobs via Ollama Batch (%s)", len(unscored_jobs), best_ollama)
        for i in range(0, len(unscored_jobs), 5):
            chunk = unscored_jobs[i:i+5]
            results = score_batch_ollama(resume_text, chunk, best_ollama)
            if results:
                for res in results:
                    scored_jobs_map[res.get("id")] = res
                if on_chunk_complete:
                    on_chunk_complete(results)
    elif unscored_jobs:
        logger.warning("%d jobs remain unscored — NIM failed and no local Ollama fallback available.", len(unscored_jobs))

    # Assemble final list
    final_jobs = []
    for i, job in enumerate(jobs):
        job_id = job.get("id")
        score_data = scored_jobs_map.get(job_id)
        
        if not score_data:
            score_data = {"score": 0, "matching_skills": [], "missing_skills": []}

        job["score"] = score_data.get("score", 0)
        job["matching_skills"] = score_data.get("matching_skills", [])
        job["missing_skills"] = score_data.get("missing_skills", [])
        job["recommendation"] = score_data.get("recommendation", "")
        final_jobs.append(job)

    return final_jobs
