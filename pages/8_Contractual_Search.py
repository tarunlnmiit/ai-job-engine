import streamlit as st
import yaml
import os
from pathlib import Path
from datetime import datetime
import asyncio
import inspect
from dotenv import load_dotenv
from core.ui.style import apply_custom_style, safe_score

load_dotenv()

st.set_page_config(page_title="Contractual Search", page_icon="📝", layout="wide")
apply_custom_style()

from core.ui.components import render_role_expander

st.title("📝 Contractual Roles Search")
st.markdown("##### *Specialized engine for Remote Contractual opportunities.*")

# --- Global Role Expander ---
roles_text_val = render_role_expander(config_key="contractual_roles_text")

# Load existing config for defaults
config_path = Path("config.yaml")
if config_path.exists():
    with open(config_path) as f:
        config = yaml.safe_load(f)
else:
    config = {}

# Sidebar for User Profile
with st.sidebar:
    st.header("👤 Your Contractual Profile")
    hourly_rate = st.number_input("Target Hourly Rate ($)", value=50.0, step=5.0)
    availability = st.selectbox("Availability", options=["Immediate", "1 Week", "2 Weeks", "1 Month"])
    
    st.info("These settings will be used by the AI Scorer to prioritize suitable opportunities.")
    
    st.divider()
    st.subheader("🌍 Official Portals")
    st.markdown("""
    - [Turing](https://www.turing.com/)
    - [Andela](https://andela.com/)
    - [Braintrust](https://usebraintrust.com/)
    - [Arc.dev](https://arc.dev/)
    """)
    
    st.divider()
    st.subheader("⚙️ AI Engine Settings")
    nim_batch_size = st.slider(
        "NIM Batch Size",
        min_value=1,
        max_value=20,
        value=int(os.getenv("NIM_BATCH_SIZE", "5")),
        key="nim_batch_size_contract"
    )
    os.environ["NIM_BATCH_SIZE"] = str(nim_batch_size)

col_main, col_info = st.columns([2, 1])

with col_main:
    with st.form("contractual_search"):
        st.subheader("🎯 Mission Parameters")
        
        c1, c2 = st.columns(2)
        with c1:
            roles_text = st.text_area(
                "Roles to search",
                value=st.session_state.get("contractual_roles_text", "\n".join(config.get("search", {}).get("roles", ["Python Developer", "Software Engineer"]))),
                height=120,
                help="Use the AI Role Variant Generator above to expand this list."
            )
        with c2:
            locations = st.multiselect(
                "Target Locations",
                options=["Remote", "US Remote", "Global", "India Remote"],
                default=["Remote", "Global"]
            )
            
        st.subheader("🌐 Specialized Platforms")
        platforms = st.multiselect(
            "Select Contractual-focused portals",
            options=[
                "uplers", "braintrust", "andela", "arc_dev", "mercor", "turing", "pro5"
            ],
            default=["uplers", "braintrust", "andela", "arc_dev", "mercor", "turing", "pro5"]
        )
        
        max_pages = st.number_input("Search Depth (Pages per location)", value=1, min_value=1, max_value=5)
        skip_scoring = st.checkbox("🚀 Save Only (Skip AI Scoring)", value=False, help="Fast mode: Scrape jobs now and score them later.")
        
        submitted = st.form_submit_button("🚀 INITIATE CONTRACTUAL SEARCH", width="stretch")

with col_info:
    st.subheader("ℹ️ Contractual Logic")
    st.markdown("""
    - **Remote First**: Focuses on platforms specialized in remote freelance/contractual roles.
    - **Context Injection**: Your target hourly rate and availability are added to every AI scoring prompt.
    """)

