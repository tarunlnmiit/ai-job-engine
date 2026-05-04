# Job Hunt Automation Tool — Technical Blueprint

---

## 1. What This Tool Does

A locally-run Streamlit app that:
1. Scrapes jobs from Indian + global (remote-friendly) portals
2. Scores each job against your resume using Gemini Flash
3. Tailors your resume per JD (ATS-optimized + formatted)
4. Auto-applies on platforms with Easy Apply (LinkedIn, Instahyre, etc.)
5. Flags non-auto-apply jobs, fetches contact/network info
6. Maintains an Excel tracker with all job metadata
7. Runs on a Streamlit dashboard for monitoring

---

## 2. LLM Stack

| Task | LLM | Why |
|---|---|---|
| Job scoring against resume | **Gemini Flash** (free API) | Fast, 1M token/day free, large context |
| Resume tailoring per JD | **Gemini Flash** | Best instruction following for formatting |
| Skill gap extraction | **Gemini Flash** | Structured output |
| Contact/network info parsing | **Gemini Flash** | Pattern extraction |
| Offline fallback / batching | **Ollama gemma4** | When Gemini rate-limited |

**Gemini Flash Free Limits:** 15 RPM, 1,500 requests/day, 1M tokens/day — sufficient for ~100-200 jobs/day.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   STREAMLIT DASHBOARD                   │
│  Search Config │ Job Feed │ Apply Queue │ Tracker        │
└───────────────────────────┬─────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  [Scraper Engine]   [AI Engine]         [Apply Engine]
  - LinkedIn         - Gemini Flash      - Selenium
  - Naukri           - Ollama gemma4     - Auto-apply
  - Wellfound        - Scoring           - Resume mod
  - Indeed IN        - Tailoring         - Form fill
  - Internshala      - ATS check         - Flag manual
  - Greenhouse
  - Lever
  - Remotive
  - WeWorkRemotely
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                   [Excel Tracker]
                   jobs_tracker.xlsx
```

---

## 4. Tech Stack

```
Language:       Python 3.11+
UI:             Streamlit
Scraping:       Playwright (headless), BeautifulSoup4, httpx
Browser Auto:   Playwright (apply) or Selenium
AI:             google-generativeai (Gemini Flash), ollama
Resume Gen:     python-docx (modify), reportlab (PDF export)
Excel:          openpyxl
Scheduling:     APScheduler (auto-refresh)
Storage:        SQLite (job cache) + Excel (tracker)
Config:         .env file + Streamlit secrets
```

---

## 5. Project Structure

```
job_hunt_tool/
├── app.py                    # Streamlit entry point
├── .env                      # GEMINI_API_KEY, LinkedIn creds
├── config.yaml               # Search preferences
├── requirements.txt
│
├── core/
│   ├── scraper/
│   │   ├── linkedin.py       # LinkedIn job scraper
│   │   ├── naukri.py         # Naukri.com scraper
│   │   ├── wellfound.py      # Wellfound (AngelList) scraper
│   │   ├── indeed.py         # Indeed India + global
│   │   ├── greenhouse.py     # Greenhouse API jobs
│   │   ├── lever.py          # Lever API jobs
│   │   ├── remotive.py       # Remotive.com (remote jobs)
│   │   ├── weworkremotely.py # WeWorkRemotely
│   │   ├── instahyre.py      # Instahyre
│   │   └── base.py           # BaseJobScraper class
│   │
│   ├── ai/
│   │   ├── scorer.py         # Score job vs resume
│   │   ├── resume_tailor.py  # Modify resume per JD
│   │   ├── ats_checker.py    # ATS keyword analysis
│   │   └── contact_finder.py # Extract contact/network hints
│   │
│   ├── apply/
│   │   ├── linkedin_apply.py # LinkedIn Easy Apply automation
│   │   ├── form_filler.py    # Generic form auto-fill
│   │   └── apply_router.py   # Decide: auto vs manual flag
│   │
│   ├── resume/
│   │   ├── parser.py         # Parse uploaded resume
│   │   ├── modifier.py       # python-docx modifications
│   │   └── pdf_exporter.py   # Export to PDF
│   │
│   └── tracker/
│       ├── db.py             # SQLite job cache
│       └── excel.py          # Excel tracker updates
│
├── pages/
│   ├── 1_Search.py           # Configure & trigger search
│   ├── 2_Job_Feed.py         # Browse scored jobs
│   ├── 3_Apply_Queue.py      # Review & apply
│   ├── 4_Manual_Queue.py     # Jobs needing manual apply
│   └── 5_Tracker.py          # Excel tracker view
│
├── resume/
│   └── my_resume.docx        # Your master resume
│
└── data/
    ├── jobs.db               # SQLite cache
    └── jobs_tracker.xlsx     # Excel tracker
