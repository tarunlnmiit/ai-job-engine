import streamlit as st
import os
import pandas as pd
from datetime import datetime
from core.tracker.csv_tracker import CSVTracker
from core.tracker.db import JobCache
from core.ai.scorer import score_batch
from core.resume.parser import ResumeParser
from core.ui.style import apply_custom_style, get_resume_path
import time

st.set_page_config(page_title="Batch Scorer", page_icon="🤖", layout="wide")
apply_custom_style()

st.title("🤖 Batch AI Scorer")
st.markdown("##### *Score previously saved jobs in bulk using NIM + OpenRouter in parallel.*")

# --- AI Configuration Sidebar ---
with st.sidebar:
    st.header("⚙️ AI Engine Settings")
    nim_batch_size = st.slider(
        "Batch Size (jobs per request)",
        min_value=1,
        max_value=20,
        value=int(os.getenv("NIM_BATCH_SIZE", "5")),
        help="How many jobs per chunk sent to each scorer. Higher = fewer requests but larger payloads."
    )
    os.environ["NIM_BATCH_SIZE"] = str(nim_batch_size)

    st.divider()
    st.markdown("**Scorers**")

    nim_key = os.getenv("NVIDIA_API_KEY", "")
    nim_model = os.getenv("NIM_MODEL", "z-ai/glm4.7")
    nim_ok = bool(nim_key and "your_" not in nim_key)
    st.markdown(f"{'🟢' if nim_ok else '🔴'} **NIM** — `{nim_model}`")

    or_key = os.getenv("OPENROUTER_API_KEY", "")
    or_model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    or_fallbacks = os.getenv("OPENROUTER_FALLBACK_MODELS", "")
    or_ok = bool(or_key and "your_" not in or_key)
    st.markdown(f"{'🟢' if or_ok else '🔴'} **OpenRouter** — `{or_model}`")
    if or_fallbacks and or_ok:
        with st.expander("Fallback models"):
            for m in or_fallbacks.split(","):
                st.caption(m.strip())

    ollama_model = os.getenv("OLLAMA_MODEL", "")
    st.markdown(f"🟡 **Ollama** — `{ollama_model or 'auto-detect'}` *(fallback only)*")

    st.divider()
    if not nim_ok and not or_ok:
        st.error("No scorers active. Set NVIDIA_API_KEY or OPENROUTER_API_KEY in .env")
    elif nim_ok and or_ok:
        st.success("NIM + OpenRouter both active — parallel mode")
    elif nim_ok:
        st.warning("Only NIM active — OpenRouter key missing")
    elif or_ok:
        st.warning("Only OpenRouter active — NIM key missing")

tracker = CSVTracker()
db = JobCache()
jobs = tracker.get_all_jobs()

if not jobs:
    st.info("No jobs found in the tracker. Go to Search to find and save jobs first.")
    st.stop()

df = pd.DataFrame(jobs)

def is_unscored(row):
    score = str(row.get("Score (%)", "")).strip()
    return score == "" or score == "0" or score == "0.0"

unscored_mask = df.apply(is_unscored, axis=1)
unscored_df = df[unscored_mask]

col_stats, col_action = st.columns([1, 2], gap="large")

with col_stats:
    st.subheader("📊 Tracker Status")
    st.metric("Total Jobs", len(df))
    st.metric("Unscored Jobs", len(unscored_df), delta=f"{len(unscored_df)} pending", delta_color="inverse")

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
            help="Select the resume version to score these jobs against."
        )

        target_platform = st.selectbox("Filter by Platform", options=["All"] + sorted(unscored_df["Platform"].unique().tolist()))

        limit = st.number_input("Max jobs to score in this batch", value=min(len(unscored_df), 50), min_value=1, max_value=500)

        submitted = st.form_submit_button("🚀 START SCORING MISSION", width="stretch")

if submitted:
    to_score_df = unscored_df.copy()
    if target_platform != "All":
        to_score_df = to_score_df[to_score_df["Platform"] == target_platform]

    to_score_df = to_score_df.head(int(limit))

    if to_score_df.empty:
        st.warning("No jobs match your filters.")
        st.stop()

    with st.status(f"🤖 Scoring {len(to_score_df)} jobs via NIM + OpenRouter...", expanded=True) as status:
        # 1. Load Resume
        resume_path = get_resume_path(mode="score", job_type=mission_context)
        if not resume_path:
            status.update(label=f"❌ Resume '{mission_context}' not found!", state="error")
            st.stop()

        status.write(f"📄 Parsing `{os.path.basename(resume_path)}`...")
        parser = ResumeParser()
        resume_text = parser.parse(str(resume_path))

        # 2. Prepare jobs — Enrich with full descriptions from DB
        db = JobCache()
        jobs_to_score = []
        import logging
        enrich_logger = logging.getLogger("job_hunt.pages.batch_scorer")
        
        for _, row in to_score_df.iterrows():
            jid = str(row["Job ID"]).strip()
            # Try to get full description from SQLite DB
            db_job = db.get_job(jid)
            
            if db_job:
                description = db_job.get("description")
                enrich_logger.info("Enriched job %s from DB (desc len: %d)", jid, len(str(description or "")))
            else:
                description = row.get("Description")
                enrich_logger.warning("Job %s NOT found in DB, using CSV snippet", jid)
            
            jobs_to_score.append({
                "id": jid,
                "description": str(description or "No description available"),
                "title": str(row["Role"]),
                "company": str(row["Company"]),
                "location": str(row["Location"]),
                "platform": str(row["Platform"]),
                "application_url": str(row["Application URL"])
            })

        # 3. Score — collect results from threads, write DB/CSV in main thread after
        import threading
        scored_results = {}          # job_id → (res, orig_row, scorer)
        tally = {"NIM": 0, "OpenRouter": 0, "Ollama": 0}
        collect_lock = threading.Lock()

        # Build a lookup from job_id → orig_row for fast ID matching
        id_to_orig = {str(row["Job ID"]).strip(): row for _, row in to_score_df.iterrows()}

        def on_chunk(results, scorer="Unknown"):
            # Called from background threads — only collect, no Streamlit/file I/O
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

        status.write("⏳ Scoring in progress (NIM + OpenRouter parallel)...")
        score_batch(resume_text, jobs_to_score, on_chunk_complete=on_chunk)

        # Diagnostic: surface tally vs collected count
        raw_total = sum(tally.values())
        status.write(
            f"📊 Scoring done — raw results: {raw_total} "
            f"(NIM:{tally['NIM']} OR:{tally['OpenRouter']} Ollama:{tally['Ollama']}) "
            f"| matched to tracker: {len(scored_results)}"
        )
        if raw_total > 0 and len(scored_results) == 0:
            status.update(label="❌ Scoring returned results but no Job IDs matched tracker — check logs", state="error")
            st.stop()

        # All threads done — write DB/CSV from main thread sequentially
        save_errors = 0
        for jid, (res, orig_row, scorer) in scored_results.items():
            jid = str(res.get("id", ""))
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
                st.warning(f"Save failed for job {jid}: {e}")

        total_saved = len(scored_results) - save_errors
        status.update(
            label=f"✅ Done! {total_saved}/{len(jobs_to_score)} saved — NIM:{tally['NIM']} OR:{tally['OpenRouter']} Ollama:{tally['Ollama']}"
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
