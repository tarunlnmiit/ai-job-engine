# Job Scraper Technical Details

Reference for understanding how each scraper works.

## Overview

All scrapers inherit from `BaseJobScraper` and implement the `search()` method:

```python
class BaseJobScraper:
    def search(self, role: str, location: str, **kwargs) -> list[Job]:
        """Return list of Job objects"""
        raise NotImplementedError
```

## Scrapers by Type

### Public API Scrapers (Fast, Reliable)

#### Greenhouse
- **Type**: Public API (no auth required)
- **Endpoint**: `https://boards-api.greenhouse.io/v1/boards/{company}/jobs`
- **Companies**: 14 pre-configured (Anthropic, OpenAI, Stripe, Figma, Linear, etc)
- **Speed**: <5 seconds
- **Rate limit**: None documented
- **Features**: Full job description, no salary data
- **File**: `core/scraper/greenhouse.py`

#### Lever
- **Type**: Public API (no auth required)
- **Endpoint**: `https://api.lever.co/v0/postings/{company}`
- **Companies**: 10 pre-configured (Anthropic, OpenAI, Stripe, Figma, Linear, etc)
- **Speed**: <5 seconds
- **Rate limit**: None documented
- **Features**: Full job description, company details
- **File**: `core/scraper/lever.py`

#### Naukri
- **Type**: Semi-public API (no auth required but has headers)
- **Endpoint**: `https://www.naukri.com/jobapi/v3/search`
- **Params**: keyword, location, experience, salary filters
- **Speed**: <10 seconds
- **Rate limit**: Unknown
- **Features**: India-specific, salary data, experience level
- **File**: `core/scraper/naukri.py`

#### Remotive
- **Type**: Public API
- **Endpoint**: `https://remotive.com/api/remote-jobs`
- **Params**: search (job title)
- **Speed**: <5 seconds
- **Rate limit**: None documented
- **Features**: Remote-only, global, company info
- **File**: `core/scraper/remotive.py`

#### Wellfound
- **Type**: Public API
- **Endpoint**: `https://api.wellfound.com/v1/jobs`
- **Params**: query (role), location, limit
- **Speed**: <5 seconds
- **Rate limit**: None documented
- **Features**: Startup jobs, equity focus, Easy Apply flag
- **File**: `core/scraper/wellfound.py`

#### Instahyre
- **Type**: Public API
- **Endpoint**: `https://api.instahyre.com/api/v2/public_jobs/`
- **Params**: search (role), page, limit
- **Speed**: <5 seconds
- **Rate limit**: None documented
- **Features**: Indian startups, Easy Apply, skills tagging
- **File**: `core/scraper/instahyre.py`

### Feed-based Scrapers (Fast, Parsing Required)

#### WeWorkRemotely
- **Type**: RSS Feed Parser
- **Endpoint**: `https://weworkremotely.com/categories/remote-full-time-jobs.rss`
- **Speed**: <5 seconds
- **Parser**: XML ElementTree
- **Features**: Remote-only, company extracted from title format
- **Limitation**: No salary data, limited metadata
- **File**: `core/scraper/weworkremotely.py`

### HTML Scrapers (Medium Speed, Complex Parsing)

#### Indeed
- **Type**: HTML scraper with BeautifulSoup
- **Endpoint**: `https://in.indeed.com/jobs?q={role}&l={location}`
- **Speed**: 20-40 seconds (per location/role combo)
- **Parser**: BeautifulSoup4
- **Dependencies**: `beautifulsoup4` required
- **Selectors**:
  - Job cards: `div[data-tn-component="organicJob"]`
  - Title: `a[data-qa="job-item-title"]`
  - Company: `span[data-qa="companyName"]`
  - Location: `div[data-qa="job-item-location"]`
- **Limitations**: Selectors fragile (Indeed changes HTML frequently)
- **Features**: Large job board, all sectors, salary negotiable
- **File**: `core/scraper/indeed.py`

### Browser Automation Scrapers (Slow, Comprehensive)

#### LinkedIn
- **Type**: Playwright browser automation
- **Endpoint**: `https://www.linkedin.com/jobs/search/`
- **Speed**: 2-5 minutes (per role/location combo)
- **Browser**: Chromium (headless)
- **Auth**: Email/password required
- **Dependencies**: `playwright` required, chromium binary
- **Flow**:
  1. Launch browser
  2. Navigate to login page
  3. Fill email/password
  4. Click login, wait for redirect
  5. Navigate to jobs search with filters
  6. Parse job cards
  7. Click each job to get full description
  8. Check for Easy Apply button
- **Features**:
  - Easy Apply detection
  - Full job description
  - Recruiter info (premium feature)
  - Network matches
- **Rate limiting**: LinkedIn may block if >10 searches/day
- **Limitations**:
  - Violates LinkedIn ToS
  - Slow compared to APIs
  - Requires real account (no bots allowed)
  - Fragile to LinkedIn HTML changes
- **File**: `core/scraper/linkedin.py`

## Job Object Structure

