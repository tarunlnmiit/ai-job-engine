"""Apply queue with resume tailoring, Chrome automation, and sequential queue mode."""

import threading
import time
from pathlib import Path
from datetime import date, datetime

import streamlit as st

from core.ui.style import apply_custom_style, safe_score
from core.tracker.csv_tracker import CSVTracker
from core.resume.picker import pick_resume, classify_job, RESUME_TYPES, get_all_resume_options
from core.resume.docx_generator import generate_tailored_resume
from core.apply.chrome_apply import launch_and_stage, CHROME_DEBUG_PORT
from core.apply import auto_apply
from logger import get_logger

logger = get_logger("ui.apply_queue")

st.set_page_config(page_title="Apply Queue", page_icon="🤖", layout="wide")
apply_custom_style()

st.title("🤖 Apply Queue")
st.markdown("##### *Auto-resume selection, AI tailoring, and Chrome apply — one job at a time.*")

RESUME_TYPE_LABELS = {
    "IN": "🇮🇳 India Resume",
    "EU": "🌍 EU/International Resume",
    "remote_contractual": "💼 Contractual Resume",
}

tracker = CSVTracker()
all_jobs = tracker.get_all_jobs()
logger.debug("Apply Queue loaded: %d total jobs in tracker", len(all_jobs))

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "tailored_paths" not in st.session_state:
    st.session_state.tailored_paths = {}
if "apply_results" not in st.session_state:
    st.session_state.apply_results = {}
if "queue_index" not in st.session_state:
    st.session_state.queue_index = 0
if "queue_mode" not in st.session_state:
    st.session_state.queue_mode = False
if "auto_run" not in st.session_state:
    st.session_state.auto_run = False
if "auto_run_idx" not in st.session_state:
    st.session_state.auto_run_idx = 0
if "auto_run_state" not in st.session_state:
    # "idle" | "applying" | "needs_input" | "applied" | "failed" | "manual_required"
    st.session_state.auto_run_state = "idle"
if "auto_run_result" not in st.session_state:
    st.session_state.auto_run_result = {}
if "auto_run_user_inputs" not in st.session_state:
    st.session_state.auto_run_user_inputs = {}
if "auto_run_log" not in st.session_state:
    st.session_state.auto_run_log = []
if "auto_run_thread" not in st.session_state:
    st.session_state.auto_run_thread = None
if "auto_run_thread_result" not in st.session_state:
    st.session_state.auto_run_thread_result = {}
if "auto_run_tailor_result" not in st.session_state:
    st.session_state.auto_run_tailor_result = {}


# ---------------------------------------------------------------------------
# Logging helper (Python logger + UI log panel)
# ---------------------------------------------------------------------------

def _log(level: str, msg: str, *args) -> None:
    formatted = msg % args if args else msg
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.auto_run_log.append((ts, level, formatted))
    if len(st.session_state.auto_run_log) > 200:
        st.session_state.auto_run_log = st.session_state.auto_run_log[-200:]
    getattr(logger, level.lower(), logger.info)(formatted)


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

@st.dialog("📝 Your Input Needed")
def _input_dialog(result: dict):
    """Dialog shown when automation needs user to provide a field value."""
    label = result.get("label", "Unknown field")
    field_name = result.get("field_name", "field")
    field_type = result.get("field_type", "text")
    hint = result.get("hint", "")
    page_url = result.get("page_url", "")

    st.markdown(f"**{label}**")
    if hint:
        st.caption(hint)
    if page_url:
        st.caption(f"Page: {page_url[:80]}")

    if field_type == "confirm":
        # No text input — just a continue/stop choice
        answer = "__confirmed__"
    elif field_type == "textarea":
        answer = st.text_area("Your answer", height=120, key="dialog_answer")
    else:
        answer = st.text_input("Your answer", key="dialog_answer")

    c1, c2 = st.columns(2)
    if c1.button("▶ Continue", type="primary", use_container_width=True):
        _log("info", "User provided input for '%s': %s", label, str(answer)[:40])
        # Merge into user inputs; signal resume
        new_inputs = dict(st.session_state.auto_run_user_inputs)
        new_inputs[field_name] = answer if field_type != "confirm" else "__confirmed__"
        new_inputs["__resume"] = True
        st.session_state.auto_run_user_inputs = new_inputs
        st.session_state.auto_run_state = "idle"  # re-trigger apply
        st.rerun()

    if c2.button("⏭️ Skip Job", use_container_width=True):
        _log("warning", "User skipped job after needs_input for '%s'", label)
        st.session_state.auto_run_idx += 1
        st.session_state.auto_run_state = "idle"
        st.session_state.auto_run_user_inputs = {}
        st.session_state.auto_run_result = {}
        st.rerun()


