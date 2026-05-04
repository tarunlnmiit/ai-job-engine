# Job Hunt Automation Tool

AI-powered job search automation with resume scoring, tailoring, and automated applications.

## ✨ Features

- **12 job portal scrapers**: LinkedIn, Naukri, Greenhouse, Lever, Remotive, WeWorkRemotely, Wellfound, Instahyre, Indeed, Hacker News, Hirist, ArbeitNow
- **AI job scoring**: Groq Llama 3.3 scores jobs against your resume in real-time
- **Resume tailoring**: Automatically tailors resume per job description
- **Auto-apply**: One-click apply to jobs with Easy Apply
- **Contact finding**: Identifies recruiter contacts at target companies
- **Excel tracking**: Complete application tracker with all metadata
- **Streamlit dashboard**: Beautiful real-time UI for search and applications

## 🚀 Quick Start

### 1. Setup

```bash
# Start chrome in debugging mode before running the app
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/Library/Application Support/Google/Chrome_Scraper"

# Clone or navigate to project
cd job_hunt_tool

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (required for LinkedIn, Indeed, etc)
playwright install chromium

# Install BeautifulSoup4 (required for Indeed scraper)
pip install beautifulsoup4
```

### 2. Configure Environment

```bash
# Copy and edit .env template
cp .env.template .env
```

Required:
- `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3` — Get from https://console.groq.com
- `LINKEDIN_EMAIL` — Your LinkedIn email (if using LinkedIn scraper)
- `LINKEDIN_PASSWORD` — Your LinkedIn password (if using LinkedIn scraper)

### 3. Configure Search

Edit `config.yaml`:

```yaml
search:
  roles:
    - "Product Manager"
    - "Senior PM"
  locations:
    - "India"
    - "Remote"
  experience_years: 3
  salary_min_inr: 1500000
  remote_ok: true

portals:
  - linkedin      # Requires auth
  - naukri        # India-focused
  - greenhouse    # Tech companies
  - lever         # Tech companies
  - remotive      # Remote jobs
  - weworkremotely # Remote jobs
  - wellfound     # Startup jobs
  - instahyre     # Indian startups
  - indeed_india  # General jobs (India)
  - hacker_news   # Who is hiring
  - hirist        # India tech jobs
  - arbeitnow     # Europe jobs

ai:
  score_threshold: 65  # Only show jobs 65%+ match
```

### 4. Add Resume

Place your resume at:
- `resume/CV_Tarun_Gupta_1225_updated_No.pdf` (default, auto-detected)
- Or: `resume/my_resume.docx` / `.pdf` / `.txt`

### 5. Run

```bash
streamlit run app.py
```

Visit `http://localhost:8501` in your browser and go to **Search** tab.

## 📖 How It Works

### Phase 1: Search & Score (🔍 Search Tab)

1. **Configure search criteria**: Set target roles, locations, experience level, salary, and select platforms
2. **Scrape jobs**: Tool simultaneously searches all enabled job portals:
   - API-based portals (Greenhouse, Lever, Remotive, Wellfound, Instahyre, Naukri) — fast
   - HTML/RSS portals (Indeed, WeWorkRemotely) — medium speed
   - Browser automation (LinkedIn) — slower but gets Easy Apply status
3. **Score against resume**:
   - Parses your resume (DOCX/PDF/TXT)
   - Sends each job + resume to Groq Llama 3.3
   - Gets score (0-100), matching skills, missing skills
   - **Progress bar** shows real-time status
4. **Filter results**: Only jobs meeting your minimum score threshold appear in Job Feed

### Phase 2: Review & Tailor (📋 Job Feed Tab)

1. Browse all matching jobs with scores
2. Click job to see:
   - Full job description
   - Matching vs. missing skills
   - Match score breakdown
   - Company and apply link
3. Add to **Apply Queue** for jobs you want to pursue

### Phase 3: Apply (🤖 Apply Queue Tab)

1. Review tailored resume (auto-customized per job)
2. One-click apply:
   - **Easy Apply jobs** (LinkedIn, Instahyre, others): Auto-submits tailored resume
   - **Manual jobs**: Opens application link, shows recruiter contact if found
3. Marks job as "applied" in tracker

### Phase 4: Track (📊 Tracker Tab)

1. CSV tracker auto-updates with all applications
2. Monitor response rate, interview status, offers
3. Download full report for follow-up

