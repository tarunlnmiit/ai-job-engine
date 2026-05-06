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
st.markdown("##### *Score previously saved jobs in bulk using your AI engine.*")

# --- AI Configuration Sidebar ---
with st.sidebar:
    st.header("⚙️ AI Engine Settings")
    nim_batch_size = st.slider(
        "NIM Batch Size (Jobs per request)",
        min_value=1,
        max_value=20,
        value=int(os.getenv("NIM_BATCH_SIZE", "5")),
        help="How many jobs to send to Mistral/NIM at once. Higher is faster but requires more output tokens."
    )
    # Update environment variable for current session
    os.environ["NIM_BATCH_SIZE"] = str(nim_batch_size)
    
    st.info(f"Using Mistral Large 3 via NVIDIA NIM. Current batch size: {nim_batch_size}")
    st.divider()

tracker = CSVTracker()
db = JobCache()
jobs = tracker.get_all_jobs()

if not jobs:
    st.info("No jobs found in the tracker. Go to Search to find and save jobs first.")
    st.stop()

df = pd.DataFrame(jobs)

# Identify unscored jobs
# Scored jobs have a non-empty, non-zero Score (%)
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
    # Filter by platform if needed
    to_score_df = unscored_df.copy()
    if target_platform != "All":
        to_score_df = to_score_df[to_score_df["Platform"] == target_platform]
    
    to_score_df = to_score_df.head(int(limit))
    
    if to_score_df.empty:
        st.warning("No jobs match your filters.")
        st.stop()
        
    with st.status(f"🤖 Scoring {len(to_score_df)} jobs...", expanded=True) as status:
        # 1. Load Resume
        resume_path = get_resume_path(mode="score", job_type=mission_context)
        if not resume_path:
            status.update(label=f"❌ Resume '{mission_context}' not found!", state="error")
            st.stop()
            
        status.write(f"📄 Parsing {os.path.basename(resume_path)}...")
        parser = ResumeParser()
        resume_text = parser.parse(str(resume_path))
        
        # 2. Prepare jobs
        jobs_to_score = []
        for _, row in to_score_df.iterrows():
            jobs_to_score.append({
                "id": str(row["Job ID"]),
                "description": str(row["Description"]),
                "title": str(row["Role"]),
                "company": str(row["Company"]),
                "location": str(row["Location"]),
                "platform": str(row["Platform"]),
                "application_url": str(row["Application URL"])
            })
            
        # 3. Score
        def on_chunk(results):
            status.write(f"💾 Saving chunk of {len(results)} results...")
            for res in results:
                jid = res.get("id")
                # Find original job data to preserve other fields
                orig_row = to_score_df[to_score_df["Job ID"] == jid].iloc[0].to_dict()
                
                update_data = {
                    "id": jid,
                    "title": orig_row.get("Role"),
                    "company": orig_row.get("Company"),
                    "location": orig_row.get("Location"),
                    "platform": orig_row.get("Platform"),
                    "description": orig_row.get("Description"),
                    "application_url": orig_row.get("Application URL"),
                    "score": int(float(res.get("score", 0))),
                    "matching_skills": res.get("matching_skills", []),
                    "missing_skills": res.get("missing_skills", []),
                    "recommendation": res.get("recommendation", ""),
                    "status": "new"
                }
                db.add_job(update_data)
                tracker.update_job(update_data)
        
        score_batch(resume_text, jobs_to_score, on_chunk_complete=on_chunk)
        status.update(label=f"✅ Mission Complete! {len(to_score_df)} jobs scored.", state="complete")
        
        st.balloons()
        time.sleep(2)
        st.rerun()

# --- Preview Table ---
st.divider()
st.subheader("👀 Pending Jobs Preview")
st.dataframe(
    unscored_df[["Platform", "Company", "Role", "Location", "Date Found"]].head(100),
    width="stretch"
)
