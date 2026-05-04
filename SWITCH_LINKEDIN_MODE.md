# Quick Switch: LinkedIn Automation Mode

Three ways to run LinkedIn scraping + Easy Apply automation.

## 1. Headless Playwright (Default - Fastest)

Hidden browser automation. No visibility.

**Currently active.** No changes needed.

```python
# Uses: core/scraper/linkedin.py (LinkedInScraper)
# Uses: core/apply/linkedin_apply.py (LinkedInAutoApply)
```

## 2. Visible Playwright (Recommended for Debugging)

Playwright but with visible browser window. See automation happening.

### Switch to Visible Playwright:

**Edit `core/scraper/__init__.py`:**

```python
# At bottom of file, uncomment:
LinkedInScraper = LinkedInScraperHybrid  # Playwright with visible browser
```

**Edit `core/apply/apply_router.py`:**

```python
# At imports, change:
from .linkedin_apply import LinkedInAutoApply

# To:
from .linkedin_apply_devtools import LinkedInAutoApplyHybrid as LinkedInAutoApply
```

**That's it!** Rest of code unchanged. Same interface.

## 3. Chrome DevTools MCP (Full Integration)

Real-time Chrome DevTools control. Most transparent, debuggable.

**Requires**: Claude Code with chrome-devtools-mcp plugin.

### Switch to Chrome DevTools MCP:

**Edit `core/scraper/__init__.py`:**

```python
# At bottom, change:
LinkedInScraper = LinkedInScraperHybrid

# To:
LinkedInScraper = LinkedInScraperDevTools  # Full Chrome DevTools
```

**Edit `core/apply/apply_router.py`:**

```python
# Change:
from .linkedin_apply_devtools import LinkedInAutoApplyHybrid as LinkedInAutoApply

# To:
from .linkedin_apply_devtools import LinkedInAutoApplyDevTools as LinkedInAutoApply
```

## Comparison

| Feature | Headless | Visible Playwright | Chrome DevTools |
|---------|----------|-------------------|-----------------|
| Speed | ⚡⚡⚡ Fast | ⚡⚡ Medium | ⚡ Slower |
| Debugging | 🔴 Hard | 🟡 Easy | 🟢 Very Easy |
| Visibility | ❌ Hidden | ✅ Browser window | ✅ Real-time |
| Browser process | Separate | Visible window | Integrated |
| Best for | Production | Development | Development |

## Current Status

- **Mode**: Headless Playwright
- **LinkedIn scraper**: `core/scraper/linkedin.py`
- **Easy Apply**: `core/apply/linkedin_apply.py`
- **Test account**: Configured in `.env`

## To Switch:

1. **One of the edits above** (2-3 lines changed)
2. **Restart Streamlit app**: `streamlit run app.py`
3. **Run search** and watch browser automation

## Troubleshooting

### Page not loading in visible Playwright:

```
LinkedIn login page hangs or doesn't load.
→ Check .env LINKEDIN_EMAIL and LINKEDIN_PASSWORD
→ Check if LinkedIn requires CAPTCHA
→ Increase timeout in linkedin_devtools.py
```

### Chrome DevTools not found:

```
ModuleNotFoundError: No module named 'claude_code_mcp'
→ Claude Code chrome-devtools-mcp plugin not installed
→ Stay with Visible Playwright for now
→ Check plugin availability: claude --list-plugins
```

### Easy Apply form not filling:

```
Form fields not auto-filling
→ LinkedIn usually pre-fills from profile
→ May need manual confirmation for some fields
→ Check browser console for errors
```

## Examples

### Debugging LinkedIn Selector Change

If LinkedIn changes HTML structure:

**Visible Playwright**: You see the page and can inspect elements in browser DevTools

**Chrome DevTools**: Snapshot shows current UIDs and structure—easier to fix code

```python
# When selector breaks:
# 1. Run search with visible mode
# 2. Inspect page in browser DevTools
# 3. Find new selector
# 4. Update code and retry
```

## Files Involved

| File | Purpose | Modes |
|------|---------|-------|
| `core/scraper/linkedin.py` | Headless scraper | Headless only |
| `core/scraper/linkedin_devtools.py` | Alternative scrapers | Visible, DevTools |
| `core/apply/linkedin_apply.py` | Headless Easy Apply | Headless only |
| `core/apply/linkedin_apply_devtools.py` | Alternative appliers | Visible, DevTools |
| `core/scraper/__init__.py` | Selector | Switch here |
| `core/apply/apply_router.py` | Selector | Optional, switch if needed |

## Next Steps

1. **Try Visible Playwright**: Edit one file, restart, run search
2. **If LinkedIn breaks**: Easy to debug with visible window
3. **When Chrome DevTools ready**: Switch to full integration

---

**See `CHROME_DEVTOOLS_INTEGRATION.md` for detailed implementation guide.**