## 📱 Usage Guide by Tab

### 🔍 Search Tab

1. **Configure search parameters**:
   - Enter target roles (one per line): "Product Manager", "PM", "Senior PM"
   - Enter locations: "India", "Remote", "Bangalore"
   - Set minimum experience and salary
   - Check "Remote OK" if flexible

2. **Select platforms** (multi-select):
   - Choose 3-5 platforms for balanced speed/coverage
   - Suggested: `naukri`, `greenhouse`, `lever`, `indeed_india`
   - Add `linkedin` for comprehensive search (slower)

3. **Set AI threshold**:
   - 65% default: Only jobs matching 2/3 of your skills
   - 50% less selective: See more opportunities
   - 80% strict: Only highly-matching jobs

4. **Click "🚀 Start Search"**:
   - See real-time progress bar
   - Shows platform, role, location being searched
   - Scoring happens automatically
   - Results saved to database

5. **Check results**:
   - Go to **Job Feed** to see scored jobs
   - All jobs show score, matching skills, missing skills

### 📋 Job Feed Tab

1. **Browse all jobs**:
   - Sort by score, date, platform, company
   - Filter by status, salary range, skill gaps

2. **Click job card** to expand:
   - Full description
   - Skills analysis
   - Easy Apply availability
   - Recruiter contact (if found)

3. **Actions**:
   - **Add to Queue**: Mark for applying
   - **Save for Later**: Keep in feed but skip for now
   - **Skip**: Hide permanently
   - **Notes**: Add your thoughts

### 🤖 Apply Queue Tab

1. **Review next job to apply**:
   - See original resume
   - See tailored resume (auto-customized for this job)
   - Highlight what changed

2. **Before applying**:
   - Verify tailored resume looks good
   - Check company and role one more time

3. **Apply**:
   - **Easy Apply**: One-click submit (LinkedIn, Instahyre, etc)
   - **Manual**: Opens job link, shows recruiter email/LinkedIn
   - Marked as "applied" in tracker automatically

### 4️⃣ Manual Queue Tab

Jobs requiring manual application:
- Apply link opens in new tab
- Recruiter contact info provided
- Add personal notes before applying
- Mark as "applied" when done

### 📊 Tracker Tab

1. **View all applications**:
   - Filter by status: New, Applied, Interviewing, Offered
   - Download Excel report
   - Track response times

2. **Update status**:
   - Click job to edit status
   - Add interview dates, recruiter notes
   - Track offer details

3. **Metrics**:
   - Applications sent
   - Response rate
   - Interview conversion
   - Avg time to response

## 💼 Supported Job Portals

All scrapers are implemented and work in parallel:

| Portal | Type | Speed | Auth | Best For |
|--------|------|-------|------|----------|
| **LinkedIn** | Browser (Playwright) | Slow (2-3 min) | ✅ Email/Password | Tech, all roles, Easy Apply |
| **Naukri** | API | Fast (<10s) | ❌ Public API | India, all sectors |
| **Greenhouse** | API | Fast (<5s) | ❌ Public API | Tech companies, startups |
| **Lever** | API | Fast (<5s) | ❌ Public API | Tech companies, startups |
| **Indeed** | HTML Scraper | Medium (30s) | ❌ Public search | Large job board, global |
| **Remotive** | API | Fast (<5s) | ❌ Public API | Remote-only jobs, global |
| **WeWorkRemotely** | RSS | Fast (<5s) | ❌ RSS feed | Remote-only jobs, global |
| **Wellfound** | API | Fast (<5s) | ❌ Public API | Startup jobs, equity focus |
| **Instahyre** | API | Fast (<5s) | ❌ Public API | Indian startups, tech |
| **Hacker News** | HTML | Fast (<10s) | ❌ Public | Who is Hiring threads |
| **Hirist** | Browser/HTML | Medium (30s) | ❌ Public | India tech jobs |
| **ArbeitNow** | API | Fast (<5s) | ❌ Public | Europe jobs |

### Setup by Portal

**LinkedIn** (requires setup):
```bash
# Add to .env
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=your_password
```
- Slowest but most comprehensive
- Detects Easy Apply availability
- LinkedIn network matches (premium feature)
- Against ToS, use responsibly

