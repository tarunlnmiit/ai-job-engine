import os
import json
import time
from typing import Optional
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"), override=True)

from logger import get_logger
from core.scorer.claude_subprocess_scorer import score_batch_claude_subprocess as _claude_score_batch

logger = get_logger("ai.scorer")

# All alternative scorers dormant — Claude CLI subprocess is primary
GROQ_AVAILABLE = False
NIM_AVAILABLE = False
OLLAMA_AVAILABLE = False
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


def _recover_partial_json(text: str) -> list:
    """Extract complete JSON objects from a truncated array string."""
    import re
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objects.append(json.loads(text[start:i + 1]))
                except json.JSONDecodeError:
                    pass
                start = None
    if objects:
        logger.warning("NIM JSON truncated — recovered %d/%d objects via partial parse", len(objects), text.count('"id"'))
    return objects



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
            
        # Robust extraction: Find first [ and last ]
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        if start_idx != -1 and end_idx != -1:
            text = text[start_idx:end_idx+1]
            
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


def score_job(resume_text: str, job_description: str, retries: int = 2) -> Optional[dict]:
    """Score single job via Claude Code CLI subprocess."""
    actual_resume = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    results, _ = _claude_score_batch(actual_resume, [{"id": "_single_", "description": job_description}])
    if results:
        return results[0]
    return None


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
    """Score a batch of jobs using NVIDIA NIM via OpenAI-compatible SDK."""
    if not NIM_AVAILABLE:
        logger.debug("NIM client not available — skipping")
        return []

    client = get_nim_client()
    if not client:
        logger.warning("NVIDIA_API_KEY not set — skipping NIM scoring")
        return []

    model_name = os.getenv("NIM_MODEL", "minimaxai/minimax-m2.7")
    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    jobs_to_send = [
        {"id": j.get("id"), "description": j.get("description", "")[:2000]}
        for j in jobs
    ]
    prompt = BATCH_SCORE_PROMPT.format(
        resume_text=actual_resume_data,
        jobs_json=json.dumps(jobs_to_send, indent=2)
    )

    for attempt in range(2):
        try:
            logger.info("⚡ NVIDIA NIM (%s) — batch %d jobs (attempt %d/2)...", model_name, len(jobs), attempt + 1)
            t0 = time.time()

            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.15,
                top_p=1,
                max_tokens=8192,
                stream=True,
            )

            full_content = []
            for chunk in completion:
                if not getattr(chunk, "choices", None) or not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # skip reasoning_content from thinking models (e.g. minimax-m2.7, kimi-k2)
                content = getattr(delta, "content", None)
                if content:
                    full_content.append(content)

            elapsed = time.time() - t0
            text = "".join(full_content).strip()
            logger.info("✅ NIM complete in %.2fs — %d chars", elapsed, len(text))

            # Strip markdown fences
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            # Extract JSON array
            start_idx = text.find('[')
            end_idx = text.rfind(']')
            if start_idx != -1 and end_idx != -1:
                text = text[start_idx:end_idx + 1]

            try:
                results = json.loads(text)
            except json.JSONDecodeError:
                results = _recover_partial_json(text)

            if isinstance(results, list):
                logger.info("NIM parsed %d scored results", len(results))
                return results
            elif isinstance(results, dict):
                for key in results:
                    if isinstance(results[key], list):
                        logger.info("NIM parsed %d scored results (from key '%s')", len(results[key]), key)
                        return results[key]
            logger.warning("NIM returned unexpected JSON shape — raw: %.200s", text)
            return []
        except json.JSONDecodeError as e:
            logger.error("NIM JSON parse failed (attempt %d/2): %s — raw text: %.300s", attempt + 1, e, text)
            if attempt < 1:
                time.sleep(2)
        except Exception as e:
            logger.error("NIM batch error (attempt %d/2): %s", attempt + 1, e)
            if attempt < 1:
                time.sleep(2)
    logger.warning("NIM gave up after 2 attempts — returning []")
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