@st.dialog("⚠️ Apply Error")
def _error_dialog(result: dict):
    reason = result.get("reason", "Unknown error")
    st.error(reason)
    c1, c2 = st.columns(2)
    if c1.button("⏭️ Skip", use_container_width=True):
        _log("warning", "Skipping job after error: %s", reason)
        st.session_state.auto_run_idx += 1
        st.session_state.auto_run_state = "idle"
        st.session_state.auto_run_user_inputs = {}
        st.session_state.auto_run_result = {}
        st.rerun()
    if c2.button("⏹ Stop", use_container_width=True):
        _log("info", "Auto-run stopped after error")
        st.session_state.auto_run = False
        st.session_state.auto_run_state = "idle"
        st.rerun()


# ---------------------------------------------------------------------------
# Sidebar: filter + log
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔍 Filter")
    from core.apply.auto_apply import _is_chrome_debug_running, CHROME_DEBUG_PORT as _CDP_PORT
    if _is_chrome_debug_running():
        st.success(f"✅ Chrome on port {_CDP_PORT} — using your logged-in session")
    else:
        st.info(f"Chrome will be launched automatically on port {_CDP_PORT} when you apply")
    st.divider()
    status_filter = st.selectbox(
        "Job Status",
        options=["shortlisted", "new", "manual_required"],
        index=0,
    )
    min_score = st.slider("Min Score %", 0, 100, 0)

    if st.session_state.auto_run_log:
        st.divider()
        st.subheader("📋 Activity Log")
        if st.button("🗑 Clear Log", key="clear_log"):
            st.session_state.auto_run_log = []
            st.rerun()
        icons = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "debug": "🔍"}
        lines = [
            f"{icons.get(lvl, '•')} [{ts}] {msg}"
            for ts, lvl, msg in reversed(st.session_state.auto_run_log[-50:])
        ]
        st.code("\n".join(lines), language=None)

# ---------------------------------------------------------------------------
# Build queue
# ---------------------------------------------------------------------------
apply_queue = [
    j for j in all_jobs
    if j.get("Status") == status_filter
    and j.get("Job ID", "").strip()
    and j.get("Role", "").strip()
]

if status_filter == "new":
    apply_queue = [j for j in apply_queue if safe_score(j.get("Score (%)")) >= 75]

if min_score > 0:
    apply_queue = [j for j in apply_queue if safe_score(j.get("Score (%)")) >= min_score]

apply_queue = sorted(apply_queue, key=lambda j: safe_score(j.get("Score (%)")), reverse=True)
logger.debug(
    "Apply queue built: %d jobs (filter=%s, min_score=%d)",
    len(apply_queue), status_filter, min_score,
)

if not apply_queue:
    st.info(f"No **{status_filter}** jobs found. Go to Job Feed to shortlist jobs.")
    st.stop()

# --- Metrics ---
m1, m2, m3 = st.columns(3)
m1.metric("In Queue", len(apply_queue))
m2.metric("With Description", sum(1 for j in apply_queue if len(str(j.get("Description", ""))) > 50))
m3.metric("High Score (≥80)", sum(1 for j in apply_queue if safe_score(j.get("Score (%)")) >= 80))