**Naukri** (no setup needed):
- India's largest job board
- 50+ Indian companies
- Filters by experience, salary automatically
- Free to use

**Greenhouse & Lever** (no setup needed):
- APIs for 10+ tech companies each (Anthropic, OpenAI, Stripe, Notion, Linear, etc)
- Comprehensive job descriptions
- No rate limiting
- Startup/tech focused

**Remotive & WeWorkRemotely** (no setup needed):
- 100% remote jobs
- Global opportunities
- No salary data but flexible
- RSS + API feeds

**Indeed** (no setup needed):
- Largest job board globally
- Requires BeautifulSoup4 for HTML parsing
- Slower (~30s per search)
- All sectors covered

**Wellfound & Instahyre** (no setup needed):
- Startup job focus
- Wellfound: Global, equity-aware
- Instahyre: India-focused, tech/startups
- Both have Easy Apply options

## 🗂️ Project Structure

```
job_hunt_tool/
├── app.py                 # Main Streamlit app
├── config.yaml            # Search configuration
├── requirements.txt       # Python dependencies
├── .env.template          # Environment variables template
│
├── core/
│   ├── scraper/           # Job scrapers (LinkedIn, Naukri, etc)
│   ├── ai/                # Scoring, resume tailoring, ATS check
│   ├── apply/             # Application automation
│   ├── resume/            # Resume parsing and modification
│   └── tracker/           # Database and Excel tracking
│
├── pages/
│   ├── 1_Search.py        # Configure search parameters
│   ├── 2_Job_Feed.py      # Browse and score jobs
│   ├── 3_Apply_Queue.py   # Review and apply
│   ├── 4_Manual_Queue.py  # Manual applications + contacts
│   └── 5_Tracker.py       # Track applications
│
├── resume/
│   └── my_resume.docx     # Your master resume
│
└── data/
    ├── jobs.db            # SQLite cache
    └── jobs_tracker.csv  # CSV tracker
```

## 🔧 Configuration Reference

### config.yaml Examples

**Example 1: India-focused, fast search**
```yaml
search:
  roles:
    - "Product Manager"
    - "Senior PM"
  locations:
    - "India"
    - "Bangalore"
  experience_years: 3
  salary_min_inr: 1500000
  remote_ok: true

portals:
  - naukri        # India specialist
  - greenhouse
  - lever
  - instahyre     # Indian startups
```

**Example 2: Remote-only, global search**
```yaml
search:
  roles:
    - "Data Scientist"
    - "ML Engineer"
  locations:
    - "Remote"
  experience_years: 5
  salary_min_inr: 2000000
  remote_ok: true

portals:
  - remotive
  - weworkremotely
  - wellfound
  - indeed_india
```

**Example 3: Comprehensive search (slower but thorough)**
```yaml
search:
  roles:
    - "PM"
  locations:
    - "India"
    - "Remote"
  experience_years: 3
  salary_min_inr: 1500000
  remote_ok: true

portals:
  - linkedin      # Comprehensive but slow
  - naukri
  - greenhouse
  - lever
  - indeed_india
  - instahyre
  - remotive
```

**Example 4: Startups only**
```yaml
search:
  roles:
    - "Product Manager"
  locations:
    - "India"
  experience_years: 2
  salary_min_inr: 1000000
  remote_ok: true

portals:
  - wellfound
  - instahyre
  - remotive
  - greenhouse
```

### config.yaml Full Schema

```yaml
search:
  roles: []              # List of job titles to search
  locations: []          # List of cities/regions
  experience_years: 0    # Minimum years (filter in scraper)
  salary_min_inr: 0      # Minimum salary in INR
  remote_ok: true        # Include remote jobs

portals: []              # Which job boards to scrape
                         # Valid: linkedin, naukri, greenhouse, lever,
                         #        remotive, weworkremotely, wellfound,
                         #        instahyre, indeed_india

ai:
  score_threshold: 65    # Min match % (0-100)

apply:
  auto_apply_platforms:  # Auto-submit Easy Apply jobs
    - linkedin
    - instahyre

last_search: ""          # Auto-set after search
jobs_found: 0            # Auto-set after search
jobs_scored: 0           # Auto-set after search
```

### .env Configuration