def score_batch_openrouter(resume_text: str, jobs: list[dict]) -> list[dict]:
    """Score batch via OpenRouter free models with automatic fallback on 429."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "your_" in api_key:
        logger.warning("OPENROUTER_API_KEY missing or placeholder — skipping OpenRouter")
        return []

    try:
        from openai import OpenAI, RateLimitError
    except ImportError:
        logger.warning("openai SDK not installed — skipping OpenRouter (pip install openai)")
        return []

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    primary = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    fallbacks_raw = os.getenv(
        "OPENROUTER_FALLBACK_MODELS",
        "google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free,meta-llama/llama-3.3-70b-instruct:free"
    )
    fallbacks = [m.strip() for m in fallbacks_raw.split(",") if m.strip()]
    models = [primary] + [m for m in fallbacks if m != primary]

    jobs_to_send = [
        {"id": j.get("id"), "description": j.get("description", "")[:2000]}
        for j in jobs
    ]
    actual_resume_data = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    prompt = BATCH_SCORE_PROMPT.format(
        resume_text=actual_resume_data,
        jobs_json=json.dumps(jobs_to_send, indent=2)
    )

    for model in models:
        for attempt in range(2):
            try:
                logger.info("⚡ OpenRouter (%s) — batch %d jobs (attempt %d/2)...", model, len(jobs), attempt + 1)
                # Debug: Show full prompt in terminal
                logger.info("--- OPENROUTER PROMPT ---\n%s\n-----------------------", prompt)
                t0 = time.time()
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=4096,
                )
                elapsed = time.time() - t0
                text = (resp.choices[0].message.content or "").strip()
                logger.info("✅ OpenRouter (%s) done in %.2fs — %d chars", model, elapsed, len(text))
                # Debug: Show full response in terminal
                logger.info("--- OPENROUTER RESPONSE ---\n%s\n-------------------------", text)

                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]

                start_idx = text.find("[")
                end_idx = text.rfind("]")
                if start_idx != -1 and end_idx != -1:
                    text = text[start_idx:end_idx + 1]
                else:
                    logger.warning("OpenRouter (%s) — no JSON array found in response: %.200s", model, text)
                    break

                results = json.loads(text)
                if isinstance(results, list):
                    return results
                elif isinstance(results, dict):
                    # OpenRouter error envelope: {"error": {"message": ..., "code": ...}}
                    if "error" in results:
                        logger.error("OpenRouter (%s) API error: %s", model, results["error"])
                        break
                    for k in results:
                        if isinstance(results[k], list):
                            return results[k]
                    logger.warning("OpenRouter (%s) dict has no list value — keys: %s", model, list(results.keys()))
                    break
            except json.JSONDecodeError as e:
                logger.error("OpenRouter (%s) JSON parse failed: %s — raw: %.300s", model, e, text)
                break
            except RateLimitError:
                if attempt == 0:
                    logger.warning("OpenRouter 429 on %s — retrying after 3s...", model)
                    time.sleep(3)
                    continue
                logger.warning("OpenRouter 429 on %s — trying next model...", model)
                break
            except Exception as e:
                logger.error("OpenRouter error (%s): %s", model, e)
                break

    logger.error("All OpenRouter models exhausted for this batch")
    return []


def score_batch(resume_text: str, jobs: list[dict], batch_size: int = 50, max_workers: int = 1, on_chunk_complete=None) -> list[dict]:
    """Score jobs via Claude Code CLI subprocess. All other scorers dormant."""
    actual_resume = PRE_PARSED_SKILLS if PRE_PARSED_SKILLS else resume_text
    scored_jobs_map: dict = {}

    chunks = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    logger.info("═══ Scoring %d jobs | %d chunks of %d | Claude CLI ═══", len(jobs), len(chunks), batch_size)

    for idx, chunk in enumerate(chunks):
        results, retry_time = _claude_score_batch(actual_resume, chunk)
        if retry_time:
            logger.warning("Claude usage limit — retry after %s. Stopping early.", retry_time)
            break
        newly_scored = []
        for res in results:
            jid = str(res.get("id", "")).strip()
            if jid:
                scored_jobs_map[jid] = res
                newly_scored.append(res)
        logger.info("Chunk %d/%d → %d/%d scored", idx + 1, len(chunks), len(newly_scored), len(chunk))
        if on_chunk_complete and newly_scored:
            on_chunk_complete(newly_scored, scorer="ClaudeCLI")

    final_jobs = []
    for job in jobs:
        job_id = str(job.get("id")).strip()
        score_data = scored_jobs_map.get(job_id) or {"score": 0, "matching_skills": [], "missing_skills": []}
        job["score"] = score_data.get("score", 0)
        job["matching_skills"] = score_data.get("matching_skills", [])
        job["missing_skills"] = score_data.get("missing_skills", [])
        job["recommendation"] = score_data.get("recommendation", "")
        final_jobs.append(job)

    total_scored = sum(1 for j in final_jobs if j.get("score", 0) > 0)
    logger.info("═══ Final: %d/%d scored via Claude CLI ═══", total_scored, len(jobs))
    return final_jobs