All scrapers return `Job` objects with this structure:

```python
@dataclass
class Job:
    id: str                          # Unique ID (platform_jobid)
    title: str                       # Job title
    company: str                     # Company name
    location: str                    # Location (city or Remote)
    description: str                 # Full job description
    application_url: str             # Link to apply
    platform: str                    # Platform name (linkedin, naukri, etc)
    salary: Optional[str]            # Salary range if available
    skills_required: list[str]       # Required skills
    is_remote: bool                  # True if remote
    is_easy_apply: bool              # One-click apply available
    posted_date: Optional[datetime]  # When posted
    experience_required: Optional[str] # Experience text
    date_found: Optional[str]        # When we found it
    score: Optional[float]           # AI score (0-100) — set by scorer
    status: str                      # new/applied/interview/offer
    matching_skills: list[str]       # Skills that match resume
    missing_skills: list[str]        # Skills you're missing
    notes: Optional[str]             # Your notes
```

## Database Schema

Jobs are stored in SQLite at `data/jobs.db`:

```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    title TEXT,
    company TEXT,
    location TEXT,
    salary TEXT,
    description TEXT,
    skills_required TEXT,          -- JSON serialized
    platform TEXT,
    application_url TEXT,
    is_remote BOOLEAN,
    is_easy_apply BOOLEAN,
    score REAL,                    -- 0-100 from AI scorer
    status TEXT,                   -- new/applied/interview/offer
    date_found TEXT,               -- ISO format date
    date_applied TEXT,
    matching_skills TEXT,          -- JSON serialized
    missing_skills TEXT,           -- JSON serialized
    notes TEXT,
    contact_info TEXT,             -- Recruiter email
    linkedin_network_match TEXT
)
```

## Implementing a New Scraper

1. Create new file in `core/scraper/`:

```python
import httpx
from datetime import datetime
from .base import BaseJobScraper, Job

class MyJobScraper(BaseJobScraper):
    """Scrape jobs from MyJobBoard."""
    
    def search(self, role: str, location: str = None, **kwargs) -> list[Job]:
        """Search for jobs."""
        jobs = []
        
        try:
            # Make API call or scrape HTML
            response = httpx.get(...)
            data = response.json()  # or parse HTML
            
            # Parse response
            for item in data:
                job = Job(
                    id=f"myboard_{item['id']}",
                    title=item['title'],
                    company=item['company'],
                    location=item.get('location', 'Remote'),
                    description=item.get('description', ''),
                    application_url=item['url'],
                    platform='myboard',
                    is_remote='remote' in item.get('location', '').lower(),
                    date_found=datetime.now().strftime("%Y-%m-%d"),
                )
                jobs.append(job)
        
        except Exception as e:
            print(f"Error scraping MyJobBoard: {e}")
        
        return jobs
```

2. Add import to `core/scraper/__init__.py`

3. Add to scraper_map in `pages/1_Search.py`

4. Add to config.yaml portals list

5. Test:
```python
scraper = MyJobScraper()
jobs = scraper.search("Product Manager", "India")
```

## Performance Tuning

### API Scrapers (fastest)
- Run all in parallel
- Total time: max(individual times) ≈ 5-10 seconds
- Can handle many roles/locations with minimal overhead

### HTML Scrapers (medium)
- BeautifulSoup parsing adds overhead
- Indeed: 20-40 seconds per location/role
- Total: 10s base + 30s per combo = slower

### Browser Scrapers (slowest)
- LinkedIn: 2-3 minutes per role/location
- Browser startup: 2-3 seconds
- Page loads: 3-5 seconds each
- DOM parsing: 1-2 seconds
- Sequential only (can't parallelize browsers)

### Optimization Tips
- Use API scrapers preferentially
- Batch related searches (same location, different roles)
- Disable slow scrapers for quick iterations
- Cache results (don't re-scrape same query same day)

## Debugging Tips

### Check scraper output
```python
from core.scraper import LinkedInScraper
scraper = LinkedInScraper(email="test@gmail.com", password="pwd")
jobs = scraper.search("PM", "India")
print(f"Found {len(jobs)} jobs")
for j in jobs[:3]:
    print(f"{j.title} at {j.company}")
```

### Monitor HTTP requests
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# httpx will now log all requests
```

### Check database
```python
from core.tracker.db import JobCache
db = JobCache()
all_jobs = db.get_all_jobs()
print(f"Total jobs in DB: {len(all_jobs)}")
```

## Common Issues

**API returns 404**
- Company/endpoint may have changed
- Check URL format
- Add auth headers if needed

**HTML selectors don't work**
- Website redesigned
- Selectors change frequently
- Monitor with web inspector
- Update selectors when broken

**Rate limiting**
- Most APIs have limits
- Add exponential backoff
- Use caching
- Slow down requests

**LinkedIn keeps blocking**
- Use real account
- Don't search >10 times/day
- Add random delays
- Disable if not needed

---

Each scraper's code is well-commented with platform-specific notes. Check `core/scraper/*.py` for implementation details!