```bash
# Required
GROQ_API_KEY_1=\u003cyour_key_1\u003e
GROQ_API_KEY_2=\u003cyour_key_2\u003e
GROQ_API_KEY_3=\u003cyour_key_3\u003e


# Optional - LinkedIn scraper
LINKEDIN_EMAIL=<your_email@company.com>
LINKEDIN_PASSWORD=<your_password>

# Optional - Other credentials (future use)
INDEED_EMAIL=<optional>
INDEED_PASSWORD=<optional>
```

Get Groq API key:
1. Visit https://console.groq.com
2. Create API key(s)
3. Copy to .env as `GROQ_API_KEY_1`, etc.

**LinkedIn credentials**:
- Use your real account credentials
- 2FA must be disabled or use app password
- Respect LinkedIn ToS (personal job hunting is OK)

## 📊 Tracking

All applications are tracked in `data/jobs_tracker.csv` with:
- Job details (title, company, location, salary)
- AI match score and skill gaps
- Application status and dates
- Recruiter contacts
- Your notes

You can:
- Filter by status, platform, score
- Sort by date, score, or company
- Download as Excel or CSV
- Update statuses as you get responses

## 🤖 AI Stack

| Task | LLM | Why |
|------|-----|-----|
| Job scoring | Groq Llama 3 | Fast, free tier (rotation support) |
| Resume tailoring | Groq Llama 3 | Best instruction following |
| Fallback | Ollama gemma4 | When rate-limited |

**Groq Limits**: Depends on key tier; rotation handled automatically.

## 🔐 Privacy & Ethics

- Uses your real LinkedIn account (no fake profiles)
- Respects robots.txt and API terms of service
- Adds random delays between requests
- Only applies to jobs you're genuinely interested in
- Never fabricates experience or skills in tailored resumes

## 🐛 Troubleshooting

### Search stuck or slow
**Problem**: Search running for >5 minutes
- LinkedIn can take 2-3 min per role, disable if slow
- Check internet speed
- Disable slow portals in config.yaml

**Solution**:
```yaml
portals:
  - naukri       # Fast APIs only
  - greenhouse
  - lever
  - indeed_india
```

### "No jobs found"
**Check**:
1. Verify roles/locations in config.yaml match job market
2. Lower score threshold temporarily (test with 40%)
3. Try individual portals first

**Debug**: Run with just one portal:
```yaml
portals:
  - greenhouse
```

### LinkedIn login fails
**Problem**: "LinkedIn login failed" error
- Email/password incorrect
- 2FA enabled — temporarily disable or use app password
- LinkedIn blocking Playwright — retry or use other portals

**Solution**:
```bash
# Test credentials
echo "LINKEDIN_EMAIL=your@email.com"
echo "LINKEDIN_PASSWORD=your_password"
# Remove from config if not working
```

### Playwright not installed
**Error**: "Playwright not installed"
```bash
pip install playwright
playwright install chromium
```

### BeautifulSoup4 error with Indeed
**Error**: "BeautifulSoup not installed"
```bash
pip install beautifulsoup4
```

### Groq API rate limited
**Error**: "429 Rate limited"
- Groq free tier has RPM limits. The tool automatically rotates between multiple keys in `.env`.
- Wait 60 seconds or upgrade to paid
- Or disable scoring temporarily

### Resume not parsing
**Solutions**:
- Use DOCX format (best compatibility)
- If PDF: try converting to DOCX
- If TXT: ensure UTF-8 encoding
- Check file size <50MB

### Streamlit not starting
```bash
# Reinstall dependencies
pip install --upgrade streamlit

# Or run with specific host/port
streamlit run app.py --server.port 8501 --server.headless true
```

### Jobs database corrupted
```bash
# Delete and rebuild
rm data/jobs.db

# Restart app
streamlit run app.py
```

## ❓ Common Questions

**Q: How long does a full search take?**
- Fast (API only): 30-60 seconds for 50-100 jobs
- With Indeed: 2-3 minutes
- With LinkedIn: 5-10 minutes
- Total time depends on platforms + job market

**Q: Can I search the same criteria daily?**
- Yes! Set up a recurring search in Search tab
- Jobs marked as duplicates automatically
- Useful for tracking new postings

**Q: What if a job site blocks me?**
- Most won't since we use APIs/public feeds
- LinkedIn might if 10+ searches/day
- Switch to other platforms or slow down