st.divider()

# --- Export for Claude Co-work ---
def _build_claude_export(jobs: list[dict], tailored_paths: dict) -> str:
    from core.apply.auto_apply import PROFILE
    from core.resume.picker import pick_resume

    job_lines = []
    for i, job in enumerate(jobs, 1):
        jid = job.get("Job ID", "")
        resume_path, _ = pick_resume(job)
        tailored = tailored_paths.get(jid)
        resume_file = tailored or (str(resume_path) if resume_path else "")
        desc = str(job.get("Description", "")).strip()[:500]
        job_lines.append(
            f"### Job {i}: {job.get('Role', '?')} @ {job.get('Company', '?')}\n"
            f"- **ID**: `{jid}`\n"
            f"- **URL**: {job.get('Application URL', 'N/A')}\n"
            f"- **Score**: {safe_score(job.get('Score (%)'))}%\n"
            f"- **Platform**: {job.get('Platform', '')}\n"
            f"- **Location**: {job.get('Location', '')}\n"
            f"- **Resume**: `{resume_file}`\n"
            f"- **Description snippet**: {desc[:300]}{'…' if len(desc) > 300 else ''}\n"
        )

    profile_lines = "\n".join(f"- **{k}**: {v}" for k, v in PROFILE.items())

    return f"""# Claude Co-Work: Job Application Queue
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Jobs to apply: {len(jobs)}

---

## Your Task

You are helping apply to the jobs listed below using Chrome DevTools MCP.

**Chrome must be running with remote debugging:**
```
open -a 'Google Chrome' --args --remote-debugging-port=9222
```

### For each job, do this in order:

1. Use `list_pages` to check if Chrome is open
2. Navigate to the job's **URL** using `navigate_page`
3. Wait for page to load (`wait_for` domcontentloaded)
4. Take a screenshot to understand the page
5. Find and click the Apply button (look for "Apply", "Easy Apply", "Apply Now")
6. Fill form fields using the **Profile** below — match label text to field
7. For file upload fields (resume), upload the **Resume** path for that job
8. Click Next/Continue for each step; click Submit on final step
9. Confirm success (look for "Application submitted", "Thanks for applying", etc.)
10. Report: ✅ Applied / ⚠️ Needs manual input / ❌ Failed — with reason

**If you encounter an unknown required field**, pause and ask me before submitting.
**If a CAPTCHA appears**, pause and ask me to solve it.
**Do not skip jobs silently** — report each outcome.

---

## Your Profile (use to fill forms)

{profile_lines}

---

## Jobs Queue

{chr(10).join(job_lines)}

---

## Instructions

- Process jobs **one at a time**, report outcome before moving to next
- Keep Chrome open between jobs (reuse existing session)
- If a job URL is missing or 404, skip and report
- After all jobs done, give a summary table: Job | Company | Status | Notes
"""

with st.expander("📤 Export for Claude Co-Work", expanded=False):
    st.caption("Download a prompt file you can feed to Claude Code to apply automatically via Chrome DevTools MCP.")
    export_md = _build_claude_export(apply_queue, st.session_state.tailored_paths)
    st.download_button(
        label="⬇️ Download apply_queue_prompt.md",
        data=export_md.encode("utf-8"),
        file_name=f"apply_queue_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
        mime="text/markdown",
        use_container_width=True,
    )
    with st.container():
        st.code(export_md, language="markdown")

st.divider()

# --- Mode controls ---
col_toggle, col_autorun, col_reset = st.columns([3, 2, 1])
with col_toggle:
    queue_mode = st.toggle("🚀 Queue Mode — process jobs one by one", value=st.session_state.queue_mode)
    st.session_state.queue_mode = queue_mode
