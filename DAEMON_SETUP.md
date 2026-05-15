# Claude Subprocess Scoring Daemon Setup

Automated job scoring via Claude subprocess, running nightly at 1 AM IST.

## Architecture

- **`core/scorer/claude_subprocess_scorer.py`**: Scores job batches via `claude -p` CLI
  - Uses Sonnet 4.6 (configurable)
  - Detects session limit: parses "Claude AI usage limit reached, please try again after X:XXpm"
  - Returns results + retry time if limit hit

- **`core/scheduler/scoring_daemon.py`**: Cron-callable daemon
  - Loads resume (default: EU context)
  - Fetches unscored jobs from tracker
  - Batches & scores via Claude subprocess
  - Saves to DB + CSV after each batch
  - Exits gracefully on session limit

## Configuration

Add to `.env`:

```bash
# Batch size (jobs per Claude call)
CLAUDE_BATCH_SIZE=25

# Claude model (must be accessible via `claude -p --model <name>`)
CLAUDE_MODEL=claude-sonnet-4-6
```

Resume must exist at one of:
- `data/resumes/EU.docx`
- `data/resumes/EU.pdf`
- `data/resumes/EU.txt`

## Setup Cron Job

### Option 1: Automated Setup Script

```bash
bash setup_cron.sh
```

This adds a cron entry:
```
0 1 * * * cd /path/to/project && TZ=Asia/Kolkata python3 core/scheduler/scoring_daemon.py --context EU >> logs/scoring_daemon.log 2>&1
```

### Option 2: Manual Crontab

```bash
crontab -e
```

Add:
```
0 1 * * * cd /Users/tarungupta/Making\ It\ Big/Claude/AI\ Job\ Engine/job_hunt_tool && TZ=Asia/Kolkata python3 core/scheduler/scoring_daemon.py --context EU >> logs/scoring_daemon.log 2>&1
```

(Replace path with actual project directory)

## Verify Setup

Check cron is registered:
```bash
crontab -l | grep scoring_daemon
```

Monitor logs:
```bash
tail -f logs/scoring_daemon.log
```

## Manual Test

Run daemon immediately:
```bash
python3 core/scheduler/scoring_daemon.py --context EU
```

With custom batch size:
```bash
python3 core/scheduler/scoring_daemon.py --context EU --batch-size 10
```

## Behavior

### Scoring Flow

1. Load resume (20k+ chars = ~5k tokens)
2. Fetch unscored jobs from CSV tracker
3. Batch: 25 jobs per call (adjustable via `CLAUDE_BATCH_SIZE`)
   - Per batch: resume (5k) + jobs (25 × 1.5k) + response = ~47k tokens
4. Call `claude -p` with Sonnet 4.6
5. Parse JSON results
6. Save to DB + CSV
7. Repeat until all unscored jobs processed or session limit hit

### Session Limit Handling

If Claude returns "usage limit reached", daemon:
1. Captures retry time from error message
2. Logs it: `SESSION LIMIT REACHED — retry after X:XXpm`
3. Exits gracefully (cron will retry at next scheduled time)
4. Already-scored jobs are saved to DB/CSV

### Logs

All output goes to `logs/scoring_daemon.log`:
- Batch progress
- Save counts
- Errors (JSON parse, subprocess failure)
- Session limit events

Example:
```
[2026-05-15 01:05:23] ═══ SCORING DAEMON START (context=EU) ═══
[2026-05-15 01:05:24] Total jobs in tracker: 150
[2026-05-15 01:05:24] Unscored jobs: 45
[2026-05-15 01:05:24] ─ Batch 1: 25 jobs ─
[2026-05-15 01:05:35] ✅ Claude subprocess done in 11.2s — 2843 chars
[2026-05-15 01:05:35] Claude parsed 25 scored results
[2026-05-15 01:05:36] Batch 1 saved: 25/25 jobs
[2026-05-15 01:05:38] ─ Batch 2: 20 jobs ─
[2026-05-15 01:05:45] ✅ Claude subprocess done in 7.3s — 1956 chars
[2026-05-15 01:05:45] Claude parsed 20 scored results
[2026-05-15 01:05:46] Batch 2 saved: 20/20 jobs
[2026-05-15 01:05:48] ═══ DAEMON COMPLETE: 45 jobs scored in 2 batches ═══
```

## Troubleshooting

### "Claude CLI unavailable"
- Ensure `claude` is in PATH: `which claude`
- Install Claude Code: https://github.com/anthropics/claude-code
- Test: `claude --version`

### "Resume not found"
- Check resume exists: `ls data/resumes/EU.*`
- Must be `.docx`, `.pdf`, or `.txt`
- Check format supported in `core/resume/parser.py`

### "No jobs scored"
- Check unscored jobs exist: `logs/scoring_daemon.log`
- Verify Job ID format matches between CSV and JSON
- Manually test scorer: see Manual Test section

### Cron not running
- Check cron daemon: `sudo launchctl list | grep cron` (macOS) or `systemctl status cron` (Linux)
- Verify TZ=Asia/Kolkata is set correctly
- Check log file is writable: `touch logs/scoring_daemon.log`

## Resume Contexts

The daemon supports multiple resume versions:
```bash
python3 core/scheduler/scoring_daemon.py --context IN
python3 core/scheduler/scoring_daemon.py --context remote_contractual
```

Requires corresponding resume files: `data/resumes/{context}.*`

## Token Budget

- Sonnet 4.6 context: 200k tokens
- Per batch (~25 jobs): ~47k tokens
- Sessions/day: Up to 4 full batches before limit
- If needed, reduce `CLAUDE_BATCH_SIZE` to 15-20 jobs for longer sessions