**Q: Can I tailor my resume differently for each company?**
- Yes! Tailor button in Apply Queue shows differences
- Verify before submitting
- Tool never changes core content, only keywords

**Q: How accurate is the AI scoring?**
- Generally good for skill matching (70-80% accurate)
- Check job description yourself for fit
- Use score as filter, not absolute decision

**Q: What happens if Groq API runs out?**
- Scoring rotates to the next key.
- If all keys are limited, retry after 30 seconds.

**Q: Can I use this with a team?**
- CSV tracker can be shared
- Each person needs their own Groq API key(s)
- LinkedIn logins are per-person (one account per instance)

## 🚀 Advanced Usage

### Batch Search with Different Criteria

Create multiple `config.yaml` files:

```bash
cp config.yaml config_pm.yaml     # PM roles
cp config.yaml config_analytics.yaml  # Analytics roles

# Edit each with different roles/locations
```

Run manually or script with:
```bash
streamlit run app.py --config config_pm.yaml
```

### Custom Resume Upload

In Apply Queue tab, upload different resume versions:
- `resume_tech.pdf` for technical roles
- `resume_pm.pdf` for product roles
- Auto-uses correct version based on keywords

### Skip Platform for Current Search

Override config.yaml temporarily in Search tab:
- Uncheck platforms to skip in multiselect
- Configuration is saved for next time

### Export Job Data

```bash
# Excel automatically exported to data/jobs_tracker.csv

# Or query database directly:
import sqlite3
conn = sqlite3.connect('data/jobs.db')
df = pd.read_sql('SELECT * FROM jobs WHERE score > 70', conn)
df.to_csv('high_scoring_jobs.csv')
```

### Debug Mode

Add to app.py for more logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Run with:
```bash
streamlit run app.py --logger.level=debug
```

## 📚 Documentation & Resources

**Tool Documentation**:
- [Groq API Docs](https://console.groq.com/docs/quickstart) - Job scoring model
- [Playwright Docs](https://playwright.dev/python/) - LinkedIn scraping
- [Streamlit Docs](https://docs.streamlit.io/) - Dashboard UI
- [BeautifulSoup Docs](https://www.crummy.com/software/BeautifulSoup/bs4/doc/) - Indeed scraping

**Job Portal Documentation**:
- [LinkedIn Jobs](https://www.linkedin.com/jobs/)
- [Naukri.com](https://www.naukri.com/)
- [Greenhouse Job Boards](https://boards-api.greenhouse.io/v1/boards/)
- [Lever.co Jobs](https://www.lever.co/)
- [Remotive API](https://remotive.com/api/)
- [Wellfound Jobs](https://www.wellfound.com/jobs)
- [Instahyre Jobs](https://www.instahyre.com/)
- [Indeed India](https://www.indeed.co.in/)
- [WeWorkRemotely](https://weworkremotely.com/)

**Learning Resources**:
- [Python Requests](https://requests.readthedocs.io/) - HTTP library
- [Asyncio Guide](https://docs.python.org/3/library/asyncio.html) - Async programming
- [Pandas](https://pandas.pydata.org/) - Data analysis (for custom scoring)

## 🤝 Contributing

Found a bug or have an idea?

**Common improvements**:
- Add more job portals (Dice, GitHub Jobs, AngelList, etc)
- Improve resume parsing (extract sections, skills)
- Add filters (company size, industry, funding stage)
- Custom scorer logic based on your preferences
- Automatic follow-up reminders

## 🔐 Privacy & Ethics

- Uses your real LinkedIn account (no fake profiles)
- Respects robots.txt and API terms of service
- Adds random delays between requests
- Only applies to jobs you're genuinely interested in
- Never fabricates experience or skills in tailored resumes

## 📝 License

MIT License - Use freely for personal job hunting and personal development

## 🚀 Next Steps

1. ✅ Install dependencies and configure `.env`
2. ✅ Place resume in `resume/` folder
3. ✅ Edit `config.yaml` with your target roles/locations
4. ✅ Run `streamlit run app.py`
5. ✅ Go to 🔍 Search tab and click "🚀 Start Search"
6. ✅ Review results in 📋 Job Feed
7. ✅ Apply via 🤖 Apply Queue
8. ✅ Track progress in 📊 Tracker

---

**Good luck with your job hunt! 🎯**

*Built with Python, Streamlit, Playwright, Groq Llama 3, and ❤️*
