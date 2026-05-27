import streamlit as st
import os
import pandas as pd
from core.tracker.csv_tracker import CSVTracker
from core.tracker.db import JobCache
from core.ai.scorer import score_batch
from core.resume.parser import ResumeParser
from core.ui.style import apply_custom_style, get_resume_path
import time

st.set_page_config(page_title="Batch Scorer", page_icon="🤖", layout="wide")
apply_custom_style()

st.title("🤖 Batch AI Scorer")
st.markdown("##### *Score jobs in bulk via Claude Code CLI subprocess.*")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Scorer Settings")

    batch_size = st.slider(
        "Batch Size (jobs per Claude call)",
        min_value=1,
        max_value=30,
        value=10,
        help="Jobs per CLI call. Higher = fewer calls but larger prompts. 10 is a good balance."
    )

    st.divider()
    st.markdown("**Active Scorer**")

    try:
        import subprocess
        r = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        cli_version = r.stdout.strip().split("\n")[0] if r.returncode == 0 else None
    except Exception:
        cli_version = None

    if cli_version:
        st.success(f"🟢 **Claude CLI** — `{cli_version}`")
    else:
        st.error("🔴 **Claude CLI** — not found. Install via `npm i -g @anthropic-ai/claude-code`")

    claude_model = os.getenv("CLAUDE_SCORER_MODEL", "claude-sonnet-4-6")
    st.caption(f"Model: `{claude_model}`")

    st.divider()
    st.caption("NIM / OpenRouter / Ollama / Groq — dormant")

tracker = CSVTracker()
db = JobCache()
jobs = tracker.get_all_jobs()

if not jobs:
    st.info("No jobs in tracker. Go to Search to find and save jobs first.")
    st.stop()

df = pd.DataFrame(jobs)

def is_unscored(row):
    score = str(row.get("Score (%)", "")).strip()
    return score == "" or score == "0" or score == "0.0"

unscored_mask = df.apply(is_unscored, axis=1)
unscored_df = df[unscored_mask]

# Count scoreable unscored jobs via single DB query
import sqlite3 as _sqlite3
_db_path = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")
_unscored_ids = set(str(r["Job ID"]).strip() for _, r in unscored_df.iterrows())
try:
    _conn = _sqlite3.connect(_db_path)
    _c = _conn.cursor()
    _c.execute("SELECT id FROM jobs WHERE description IS NOT NULL AND length(description) >= 50")
    _ids_with_desc = {row[0] for row in _c.fetchall()}
    _conn.close()
except Exception:
    _ids_with_desc = set()
# Also count CSV descriptions as fallback
_csv_has_desc = {str(r["Job ID"]).strip() for _, r in unscored_df.iterrows() if len(str(r.get("Description", "")).strip()) >= 50}
has_desc_count = len((_unscored_ids & _ids_with_desc) | (_unscored_ids & _csv_has_desc))
no_desc_count = len(unscored_df) - has_desc_count

col_stats, col_action = st.columns([1, 2], gap="large")

with col_stats:
    st.subheader("📊 Tracker Status")
    st.metric("Total Jobs", len(df))
    st.metric("Unscored Jobs", len(unscored_df), delta=f"{len(unscored_df)} pending", delta_color="inverse")
    scored_count = len(df) - len(unscored_df)
    if scored_count > 0:
        st.metric("Already Scored", scored_count)
    st.metric("Scoreable (have desc)", has_desc_count)
    if no_desc_count > 0:
        st.caption(f"⚠️ {no_desc_count} jobs have no cached description — will be fetched live during scoring.")

    if unscored_df.empty:
        st.success("All jobs are already scored! ✨")
        st.stop()

with col_action:
    st.subheader("🎯 Mission Control")

    with st.form("batch_score_form"):
        mission_context = st.radio(
            "Resume Context",
            options=["EU", "IN", "remote_contractual"],
            index=0,
            horizontal=True,
            help="Select the resume version to score against."
        )

        target_platform = st.selectbox(
            "Filter by Platform",
            options=["All"] + sorted(unscored_df["Platform"].unique().tolist())
        )

        limit = st.number_input(
            "Max jobs to score in this batch",
            value=min(len(unscored_df), 50),
            min_value=1,
            max_value=500
        )

        submitted = st.form_submit_button("🚀 START SCORING MISSION", width="stretch")