```

---

## 6. Module Details

### 6.1 config.yaml — Search Configuration

```yaml
search:
  roles:
    - "Product Manager"
    - "Senior Product Manager"
    - "Associate Product Manager"
  locations:
    - "India"
    - "Remote"
  experience_years: 3
  salary_min_inr: 1500000   # 15 LPA
  remote_ok: true
  
portals:
  - linkedin
  - naukri
  - wellfound
  - indeed_india
  - greenhouse
  - lever
  - remotive
  - weworkremotely

ai:
  primary: gemini-flash
  fallback: ollama/gemma4
  score_threshold: 65       # Only show jobs scoring >= 65%

apply:
  auto_apply_platforms:
    - linkedin
    - instahyre
  linkedin_email: "your@email.com"
```

---

### 6.2 Job Scraper — Base Class

```python
# core/scraper/base.py
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    salary: Optional[str]
    description: str
    skills_required: list[str]
    experience_required: Optional[str]
    posted_date: Optional[datetime]
    application_url: str
    platform: str
    is_remote: bool
    is_easy_apply: bool
    score: Optional[float] = None
    status: str = "new"       # new | applied | manual | skipped
    contact_info: Optional[str] = None

class BaseJobScraper:
    def search(self, role: str, location: str, **kwargs) -> list[Job]:
        raise NotImplementedError
```

---

### 6.3 LinkedIn Scraper

```python
# core/scraper/linkedin.py
# Uses Playwright to scrape LinkedIn Jobs (no official API for jobs)

from playwright.async_api import async_playwright
from .base import BaseJobScraper, Job
import asyncio, hashlib, re

class LinkedInScraper(BaseJobScraper):
    BASE_URL = "https://www.linkedin.com/jobs/search/"

    async def search(self, role: str, location: str = "India", 
                     remote: bool = True) -> list[Job]:
        jobs = []
        params = f"?keywords={role}&location={location}"
        if remote:
            params += "&f_WT=2"  # Remote filter

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(self.BASE_URL + params)
            await page.wait_for_selector(".jobs-search__results-list")
            
            cards = await page.query_selector_all(".job-search-card")
            for card in cards[:50]:  # First 50 results
                job = await self._parse_card(card, page)
                if job:
                    jobs.append(job)
            
            await browser.close()
        return jobs

    async def _parse_card(self, card, page) -> Job:
        # Extract title, company, location, salary, URL
        # Click into job to get full description
        # Check if Easy Apply button exists
        ...
```

---

### 6.4 Naukri Scraper

```python
# core/scraper/naukri.py
# Naukri has a semi-public API endpoint

import httpx
from .base import BaseJobScraper, Job

class NaukriScraper(BaseJobScraper):
    API_URL = "https://www.naukri.com/jobapi/v3/search"
    
    def search(self, role: str, experience: int = 3) -> list[Job]:
        headers = {
            "appid": "109",
            "systemid": "109",
            "content-type": "application/json"
        }
        params = {
            "noOfResults": 50,
            "urlType": "search_by_key_loc",
            "searchType": "adv",
            "keyword": role,
            "experience": experience,
            "k": role,
            "location": "india"
        }
        r = httpx.get(self.API_URL, params=params, headers=headers)
        return self._parse_response(r.json())
    
    def _parse_response(self, data: dict) -> list[Job]:
        jobs = []
        for item in data.get("jobDetails", []):
            jobs.append(Job(
                id=item["jobId"],
                title=item["title"],
                company=item["companyName"],
                salary=item.get("salary", "Not disclosed"),
                description=item.get("jobDescription", ""),
                skills_required=item.get("tagsAndSkills", "").split(","),
                platform="naukri",
                application_url=item["jdURL"],
                is_easy_apply=False,
                is_remote="remote" in item.get("placeholders", [{}])[0]
                    .get("label", "").lower(),
                location=item.get("placeholders", [{}])[0].get("label", "India"),
                posted_date=None,
                experience_required=item.get("experienceText"),
            ))
        return jobs