with col_autorun:
    if not st.session_state.auto_run:
        if st.button("🤖 Auto Run All", type="primary", use_container_width=True):
            _log("info", "Auto-run started — %d jobs queued (filter=%s)", len(apply_queue), status_filter)
            st.session_state.auto_run = True
            st.session_state.auto_run_idx = 0
            st.session_state.auto_run_state = "idle"
            st.session_state.auto_run_result = {}
            st.session_state.auto_run_user_inputs = {}
            st.rerun()
    else:
        if st.button("⏹ Stop Auto-Run", type="secondary", use_container_width=True):
            idx = st.session_state.auto_run_idx
            _log("info", "Auto-run stopped by user at job %d/%d", idx + 1, len(apply_queue))
            st.session_state.auto_run = False
            st.session_state.auto_run_state = "idle"
            st.rerun()
with col_reset:
    if st.button("↺ Reset", key="reset_queue"):
        st.session_state.queue_index = 0
        logger.debug("Queue index reset")
        st.rerun()

# =========================================================
# AUTO-RUN MODE
# =========================================================
if st.session_state.auto_run:
    idx = st.session_state.auto_run_idx

    if idx >= len(apply_queue):
        _log("info", "Auto-run complete — all %d jobs processed", len(apply_queue))
        st.success("🎉 Auto-Run complete! All jobs processed.")
        st.session_state.auto_run = False
        if st.button("↺ Start Over"):
            st.session_state.auto_run_idx = 0
            st.rerun()
        st.stop()

    job = apply_queue[idx]
    jid = job["Job ID"]
    url = job.get("Application URL", "")
    company = job.get("Company", "?")
    role = job.get("Role", "?")

    resume_path, resume_type = pick_resume(job)
    tailored_path = st.session_state.tailored_paths.get(jid)
    active_resume = tailored_path or resume_path

    ar_state = st.session_state.auto_run_state

    # ---- IDLE: tailor first (if needed), then apply ----
    if ar_state == "idle":
        if not url:
            _log("warning", "Auto-run [%d/%d]: no URL — %s @ %s", idx + 1, len(apply_queue), role, company)
            st.session_state.auto_run_state = "failed"
            st.session_state.auto_run_result = {
                "status": "failed",
                "reason": f"No Application URL for **{role}** @ {company}",
            }
            st.rerun()

        has_description = len(str(job.get("Description", ""))) > 50
        already_tailored = jid in st.session_state.tailored_paths
        should_tailor = has_description and resume_path and not already_tailored

        if should_tailor:
            _log("info", "Auto-run [%d/%d]: tailoring resume — %s @ %s", idx + 1, len(apply_queue), role, company)
            tailor_result: dict = {}

            def _tailor_thread(rp=resume_path, j=job, r=tailor_result):
                out = generate_tailored_resume(original_docx_path=rp, job=j)
                r["path"] = out

            t = threading.Thread(target=_tailor_thread, daemon=True)
            t.start()
            st.session_state.auto_run_thread = t
            st.session_state.auto_run_tailor_result = tailor_result
            st.session_state.auto_run_state = "tailoring"
            st.rerun()

        extra = dict(st.session_state.auto_run_user_inputs)
        _log("info", "Auto-run [%d/%d]: starting apply — %s @ %s", idx + 1, len(apply_queue), role, company)
        _log("info", "URL: %s | Resume: %s | Extra inputs: %s", url, active_resume, list(extra.keys()))

        thread_result: dict = {}

        def _apply_thread(u=url, rp=active_resume, j=job, ei=extra, r=thread_result):
            res = auto_apply.apply_job(
                job_url=u,
                resume_path=Path(rp) if rp else None,
                job=j,
                extra_inputs=ei,
            )
            r.update(res)

        t = threading.Thread(target=_apply_thread, daemon=True)
        t.start()
        st.session_state.auto_run_thread = t
        st.session_state.auto_run_thread_result = thread_result
        st.session_state.auto_run_state = "applying"
        st.rerun()

    # ---- TAILORING: poll tailor thread ----
    elif ar_state == "tailoring":
        t = st.session_state.auto_run_thread
        tailor_result = st.session_state.auto_run_tailor_result

        if t and t.is_alive():
            st.progress(idx / len(apply_queue))
            st.markdown(
                f"<div style='color:#888; font-size:0.85rem;'>Auto-Run: {idx + 1} / {len(apply_queue)}</div>",
                unsafe_allow_html=True,
            )
            with st.spinner(f"✨ Tailoring resume for **{role}** @ **{company}**…"):
                time.sleep(1)
            st.rerun()
        else:
            out = tailor_result.get("path")
            if out:
                st.session_state.tailored_paths[jid] = out
                _log("info", "Auto-run [%d/%d]: resume tailored — %s", idx + 1, len(apply_queue), out)
            else:
                _log("warning", "Auto-run [%d/%d]: tailoring failed, using base resume", idx + 1, len(apply_queue))
            st.session_state.auto_run_tailor_result = {}
            st.session_state.auto_run_state = "idle"
            st.rerun()

    # ---- APPLYING: poll thread status ----
    elif ar_state == "applying":
        t = st.session_state.auto_run_thread
        thread_result = st.session_state.auto_run_thread_result

        if t and t.is_alive():
            st.progress(idx / len(apply_queue))
            st.markdown(
                f"<div style='color:#888; font-size:0.85rem;'>Auto-Run: {idx + 1} / {len(apply_queue)}</div>",
                unsafe_allow_html=True,
            )
            with st.spinner(f"⚙️ Applying to **{role}** @ **{company}**… Chrome debug port {CHROME_DEBUG_PORT}"):
                time.sleep(1)
            st.rerun()  # poll every second
        else:
            # Thread done — read result
            result = dict(thread_result)
            _log(
                "info" if result.get("status") == "applied" else "warning",
                "Auto-run [%d/%d]: result=%s reason=%s",
                idx + 1, len(apply_queue),
                result.get("status", "?"),
                result.get("reason", ""),
            )
            st.session_state.auto_run_result = result
            st.session_state.auto_run_state = result.get("status", "failed")
            st.rerun()

    # ---- APPLIED: mark tracker, advance ----
    elif ar_state == "applied":
        result = st.session_state.auto_run_result
        _log("info", "Auto-run [%d/%d]: APPLIED — %s @ %s (jid=%s)", idx + 1, len(apply_queue), role, company, jid)
        tracker.update_job({
            "id": jid,
            "status": "applied",
            "date_applied": date.today().strftime("%Y-%m-%d"),
        })
        st.success(f"✅ Applied to **{role}** @ **{company}**")
        st.session_state.auto_run_idx += 1
        st.session_state.auto_run_state = "idle"
        st.session_state.auto_run_user_inputs = {}
        st.session_state.auto_run_result = {}
        time.sleep(1)
        st.rerun()

    # ---- NEEDS INPUT: show dialog ----
    elif ar_state == "needs_input":
        result = st.session_state.auto_run_result
        _log(
            "warning",
            "Auto-run [%d/%d]: needs_input — field='%s' for %s @ %s",
            idx + 1, len(apply_queue),
            result.get("field_name", "?"), role, company,
        )

        st.progress(idx / len(apply_queue))
        st.markdown(
            f"<div style='color:#888; font-size:0.85rem;'>Auto-Run: {idx + 1} / {len(apply_queue)}</div>",
            unsafe_allow_html=True,
        )
        st.warning(
            f"⏸ **Paused** — automation needs your input for **{role}** @ **{company}**"
        )

        info_cols = st.columns(4)
        info_cols[0].metric("Score", f"{safe_score(job.get('Score (%)'))}%")
        info_cols[1].metric("Platform", job.get("Platform", ""))
        info_cols[2].metric("Location", str(job.get("Location", ""))[:20])
        info_cols[3].metric("Debug Port", CHROME_DEBUG_PORT)

        _input_dialog(result)

    # ---- FAILED / MANUAL_REQUIRED: show error dialog ----
    elif ar_state in ("failed", "manual_required"):
        result = st.session_state.auto_run_result
        _log(
            "error",
            "Auto-run [%d/%d]: %s — %s @ %s: %s",
            idx + 1, len(apply_queue), ar_state, role, company, result.get("reason", ""),
        )
        _error_dialog(result)

    # Progress bar + info always visible when not in a blocking state
    if ar_state not in ("applying", "tailoring", "needs_input", "failed", "manual_required"):
        st.progress(idx / len(apply_queue))
        st.markdown(
            f"<div style='color:#888; font-size:0.85rem;'>Auto-Run: {idx + 1} / {len(apply_queue)}</div>",
            unsafe_allow_html=True,
        )
        st.info(
            f"🌐 Processing **{role}** @ **{company}**  \n"
            f"Chrome debug port **{CHROME_DEBUG_PORT}** — Claude can control via DevTools MCP."
        )

    st.stop()