if submitted:
    if not locations:
        st.error("Please select at least one location.")
        st.stop()
        
    with st.status("🌍 Orchestrating Contractual Search...", expanded=True) as status:
        from core.scraper import (
            UplersScraper, BraintrustScraper, AndelaScraper, 
            ArcDevScraper, MercorScraper, TuringScraper, Pro5Scraper
        )
        from core.tracker.db import JobCache
        from core.tracker.csv_tracker import CSVTracker
        from core.ai.scorer import score_batch
        from core.resume.parser import ResumeParser
        
        scraper_map = {
            "uplers": UplersScraper, "braintrust": BraintrustScraper, "andela": AndelaScraper,
            "arc_dev": ArcDevScraper, "mercor": MercorScraper, "turing": TuringScraper,
            "pro5": Pro5Scraper
        }
        
        from core.ui.style import get_resume_path
        # Use full resume for scoring
        resume_path = get_resume_path(mode="score", job_type="India") # Defaulting to India/Full since we don't have a Contractual specific path helper yet
        
        if not resume_path:
            status.update(label="❌ Resume not found!", state="error")
            st.stop()
            
        status.write(f"📄 Analyzing Resume: {os.path.basename(resume_path)}...")
        parser = ResumeParser()
            
        resume_text = parser.parse(str(resume_path))
        contract_context = f"\n\n[CONTRACTUAL CONTEXT]\n- Target Hourly Rate: ${hourly_rate}\n- Availability: {availability}\n"
        resume_text += contract_context
        
        all_jobs = []
        roles = [r.strip() for r in roles_text.split("\n") if r.strip()]
        
        for platform in platforms:
            if platform not in scraper_map: continue
            scraper = scraper_map[platform]()
            for location in locations:
                for role in roles:
                    status.write(f"🔍 {platform}: {role} in {location}...")
                    try:
                        search_role = role
                        if inspect.iscoroutinefunction(scraper.search):
                            jobs = asyncio.run(scraper.search(role=search_role, location=location, max_pages=max_pages))
                        else:
                            jobs = scraper.search(role=search_role, location=location, max_pages=max_pages)
                        all_jobs.extend(jobs)
                    except Exception as e:
                        status.write(f"⚠️ Error on {platform}: {e}")
        
        if all_jobs:
            status.write(f"⭐ Found {len(all_jobs)} jobs. Commencing AI Scoring...")
            jobs_dicts = [j.to_dict() for j in all_jobs]
            db = JobCache(); tracker = CSVTracker()
            
            if skip_scoring:
                status.write(f"💾 Saving {len(all_jobs)} unscored jobs...")
                existing = tracker.get_all_jobs()
                existing_ids = {str(ej.get("Job ID")) for ej in existing}
                new_count = 0
                for job in all_jobs:
                    if str(job.id) not in existing_ids:
                        j_dict = job.to_dict()
                        j_dict["status"] = "new"
                        j_dict["score"] = ""
                        j_dict["job_type"] = "Remote Contractual"
                        db.add_job(j_dict); tracker.update_job(j_dict)
                        new_count += 1
                status.update(label=f"✅ Saved {new_count} new unscored jobs!", state="complete")
            else:
                def on_save(results):
                    job_obj_map = {str(j.id).strip(): j for j in all_jobs}
                    for res in results:
                        jid = str(res.get("id", "")).strip()
                        orig = job_obj_map.get(jid)
                        if not orig: continue
                        j_dict = orig.to_dict()
                        j_dict.update({
                            "score": int(float(res.get("score", 0))), 
                            "matching_skills": res.get("matching_skills", []), 
                            "missing_skills": res.get("missing_skills", []), 
                            "recommendation": res.get("recommendation", ""),
                            "job_type": "Remote Contractual" # Enforce job type label
                        })
                        db.add_job(j_dict); tracker.update_job(j_dict)
                
                score_batch(resume_text, jobs_dicts, on_chunk_complete=on_save)
                status.update(label=f"✅ Mission Complete! {len(all_jobs)} jobs processed.", state="complete")
        else:
            status.update(label="⚠️ No jobs found.", state="complete")