```

---

### 6.5 Greenhouse & Lever (API-based, cleanest data)

```python
# core/scraper/greenhouse.py
# Greenhouse has a public jobs board API — no auth needed

import httpx
from .base import BaseJobScraper, Job

# Known companies using Greenhouse:
GREENHOUSE_COMPANIES = [
    "airbnb", "stripe", "notion", "figma", "linear",
    "remote", "deel", "gitlab", "hashicorp", "databricks"
    # Add more — check jobs.lever.co / boards.greenhouse.io
]

class GreenhouseScraper(BaseJobScraper):
    def search(self, role: str) -> list[Job]:
        jobs = []
        for company in GREENHOUSE_COMPANIES:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
            try:
                r = httpx.get(url, timeout=10)
                data = r.json()
                for j in data.get("jobs", []):
                    if role.lower() in j["title"].lower():
                        jobs.append(Job(
                            id=str(j["id"]),
                            title=j["title"],
                            company=company,
                            location=j["location"]["name"],
                            description=j.get("content", ""),
                            skills_required=[],
                            platform="greenhouse",
                            application_url=j["absolute_url"],
                            is_easy_apply=False,
                            is_remote="remote" in j["location"]["name"].lower(),
                            salary=None,
                            posted_date=None,
                            experience_required=None,
                        ))
            except:
                pass
        return jobs
```

---

### 6.6 AI Scorer — Gemini Flash

```python
# core/ai/scorer.py
import google.generativeai as genai
import json

genai.configure(api_key="YOUR_GEMINI_API_KEY")
model = genai.GenerativeModel("gemini-3-flash-preview")

SCORE_PROMPT = """
You are an expert recruiter and ATS system.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Analyze the match and return ONLY valid JSON (no markdown):
{{
  "score": <0-100 integer>,
  "matching_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3", "skill4"],
  "experience_match": "strong|partial|weak",
  "salary_fit": "above|within|below|unknown",
  "recommendation": "One sentence summary",
  "ats_keywords_present": ["kw1", "kw2"],
  "ats_keywords_missing": ["kw3", "kw4"]
}}
"""

def score_job(resume_text: str, job: dict) -> dict:
    prompt = SCORE_PROMPT.format(
        resume_text=resume_text,
        job_description=job["description"]
    )
    response = model.generate_content(prompt)
    return json.loads(response.text)
```

---

### 6.7 Resume Tailor — Gemini Flash

```python
# core/ai/resume_tailor.py

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
"""

def tailor_resume(resume_text: str, job: dict, missing_keywords: list) -> str:
    prompt = TAILOR_PROMPT.format(
        resume_text=resume_text,
        job_description=job["description"],
        missing_keywords=", ".join(missing_keywords)
    )
    response = model.generate_content(prompt)
    return response.text
```

---

### 6.8 LinkedIn Auto-Apply

```python
# core/apply/linkedin_apply.py
from playwright.async_api import async_playwright
import asyncio

class LinkedInAutoApply:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    async def apply(self, job_url: str, resume_path: str) -> dict:
        """
        Returns: {"status": "applied"|"failed"|"manual_required", "reason": str}
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # visible for debug
            page = await browser.new_page()
            
            # Login
            await self._login(page)
            
            # Navigate to job
            await page.goto(job_url)
            await page.wait_for_load_state("networkidle")
            
            # Check for Easy Apply button
            easy_apply_btn = await page.query_selector(
                "button[aria-label*='Easy Apply']"
            )
            if not easy_apply_btn:
                return {"status": "manual_required", 
                        "reason": "No Easy Apply button found"}
            
            await easy_apply_btn.click()
            
            # Handle multi-step form
            result = await self._fill_application_form(page, resume_path)
            await browser.close()
            return result

    async def _fill_application_form(self, page, resume_path: str) -> dict:
        """Navigate through LinkedIn Easy Apply steps"""
        max_steps = 10
        for step in range(max_steps):
            await asyncio.sleep(1)
            
            # Upload resume if prompted
            file_input = await page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(resume_path)
            
            # Fill text inputs with profile data if empty
            # (LinkedIn usually pre-fills from profile)
            
            # Check for Next/Review/Submit
            next_btn = await page.query_selector("button[aria-label='Continue to next step']")
            submit_btn = await page.query_selector("button[aria-label='Submit application']")
            review_btn = await page.query_selector("button[aria-label='Review your application']")
            
            if submit_btn:
                await submit_btn.click()
                return {"status": "applied", "reason": "Application submitted"}
            elif review_btn:
                await review_btn.click()
            elif next_btn:
                await next_btn.click()
            else:
                # Unknown state — flag for manual
                return {"status": "manual_required", 
                        "reason": f"Unknown form state at step {step}"}
        
        return {"status": "manual_required", "reason": "Too many steps"}