# =========================================================
# QUEUE MODE: one job at a time (manual)
# =========================================================
if queue_mode:
    idx = st.session_state.queue_index

    if idx >= len(apply_queue):
        st.success("✅ All done! Queue complete.")
        if st.button("↺ Start Over"):
            st.session_state.queue_index = 0
            st.rerun()
        st.stop()

    job = apply_queue[idx]
    jid = job["Job ID"]

    resume_path, resume_type = pick_resume(job)
    tailored_path = st.session_state.tailored_paths.get(jid)
    active_resume = tailored_path or resume_path

    st.markdown(
        f"<div style='color:#888; font-size:0.85rem;'>Progress: {idx + 1} / {len(apply_queue)}</div>",
        unsafe_allow_html=True,
    )
    st.progress((idx) / len(apply_queue))
    st.markdown(f"### {job['Role']} @ {job['Company']}")

    info_cols = st.columns(4)
    info_cols[0].metric("Score", f"{safe_score(job.get('Score (%)'))}%")
    info_cols[1].metric("Platform", job.get("Platform", ""))
    info_cols[2].metric("Location", str(job.get("Location", ""))[:20])
    info_cols[3].metric("Resume", RESUME_TYPE_LABELS.get(resume_type, resume_type))

    if tailored_path:
        st.caption(f"✨ Tailored: `{Path(tailored_path).name}`")
    elif resume_path:
        st.caption(f"📁 Base resume: `{resume_path.name}` (auto-selected)")
    else:
        st.warning(f"Resume file not found for type: {resume_type}")

    has_description = len(str(job.get("Description", ""))) > 50
    if not has_description:
        st.warning("⚠️ No description — tailoring will be generic.")

    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)

    tailor_disabled = resume_path is None
    if c1.button("✨ Tailor", key=f"q_tailor_{jid}", disabled=tailor_disabled, width="stretch"):
        logger.info("Queue mode: tailoring resume for %s @ %s", job["Role"], job["Company"])
        with st.status("Tailoring resume with AI…", expanded=True) as s:
            s.write("Reading resume…")
            s.write("Sending to AI…")
            out = generate_tailored_resume(original_docx_path=resume_path, job=job)
            if out:
                st.session_state.tailored_paths[jid] = out
                s.update(label="✅ Resume tailored!", state="complete")
                logger.info("Resume tailored: %s", out)
            else:
                s.update(label="❌ Tailoring failed", state="error")
                logger.error("Resume tailoring failed for %s @ %s", job["Role"], job["Company"])
        st.rerun()

    if c2.button("📥 Download", key=f"q_dl_{jid}", width="stretch"):
        dl_path = tailored_path or resume_path
        if dl_path and Path(dl_path).exists():
            with open(dl_path, "rb") as f:
                st.download_button(
                    label="Save",
                    data=f,
                    file_name=Path(dl_path).name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"q_dl_btn_{jid}",
                )

    url = job.get("Application URL", "")
    chrome_disabled = not url
    if c3.button("🌐 Chrome", key=f"q_chrome_{jid}", disabled=chrome_disabled, width="stretch"):
        logger.info("Queue mode: opening Chrome for %s @ %s — %s", job["Role"], job["Company"], url)
        st.info("Opening Chrome…")
        result = {}

        def _run():
            result.update(launch_and_stage(
                job_url=url,
                resume_path=Path(active_resume) if active_resume else None,
                job=job,
            ))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=35)
        logger.info("Queue mode: Chrome result: %s", result)
        st.session_state.apply_results[jid] = result
        st.rerun()

    chrome_result = st.session_state.apply_results.get(jid)
    if chrome_result and chrome_result.get("status") == "staged":
        staged = chrome_result.get("staged_fields", [])
        st.caption(f"Chrome: staged {', '.join(staged) if staged else 'URL only'}")

    if c4.button("✅ Applied", key=f"q_app_{jid}", width="stretch"):
        logger.info("Queue mode: marked applied — %s @ %s (jid=%s)", job["Role"], job["Company"], jid)
        tracker.update_job({
            "id": jid,
            "status": "applied",
            "date_applied": date.today().strftime("%Y-%m-%d"),
        })
        st.session_state.queue_index += 1
        st.rerun()

    if c5.button("⏭️ Skip", key=f"q_skip_{jid}", width="stretch"):
        logger.info("Queue mode: skipped — %s @ %s (jid=%s)", job["Role"], job["Company"], jid)
        st.session_state.queue_index += 1
        st.rerun()

    if has_description:
        with st.expander("Job Description", expanded=False):
            desc = str(job.get("Description", ""))
            st.write(desc[:2000] + ("…" if len(desc) > 2000 else ""))

    st.stop()