if submitted:
    to_score_df = unscored_df.copy()
    if target_platform != "All":
        to_score_df = to_score_df[to_score_df["Platform"] == target_platform]

    to_score_df = to_score_df.head(int(limit))

    if to_score_df.empty:
        st.warning("No jobs match your filters.")
        st.stop()

    with st.status(f"🤖 Scoring up to {len(to_score_df)} jobs via Claude CLI...", expanded=True) as status:
        # 1. Load Resume
        resume_path = get_resume_path(mode="score", job_type=mission_context)
        if not resume_path:
            status.update(label=f"❌ Resume '{mission_context}' not found!", state="error")
            st.stop()

        status.write(f"📄 Parsing `{os.path.basename(resume_path)}`...")
        parser = ResumeParser()
        resume_text = parser.parse(str(resume_path))

        # 2. Enrich jobs with full descriptions from DB
        db = JobCache()
        jobs_to_score = []
        skipped_no_desc = []
        import logging
        enrich_logger = logging.getLogger("job_hunt.pages.batch_scorer")

        for _, row in to_score_df.iterrows():
            jid = str(row["Job ID"]).strip()
            db_job = db.get_job(jid)

            if db_job:
                description = db_job.get("description")
                enrich_logger.info("Enriched job %s from DB (desc len: %d)", jid, len(str(description or "")))
            else:
                description = row.get("Description")
                enrich_logger.warning("Job %s not in DB, using CSV snippet", jid)

            desc_str = str(description or "").strip()
            if len(desc_str) < 50:
                skipped_no_desc.append({"id": jid, "platform": str(row["Platform"]), "company": str(row["Company"])})
                continue

            jobs_to_score.append({
                "id": jid,
                "description": desc_str,
                "title": str(row["Role"]),
                "company": str(row["Company"]),
                "location": str(row["Location"]),
                "platform": str(row["Platform"]),
                "application_url": str(row["Application URL"])
            })

        if skipped_no_desc:
            status.write(f"⚠️ Skipped {len(skipped_no_desc)} jobs with no description (WorkInLuxembourg, Greenhouse, etc. — use Description Fetcher page first).")

        if not jobs_to_score:
            status.update(label="❌ All selected jobs have no descriptions — nothing to score. Filter by Hirist, Lever, or ArbeitNow.", state="error")
            st.stop()

        # 3. Score
        import threading
        scored_results = {}
        tally = {"ClaudeCLI": 0}
        collect_lock = threading.Lock()
        scoreable_ids = {j["id"] for j in jobs_to_score}
        id_to_orig = {str(row["Job ID"]).strip(): row for _, row in to_score_df.iterrows() if str(row["Job ID"]).strip() in scoreable_ids}

        def on_chunk(results, scorer="ClaudeCLI"):
            with collect_lock:
                tally[scorer] = tally.get(scorer, 0) + len(results)
                for res in results:
                    jid = str(res.get("id", "")).strip()
                    orig_row = id_to_orig.get(jid)
                    if orig_row is None:
                        continue
                    score = int(float(res.get("score", 0)))
                    if jid not in scored_results or (scored_results[jid][0].get("score", 0) == 0 and score > 0):
                        scored_results[jid] = (res, orig_row, scorer)

        status.write(f"⏳ Scoring {len(jobs_to_score)} jobs (with descriptions) in chunks of {batch_size}...")
        score_batch(resume_text, jobs_to_score, batch_size=batch_size, on_chunk_complete=on_chunk)

        raw_total = sum(tally.values())
        status.write(f"📊 Scoring done — {raw_total} raw results | {len(scored_results)} matched to tracker")

        if raw_total > 0 and len(scored_results) == 0:
            status.update(label="❌ Results returned but no Job IDs matched tracker — check logs", state="error")
            st.stop()

        # 4. Persist — write DB/CSV from main thread
        save_errors = 0
        for jid, (res, orig_row, scorer) in scored_results.items():
            try:
                update_data = {
                    "id": jid,
                    "title": orig_row.get("Role"),
                    "company": orig_row.get("Company"),
                    "location": orig_row.get("Location"),
                    "platform": orig_row.get("Platform"),
                    "description": orig_row.get("Description"),
                    "application_url": orig_row.get("Application URL"),
                    "date_found": orig_row.get("Date Found"),
                    "salary": orig_row.get("Salary"),
                    "is_remote": orig_row.get("Remote") == "Yes",
                    "notes": orig_row.get("Notes"),
                    "score": int(float(res.get("score", 0))),
                    "matching_skills": res.get("matching_skills", []),
                    "missing_skills": res.get("missing_skills", []),
                    "recommendation": res.get("recommendation", ""),
                    "status": orig_row.get("Status", "new"),
                }
                db.add_job(update_data)
                tracker.update_job(update_data)
            except Exception as e:
                save_errors += 1
                st.warning(f"Save failed for {jid}: {e}")

        total_saved = len(scored_results) - save_errors
        skipped_msg = f" | ⏭️ {len(skipped_no_desc)} skipped (no desc)" if skipped_no_desc else ""
        status.update(
            label=f"✅ Done! {total_saved}/{len(jobs_to_score)} saved via Claude CLI{skipped_msg}"
                  + (f" | ⚠️ {save_errors} save errors" if save_errors else ""),
            state="complete" if not save_errors else "error"
        )

        st.balloons()
        time.sleep(2)
        st.rerun()

# --- Preview Table ---
st.divider()
st.subheader("👀 Pending Jobs Preview")
st.dataframe(
    unscored_df[["Platform", "Company", "Role", "Location", "Date Found"]].head(100),
    use_container_width=True
)