```

---

### 6.9 Excel Tracker

```python
# core/tracker/excel.py
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from datetime import datetime

COLUMNS = [
    "Job ID", "Date Found", "Date Applied", "Platform", "Company",
    "Role", "Location", "Remote", "Salary", "Score (%)",
    "Matching Skills", "Missing Skills", "Status",
    "Application URL", "Contact Person", "Contact Email",
    "LinkedIn Network Match", "Notes"
]

STATUS_COLORS = {
    "applied": "C6EFCE",      # Green
    "manual_required": "FFEB9C", # Yellow  
    "skipped": "F2F2F2",      # Gray
    "rejected": "FFC7CE",     # Red
    "interview": "BDD7EE",    # Blue
}

def update_tracker(job: dict, filepath: str = "data/jobs_tracker.xlsx"):
    try:
        wb = openpyxl.load_workbook(filepath)
        ws = wb.active
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Job Applications"
        _write_header(ws)
    
    # Check if job already exists (by Job ID)
    existing_rows = {ws.cell(row=r, column=1).value: r 
                     for r in range(2, ws.max_row + 1)}
    
    row_data = [
        job.get("id"),
        job.get("date_found", datetime.now().strftime("%Y-%m-%d")),
        job.get("date_applied", ""),
        job.get("platform"),
        job.get("company"),
        job.get("title"),
        job.get("location"),
        "Yes" if job.get("is_remote") else "No",
        job.get("salary", "N/A"),
        job.get("score"),
        ", ".join(job.get("matching_skills", [])),
        ", ".join(job.get("missing_skills", [])),
        job.get("status", "new"),
        job.get("application_url"),
        job.get("contact_person", ""),
        job.get("contact_email", ""),
        job.get("linkedin_network_match", ""),
        job.get("notes", ""),
    ]
    
    if job["id"] in existing_rows:
        row = existing_rows[job["id"]]
    else:
        row = ws.max_row + 1
    
    for col, value in enumerate(row_data, 1):
        cell = ws.cell(row=row, column=col, value=value)
        if col == 13:  # Status column
            color = STATUS_COLORS.get(value, "FFFFFF")
            cell.fill = PatternFill("solid", fgColor=color)
    
    wb.save(filepath)