# =========================================================
# LIST MODE: all jobs as expandable cards
# =========================================================
st.subheader(f"📋 {status_filter.title()} Jobs ({len(apply_queue)})")
all_resume_options = get_all_resume_options()

for job in apply_queue:
    jid = job["Job ID"]
    score = safe_score(job.get("Score (%)"))
    description = str(job.get("Description", ""))
    has_description = len(description) > 50

    with st.expander(
        f"**{job['Role']}** @ {job['Company']}  ·  {score}%  ·  {job['Platform']}",
        expanded=False,
    ):
        col_info, col_actions = st.columns([2, 1], gap="large")

        with col_info:
            st.markdown(f"**Location:** {job.get('Location', 'N/A')}")
            st.markdown(f"**Match Score:** `{score}%`")
            if job.get("Matching Skills"):
                st.markdown(f"**Matching:** {job['Matching Skills']}")
            if job.get("Missing Skills"):
                st.markdown(f"**Missing:** {job['Missing Skills']}")
            if job.get("Application URL"):
                st.link_button("🔗 View Original Listing", job["Application URL"])
            if has_description:
                with st.expander("Job Description", expanded=False):
                    st.write(description[:2000] + ("…" if len(description) > 2000 else ""))
            else:
                st.warning("⚠️ No description — resume tailoring may be generic.")

        with col_actions:
            auto_type = classify_job(job)
            resume_type_options = list(RESUME_TYPES.keys())
            default_idx = resume_type_options.index(auto_type)
            selected_type = st.selectbox(
                "Resume",
                options=resume_type_options,
                format_func=lambda t: RESUME_TYPE_LABELS[t],
                index=default_idx,
                key=f"rtype_{jid}",
            )
            base_resume_path = all_resume_options.get(selected_type)
            if base_resume_path:
                st.caption(f"📁 `{base_resume_path.name}`")
            else:
                st.error(f"Resume file not found: {RESUME_TYPES[selected_type]}")

            tailored_path = st.session_state.tailored_paths.get(jid)

            tailor_disabled = base_resume_path is None
            if st.button("✨ Tailor Resume", key=f"tailor_{jid}", disabled=tailor_disabled, width="stretch"):
                logger.info("List mode: tailoring resume for %s @ %s", job["Role"], job["Company"])
                with st.status("Tailoring resume with AI…", expanded=True) as status:
                    st.write("Reading original resume…")
                    st.write("Sending to AI…")
                    out = generate_tailored_resume(original_docx_path=base_resume_path, job=job)
                    if out:
                        st.session_state.tailored_paths[jid] = out
                        tailored_path = out
                        status.update(label="✅ Resume tailored!", state="complete")
                        logger.info("Resume tailored: %s", out)
                    else:
                        status.update(label="❌ Tailoring failed — check AI API keys", state="error")
                        logger.error("Resume tailoring failed for %s @ %s", job["Role"], job["Company"])

            if tailored_path and Path(tailored_path).exists():
                with open(tailored_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Tailored Resume",
                        data=f,
                        file_name=Path(tailored_path).name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_{jid}",
                        width="stretch",
                    )
                st.caption(f"Tailored: `{Path(tailored_path).name}`")
            elif base_resume_path and base_resume_path.exists():
                with open(base_resume_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Base Resume",
                        data=f,
                        file_name=base_resume_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_orig_{jid}",
                        width="stretch",
                    )

            st.markdown("---")

            apply_resume = tailored_path or base_resume_path
            url = job.get("Application URL", "")
            chrome_disabled = not url

            if chrome_disabled:
                st.warning("No application URL.")
            else:
                if st.button("🌐 Open in Chrome", key=f"chrome_{jid}", disabled=chrome_disabled, width="stretch"):
                    logger.info("List mode: opening Chrome for %s @ %s — %s", job["Role"], job["Company"], url)
                    st.info("Opening Chrome…")
                    result = {}

                    def _run_chrome(u=url, rp=apply_resume, j=job, r=result):
                        r.update(launch_and_stage(
                            job_url=u,
                            resume_path=Path(rp) if rp else None,
                            job=j,
                        ))

                    t = threading.Thread(target=_run_chrome, daemon=True)
                    t.start()
                    t.join(timeout=35)
                    logger.info("List mode: Chrome result for %s: %s", jid, result)
                    st.session_state.apply_results[jid] = result
                    st.rerun()

            chrome_result = st.session_state.apply_results.get(jid)
            if chrome_result:
                if chrome_result.get("status") == "staged":
                    staged = chrome_result.get("staged_fields", [])
                    st.success(f"Chrome opened. Staged: {', '.join(staged) if staged else 'URL only'}")
                    if chrome_result.get("debug_port"):
                        st.caption(f"🔌 Debug port {chrome_result['debug_port']} — Claude can control via MCP")
                elif chrome_result.get("status") == "failed":
                    st.error(f"Chrome error: {chrome_result.get('reason', 'unknown')}")
                    logger.error("Chrome failed for %s: %s", jid, chrome_result.get("reason"))

            st.markdown("---")

            b1, b2 = st.columns(2)
            if b1.button("✅ Mark Applied", key=f"app_{jid}", width="stretch"):
                logger.info("List mode: marked applied — %s @ %s (jid=%s)", job["Role"], job["Company"], jid)
                tracker.update_job({
                    "id": jid,
                    "status": "applied",
                    "date_applied": date.today().strftime("%Y-%m-%d"),
                })
                st.success("Marked as applied!")
                st.rerun()

            if b2.button("🚫 Dismiss", key=f"dis_{jid}", width="stretch"):
                logger.info("List mode: dismissed — %s @ %s (jid=%s)", job["Role"], job["Company"], jid)
                tracker.update_job({"id": jid, "status": "rejected"})
                st.rerun()

st.divider()
st.markdown(
    "<div style='text-align:center; color:#666; font-size:0.75rem;'>AI Job Engine • Apply Queue</div>",
    unsafe_allow_html=True,
)
