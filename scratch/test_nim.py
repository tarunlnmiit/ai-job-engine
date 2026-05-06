#!/usr/bin/env python3
"""Quick test script for NVIDIA NIM (Mistral) scoring endpoint."""

import os
import sys
import json
import time

# Load .env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import httpx

API_KEY = os.getenv("NVIDIA_API_KEY")
BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = os.getenv("NIM_MODEL", "mistralai/mixtral-8x22b-instruct-v0.1")

# ── Test 1: Simple ping ──────────────────────────────────────────────
def test_simple():
    print("=" * 60)
    print("TEST 1: Simple completion (health check)")
    print(f"  Model:    {MODEL}")
    print(f"  Base URL: {BASE_URL}")
    print(f"  API Key:  {API_KEY[:12]}...{API_KEY[-4:]}" if API_KEY else "  API Key:  ❌ NOT SET")
    print("=" * 60)

    if not API_KEY:
        print("❌ NVIDIA_API_KEY not found in .env — aborting")
        return False

    try:
        t0 = time.time()
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": "Say 'NIM is working' and nothing else."}],
                    "max_tokens": 20,
                },
            )
            elapsed = time.time() - t0

            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                print(f"✅ Response ({elapsed:.2f}s): {text}")
                print(f"   Tokens: prompt={data['usage']['prompt_tokens']}, completion={data['usage']['completion_tokens']}")
                return True
            else:
                print(f"❌ HTTP {response.status_code}: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


# ── Test 2: JSON scoring (mimics score_batch_nim) ────────────────────
def test_batch_scoring():
    print("\n" + "=" * 60)
    print("TEST 2: Batch job scoring (JSON mode)")
    print("=" * 60)

    if not API_KEY:
        print("❌ Skipping — no API key")
        return False

    fake_jobs = [
        {
            "id": "test_job_1",
            "description": "Senior Python Developer — Build ML pipelines using TensorFlow, PyTorch, and AWS SageMaker. 5+ years experience required."
        },
        {
            "id": "test_job_2",
            "description": "Frontend React Developer — Build responsive UIs with React, TypeScript, and GraphQL. No Python needed."
        },
    ]

    fake_skills = {
        "technical_skills": {
            "languages": ["Python", "SQL", "JavaScript"],
            "frameworks": ["TensorFlow", "PyTorch", "FastAPI"],
            "tools": ["AWS SageMaker", "Docker", "Kubernetes"],
        }
    }

    prompt = f"""
YOU RECRUITER. YOU ATS.

ME SKILLS:
{json.dumps(fake_skills, indent=2)}

HUNT JOBS:
{json.dumps(fake_jobs, indent=2)}

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

    for attempt in range(2):
        use_json_mode = (attempt == 0)
        mode_label = "JSON mode" if use_json_mode else "plain text"
        print(f"\n  Attempt {attempt+1}/2 ({mode_label})...")
        
        t0 = time.time()
        body = {
            "model": "mistralai/mistral-large-3-675b-instruct-2512",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.15,
            "top_p": 1.00,
            "frequency_penalty": 0.00,
            "presence_penalty": 0.00,
            "stream": False
        }
        if use_json_mode:
            body["response_format"] = {"type": "json_object"}
        
        try:
            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                    json=body,
                )
                elapsed = time.time() - t0

                if response.status_code != 200:
                    print(f"  ❌ HTTP {response.status_code}: {response.text[:300]}")
                    continue

                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                
                # Extract JSON from markdown if needed
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
                
                # Handle dict-wrapped responses
                if isinstance(results, dict):
                    for key in results:
                        if isinstance(results[key], list):
                            results = results[key]
                            break
                
                if isinstance(results, list):
                    print(f"  ✅ Scored {len(results)} jobs in {elapsed:.2f}s ({mode_label})")
                    print(f"     Tokens: prompt={data['usage']['prompt_tokens']}, completion={data['usage']['completion_tokens']}")
                    for r in results:
                        print(f"\n     📋 Job: {r.get('id')}")
                        print(f"        Score: {r.get('score')}/100")
                        print(f"        Match: {r.get('matching_skills', [])}")
                        print(f"        Miss:  {r.get('missing_skills', [])}")
                        print(f"        Rec:   {r.get('recommendation', '')}")
                    
                    if use_json_mode:
                        print("\n  ℹ️  JSON mode works — scorer.py is good as-is.")
                    else:
                        print("\n  ⚠️  JSON mode failed but plain text works.")
                        print("     Consider removing response_format from scorer.py")
                    return True
                else:
                    print(f"  ⚠️  Unexpected format: {type(results)}")
                    continue
        except Exception as e:
            print(f"  ❌ {mode_label} failed: {e}")
            continue
    
    print("  ❌ Both modes failed.")
    return False


if __name__ == "__main__":
    ok1 = test_simple()
    ok2 = test_batch_scoring() if ok1 else False

    print("\n" + "=" * 60)
    print(f"RESULTS:  Health Check {'✅' if ok1 else '❌'}  |  Batch Scoring {'✅' if ok2 else '❌'}")
    print("=" * 60)
    sys.exit(0 if (ok1 and ok2) else 1)
