# Chrome DevTools MCP Integration Guide

Replace Playwright-based LinkedIn automation with Chrome DevTools MCP for visible, debuggable browser automation.

## Architecture

### Current (Playwright)
- **Headless browser** - fast but hidden automation
- **Scraping**: `core/scraper/linkedin.py`
- **Easy Apply**: `core/apply/linkedin_apply.py`

### New (Chrome DevTools MCP)
- **Visible browser** - see automation happening in real-time
- **Scraping**: `core/scraper/linkedin_devtools.py` → `LinkedInScraperDevTools`
- **Easy Apply**: `core/apply/linkedin_apply_devtools.py` → `LinkedInAutoApplyDevTools`
- **Hybrid approach**: `LinkedInScraperHybrid`, `LinkedInAutoApplyHybrid` (Playwright + screenshots)

## Setup Requirements

### 1. Claude Code with Chrome DevTools MCP

Ensure Claude Code has chrome-devtools-mcp plugin:

```bash
# Check if plugin is available
claude --list-plugins | grep chrome-devtools
```

### 2. Start Chrome Browser Session

Chrome DevTools MCP requires an active Chrome instance:

```bash
# Claude Code opens Chrome automatically via MCP
# Or manually: open Chrome, configure for remote debugging
```

## Implementation Approach

### Option A: Full Chrome DevTools MCP (Recommended)

**File**: `core/scraper/linkedin_devtools.py` → `LinkedInScraperDevTools`

```python
# Pseudo-code of implementation:
from claude_code_mcp import chrome_devtools

async def search(self, role, location):
    # 1. Open LinkedIn login page
    page = await chrome_devtools.new_page("https://linkedin.com/login")

    # 2. Login
    snapshot = await chrome_devtools.take_snapshot()
    email_uid = find_uid_in_snapshot("input[placeholder*='Email']")
    await chrome_devtools.fill(email_uid, self.email)

    # 3. Navigate to jobs search
    jobs_url = f"https://linkedin.com/jobs/search/?keywords={role}&location={location}"
    await chrome_devtools.navigate_page(jobs_url)

    # 4. Extract jobs from DOM
    snapshot = await chrome_devtools.take_snapshot()
    jobs = parse_job_cards_from_snapshot(snapshot)

    # 5. Click each job for full description
    for job_card_uid in job_card_uids:
        await chrome_devtools.click(job_card_uid)
        snapshot = await chrome_devtools.take_snapshot()
        description = extract_description(snapshot)

    return jobs
```

**Pros**:
- Real-time visibility of automation
- Easy debugging when LinkedIn changes selectors
- Single source of truth (Chrome window)
- No hidden processes

**Cons**:
- Slower than headless Playwright
- Requires Chrome to stay open
- More API calls to MCP

### Option B: Hybrid (Playwright + Chrome DevTools Logging)

**Files**: `LinkedInScraperHybrid`, `LinkedInAutoApplyHybrid`

Uses Playwright for speed but captures Chrome DevTools snapshots for visibility:

```python
# Playwright automation in headless=False mode
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)  # Visible
    page = await browser.new_page()
    # ... automation continues ...
```

**Pros**:
- Speed of Playwright
- Browser window visible for debugging
- Familiar Playwright API
- Can add screenshot/snapshot logging

**Cons**:
- Not true Chrome DevTools MCP integration
- Still separate automation engine

## Migration Path

### Step 1: Switch to Hybrid Approach (Easiest)

Update `core/scraper/__init__.py`:

```python
# Change from:
from .linkedin import LinkedInScraper

# To:
from .linkedin_devtools import LinkedInScraperHybrid as LinkedInScraper
```

Update `core/apply/__init__.py`:

```python
# Change from:
from .linkedin_apply import LinkedInAutoApply

# To:
from .linkedin_apply_devtools import LinkedInAutoApplyHybrid as LinkedInAutoApply
```

**No other code changes needed.** Hybrid approach uses same interface.

### Step 2: Full Chrome DevTools MCP (Advanced)

When ready for full Chrome DevTools integration:

1. **Install chrome-devtools-mcp plugin** in Claude Code settings
2. **Implement** `LinkedInScraperDevTools.search()` with actual MCP calls
3. **Test** with manual Claude Code session
4. **Update scraper imports** to use `LinkedInScraperDevTools`

## API Reference (Chrome DevTools MCP)

Rough API shape (exact names may vary):

```python
# Page management
page = await chrome_devtools.new_page(url)
await chrome_devtools.navigate_page(url)
await chrome_devtools.close_page(page_id)

# Interaction
snapshot = await chrome_devtools.take_snapshot()  # Get page structure + UIDs
await chrome_devtools.click(uid)
await chrome_devtools.fill(uid, value)
await chrome_devtools.fill_form({uid1: value1, uid2: value2})
await chrome_devtools.wait_for(text_or_selector)

# Debugging
screenshot = await chrome_devtools.take_screenshot()
await chrome_devtools.hover(uid)
await chrome_devtools.press_key("Enter")

# Form handling
await chrome_devtools.upload_file(file_input_uid, "/path/to/resume.pdf")
```

## Switching Between Implementations

### Use Hybrid (Visible Playwright):

```python
# pages/1_Search.py or core/scraper/__init__.py
from core.scraper.linkedin_devtools import LinkedInScraperHybrid
scraper = LinkedInScraperHybrid(email, password)
```

### Use Full Chrome DevTools MCP:

```python
from core.scraper.linkedin_devtools import LinkedInScraperDevTools
scraper = LinkedInScraperDevTools(email, password)
```

### Keep Playwright Headless:

```python
from core.scraper.linkedin import LinkedInScraper  # Original
scraper = LinkedInScraper(email, password)
```

## Debugging Chrome DevTools Issues

### If snapshot parsing fails:

```python
# Save snapshot for analysis
snapshot = await chrome_devtools.take_snapshot()
with open("debug_snapshot.txt", "w") as f:
    f.write(snapshot)

# Look for UIDs manually
# Format: <uid-123>element text</uid-123>
```

### If page navigation times out:

```python
# Increase timeout
await chrome_devtools.navigate_page(url, timeout=60000)

# Or wait for specific element
await chrome_devtools.wait_for("div.base-card")
```

### If form filling doesn't work:

```python
# Debug form state
snapshot = await chrome_devtools.take_snapshot()
print(snapshot)  # Check for input UIDs

# Try tab key instead of clicking Next
await chrome_devtools.press_key("Tab")
```

## Performance Comparison

| Approach | Speed | Visibility | Debuggability | Setup |
|----------|-------|------------|----------------|-------|
| Playwright Headless | ⚡⚡⚡ Fast | ❌ None | 🔴 Hard | ✅ Easy |
| Playwright Visible | ⚡⚡ Medium | ✅ Window visible | 🟡 Medium | ✅ Easy |
| Chrome DevTools MCP | ⚡ Slower | ✅ Real-time | 🟢 Easy | 🟡 Requires MCP |

**Recommended for development**: Hybrid (visible Playwright)
**Recommended for production**: Full Chrome DevTools MCP (once stable)

## Next Steps

1. **Immediate**: Switch to `LinkedInScraperHybrid` in 1 line of code
2. **When ready**: Implement full Chrome DevTools MCP integration
3. **Testing**: Validate job scraping and Easy Apply with test LinkedIn account
4. **Monitoring**: Log Chrome DevTools API errors for improvement

---

**Status**: Template implementations ready. Awaiting Chrome DevTools MCP availability in Claude Code.