def _write_header(ws):
    for col, header in enumerate(COLUMNS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.font = Font(bold=True, color="FFFFFF")
```

---

### 6.10 Contact Finder (LinkedIn Network Check)

```python
# core/ai/contact_finder.py
# Two approaches:
# 1. Scrape LinkedIn for people at the company (requires login)
# 2. Gemini to infer likely contact from job posting metadata

async def find_contacts(company: str, job_url: str, page) -> dict:
    """
    Searches LinkedIn for:
    - People at this company in your 1st/2nd connections
    - HR/Talent Acquisition/Recruiter at this company
    Returns name, title, LinkedIn URL
    """
    search_url = (
        f"https://www.linkedin.com/search/results/people/"
        f"?keywords={company}+recruiter&network=%5B%22F%22%2C%22S%22%5D"
    )
    await page.goto(search_url)
    await page.wait_for_load_state("networkidle")
    
    contacts = []
    results = await page.query_selector_all(".reusable-search__result-container")
    for result in results[:3]:
        name = await result.query_selector(".actor-name")
        title = await result.query_selector(".subline-level-1")
        link = await result.query_selector("a.app-aware-link")
        
        if name and title:
            contacts.append({
                "name": await name.inner_text(),
                "title": await title.inner_text(),
                "url": await link.get_attribute("href") if link else None
            })
    
    return contacts
```

---

## 7. Streamlit Pages

### app.py (entry)

```python
import streamlit as st

st.set_page_config(
    page_title="Job Hunt Automation",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 Job Hunt Automation Dashboard")
st.markdown("Use the sidebar to navigate between modules.")

# Show summary stats
col1, col2, col3, col4 = st.columns(4)
col1.metric("Jobs Found Today", st.session_state.get("jobs_found", 0))
col2.metric("Auto-Applied", st.session_state.get("auto_applied", 0))
col3.metric("Manual Queue", st.session_state.get("manual_queue", 0))
col4.metric("Avg Match Score", f"{st.session_state.get('avg_score', 0):.0f}%")
```

### pages/1_Search.py

```python
import streamlit as st
import yaml

st.header("⚙️ Search Configuration")

with st.form("search_config"):
    roles = st.text_area("Target Roles (one per line)", 
                          value="Product Manager\nSenior PM")
    min_score = st.slider("Minimum Match Score to Show", 0, 100, 65)
    platforms = st.multiselect("Platforms to Search", 
        ["linkedin", "naukri", "wellfound", "greenhouse", "lever", 
         "remotive", "weworkremotely", "indeed_india"])
    remote_only = st.checkbox("Include Remote-from-India roles", value=True)
    
    submitted = st.form_submit_button("🚀 Start Search")

if submitted:
    with st.spinner("Searching across all platforms..."):
        # Run scrapers, score jobs, update tracker
        from core.scraper import run_all_scrapers
        jobs = run_all_scrapers(roles.split("\n"), platforms, remote_only)
        st.success(f"Found {len(jobs)} jobs. Scoring with Gemini Flash...")
        # Score and store in session state
```

### pages/2_Job_Feed.py

```python
import streamlit as st
import pandas as pd

st.header("📋 Job Feed")

# Filter controls
col1, col2, col3 = st.columns(3)
platform_filter = col1.multiselect("Platform", options=["All", "LinkedIn", "Naukri"...])
score_filter = col2.slider("Min Score", 0, 100, 65)
status_filter = col3.selectbox("Status", ["All", "New", "Applied", "Manual Queue"])

# Display jobs as cards
for job in filtered_jobs:
    with st.expander(f"[{job.score}%] {job.title} @ {job.company} | {job.platform}"):
        col1, col2 = st.columns([2,1])
        col1.markdown(f"**Location:** {job.location}  \n**Salary:** {job.salary}")
        col1.markdown(f"**Skills Required:** {', '.join(job.skills_required)}")
        col2.metric("Match Score", f"{job.score}%")
        col2.markdown(f"**Missing:** {', '.join(job.missing_skills[:5])}")
        
        col_a, col_b, col_c = st.columns(3)
        if col_a.button("✅ Auto Apply", key=f"apply_{job.id}"):
            # Trigger apply flow
            pass
        if col_b.button("👁️ View JD", key=f"jd_{job.id}"):
            st.markdown(job.description)
        col_c.link_button("🔗 Open", job.application_url)
```

### pages/3_Apply_Queue.py

```python
st.header("🤖 Auto-Apply Queue")
st.info("Review jobs before auto-applying. Resume will be tailored per JD.")

for job in auto_apply_queue:
    with st.expander(f"{job.title} @ {job.company}"):
        if st.button(f"Tailor & Apply — {job.company}", key=job.id):
            with st.spinner("Tailoring resume with Gemini Flash..."):
                tailored = tailor_resume(resume_text, job, job.missing_skills)
                st.text_area("Tailored Resume Preview", tailored, height=400)
                if st.button("Confirm & Apply"):
                    result = await linkedin_apply(job.url, tailored_resume_path)
                    st.success(result["status"])
```

### pages/4_Manual_Queue.py

```python
st.header("🚩 Manual Application Queue")

for job in manual_queue:
    with st.expander(f"{job.title} @ {job.company}"):
        st.warning(f"**Reason flagged:** {job.flag_reason}")
        st.markdown(f"**Apply here:** [{job.application_url}]({job.application_url})")
        
        if job.contacts:
            st.markdown("**💼 People to reach out to:**")
            for c in job.contacts:
                st.markdown(f"- [{c['name']}]({c['url']}) — {c['title']}")
        
        notes = st.text_area("Your Notes", key=f"notes_{job.id}")
        if st.button("Mark as Applied Manually", key=f"done_{job.id}"):
            update_tracker(job, status="applied", notes=notes)
```

### pages/5_Tracker.py

```python
import streamlit as st
import pandas as pd

st.header("📊 Application Tracker")

df = pd.read_excel("data/jobs_tracker.xlsx")

# Summary metrics
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Applied", len(df[df.Status=="applied"]))
col2.metric("Interviews", len(df[df.Status=="interview"]))
col3.metric("Manual Pending", len(df[df.Status=="manual_required"]))
col4.metric("Avg Score", f"{df['Score (%)'].mean():.0f}%")
col5.metric("Response Rate", 
    f"{len(df[df.Status=='interview'])/max(len(df),1)*100:.0f}%")

# Filterable table
st.dataframe(df, use_container_width=True)

# Download button
st.download_button("⬇️ Download Excel", 
    open("data/jobs_tracker.xlsx","rb").read(),
    "jobs_tracker.xlsx")
```

---

## 8. Installation Steps

```bash
# 1. Clone / create project folder
mkdir job_hunt_tool && cd job_hunt_tool

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install streamlit playwright beautifulsoup4 httpx \
    google-generativeai python-docx openpyxl pandas \
    apscheduler pyyaml python-dotenv ollama reportlab

# 4. Install Playwright browsers
playwright install chromium

# 5. Create .env
echo "GEMINI_API_KEY=your_key_here" > .env
echo "LINKEDIN_EMAIL=your@email.com" >> .env
echo "LINKEDIN_PASSWORD=yourpassword" >> .env

# 6. Run the app
streamlit run app.py
```

---

## 9. Job Portals Coverage

### India-Focused
| Portal | Method | Easy Apply | Notes |
|---|---|---|---|
| LinkedIn India | Playwright scrape | ✅ Yes | Best coverage |
| Naukri.com | Semi-public API | ❌ | Largest India DB |
| Instahyre | Playwright | ✅ | Startup-focused |
| Internshala | Playwright | ✅ | Fresher + exp |
| Shine.com | Playwright | ❌ | |
| Foundit (Monster) | API | ❌ | |

### Global Remote (India-eligible)
| Portal | Method | Easy Apply | Notes |
|---|---|---|---|
| Wellfound (AngelList) | API + Playwright | Partial | Startups |
| Greenhouse boards | Public API ✅ | ❌ | Best API |
| Lever boards | Public API ✅ | ❌ | Best API |
| Remotive.com | RSS Feed | ❌ | Remote only |
| WeWorkRemotely | RSS + Playwright | ❌ | Remote only |
| Remote.com | Playwright | ❌ | |
| Himalayas.app | Playwright | ❌ | |
| LinkedIn (global) | Playwright | ✅ | Unified |

---

## 10. Gemini Flash Integration Details

```python
# Gemini 1.5 Flash — Free tier
# 15 requests/minute, 1M tokens/day

import google.generativeai as genai
import time

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-3-flash-preview")

def safe_gemini_call(prompt: str, retries: int = 3) -> str:
    for i in range(retries):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if "429" in str(e):  # Rate limited
                time.sleep(60)   # Wait 1 min, then retry
            else:
                raise e
    return None

# Batch processing: score 15 jobs/min = ~900 jobs/hour
# For 100 jobs: ~7 minutes total scoring time
```

---

## 11. Ollama / gemma4 Fallback

```python
# core/ai/ollama_fallback.py
import ollama

def score_job_local(resume_text: str, job_description: str) -> dict:
    """Use when Gemini is rate-limited"""
    prompt = f"""
    Score this resume against this job description.
    Resume: {resume_text[:2000]}
    Job: {job_description[:2000]}
    Return JSON with: score (0-100), matching_skills, missing_skills
    """
    response = ollama.chat(
        model="gemma4",
        messages=[{"role": "user", "content": prompt}]
    )
    # Parse response.message.content
    import json
    return json.loads(response.message.content)
```

---

## 12. Excel Tracker Schema

| Column | Description |
|---|---|
| Job ID | Unique ID from platform |
| Date Found | When scraped |
| Date Applied | When applied |
| Platform | linkedin / naukri / etc |
| Company | Company name |
| Role | Job title |
| Location | Job location |
| Remote | Yes/No |
| Salary | Salary range if available |
| Score (%) | Gemini match score |
| Matching Skills | Skills you have that match |
| Missing Skills | Skills gap |
| Status | new / applied / manual_required / interview / rejected |
| Application URL | Direct link |
| Contact Person | Name from LinkedIn |
| Contact Email | If available |
| LinkedIn Network Match | 1st/2nd degree connection |
| Notes | Your personal notes |

---

## 13. What You Do vs What the Tool Does

### Tool Does Automatically
- Searches all configured portals on schedule
- Scores jobs against your resume via Gemini Flash
- Filters below your threshold score
- Tailors resume per JD
- Applies on LinkedIn Easy Apply + Instahyre
- Updates Excel tracker with all metadata
- Finds recruiter/network contacts at companies

### You Do Manually
- Review tailored resume before applying (one-click confirm)
- Handle CAPTCHA / 2FA during LinkedIn login
- Apply to flagged manual-only jobs
- Reach out to network contacts identified by tool
- Update interview outcomes in tracker
- Provide/update your master resume
- Decide salary negotiation strategy

---

## 14. Anti-Detection / Ethics Notes

- Add random delays between scrapes (2-5 seconds)
- Rotate User-Agent strings
- Use your real LinkedIn credentials (not fake)
- Respect `robots.txt` — Greenhouse/Lever APIs are fully allowed
- LinkedIn scraping is against ToS — keep volumes reasonable (<100/day)
- Never apply to a job you're not genuinely interested in

---

## 15. Phase-wise Build Plan

### Phase 1 (Week 1) — Core Pipeline
- [ ] Set up project structure + Streamlit shell
- [ ] Build Greenhouse + Lever scrapers (easiest, public APIs)
- [ ] Implement Gemini Flash scoring
- [ ] Build Excel tracker
- [ ] Streamlit: Job Feed page

### Phase 2 (Week 2) — India Portals
- [ ] Naukri scraper (semi-public API)
- [ ] LinkedIn scraper (Playwright)
- [ ] Resume parser (python-docx)
- [ ] Resume tailor with Gemini Flash
- [ ] Streamlit: Apply Queue page

### Phase 3 (Week 3) — Auto-Apply
- [ ] LinkedIn Easy Apply automation
- [ ] Contact finder (LinkedIn network)
- [ ] Manual queue with contact info
- [ ] Ollama fallback integration

### Phase 4 (Week 4) — Polish
- [ ] Auto-scheduler (APScheduler)
- [ ] Streamlit: Analytics/Tracker page
- [ ] Email digest of daily job finds
- [ ] Fine-tune score thresholds

---

## 16. requirements.txt

```
streamlit>=1.35.0
playwright>=1.44.0
beautifulsoup4>=4.12.0
httpx>=0.27.0
google-generativeai>=0.7.0
python-docx>=1.1.0
openpyxl>=3.1.0
pandas>=2.2.0
apscheduler>=3.10.0
pyyaml>=6.0.1
python-dotenv>=1.0.0
ollama>=0.2.0
reportlab>=4.2.0
lxml>=5.2.0
```

---

*Document version: 1.0 | Build with Python 3.11+ | Gemini Flash free API | Ollama gemma4 fallback*
