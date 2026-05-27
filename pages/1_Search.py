"""Search configuration page."""

import streamlit as st
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from core.ui.style import apply_custom_style

load_dotenv()

st.set_page_config(page_title="Search Engine", page_icon="🔍", layout="wide")
apply_custom_style()

st.title("🔍 Job Search Engine")
st.markdown("##### *Configure your AI agents and orchestrate the search.*")

# Load existing config
config_path = Path("config.yaml")
if config_path.exists():
    with open(config_path) as f:
        config = yaml.safe_load(f)
else:
    config = {}

from core.ui.components import render_role_expander

# --- Global Role Expander ---
roles_text_val = render_role_expander(config_key="roles_text")

st.markdown("<br><br>", unsafe_allow_html=True)

col_main, col_side = st.columns([2, 1], gap="large")

with col_main:
    with st.form("search_config"):
        st.subheader("🎯 Target & Thresholds")
        
        c1, c2 = st.columns(2)
        with c1:
            roles_text = st.text_area(
                "Final Roles List",
                height=150,
                key="roles_text"
            )
        with c2:
            locations_text = st.text_area(
                "Locations",
                value="\n".join(config.get("search", {}).get("locations", ["India", "Remote"])),
                height=150
            )

        st.subheader("⚖️ Filters")
        f1, f2, f3 = st.columns(3)
        with f1:
            experience = st.number_input("Min Experience", value=config.get("search", {}).get("experience_years", 3), min_value=0)
        with f2:
            salary_min = st.number_input("Min Salary (INR)", value=config.get("search", {}).get("salary_min_inr", 1500000), step=100000)
        with f3:
            score_threshold = st.slider("Min AI Score (%)", 0, 100, config.get("ai", {}).get("score_threshold", 65), 5)

        st.subheader("📄 Resume & Context")
        mission_context = st.radio(
            "Mission Context (Which CV to score against?)",
            options=["EU", "IN", "remote_contractual"],
            index=0,
            horizontal=True,
            help="Select the context for AI scoring. This will use the 'Full Resumes' version for scoring."
        )

        st.subheader("🌐 Platforms")
        platforms = st.multiselect(
            "Scrapers to engage",
            options=[
                "linkedin", "naukri", "wellfound", "indeed_india",
                "greenhouse", "lever", "remotive", "weworkremotely", "instahyre", 
                "hacker_news", "hirist", "arbeitnow", "relocateme", "thehub"
            ],
            default=config.get("portals", ["linkedin", "naukri", "greenhouse", "lever", "hacker_news"])
        )

        st.subheader("⚙️ Execution Settings")
        e1, e2 = st.columns(2)
        with e1:
            max_pages = st.number_input("Depth (Pages per target)", value=config.get("search", {}).get("max_pages", 1), min_value=1, max_value=20)
        with e2:
            remote_ok = st.checkbox("Include Remote Global", value=config.get("search", {}).get("remote_ok", True))
            skip_scoring = st.checkbox("🚀 Save Only (Skip AI Scoring)", value=False, help="Fast mode: Scrape jobs now and score them later from the Batch Scorer page.")

        submitted = st.form_submit_button("🚀 INITIATE GLOBAL SEARCH", width="stretch")

with col_side:
    st.subheader("🛠️ Maintenance")
    if st.button("🧹 Clear Browser Session", width="stretch"):
        import shutil
        session_dir = "data/browser_session"
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
            st.success("Session cleared!")
        else:
            st.info("Session already clean.")
    
    if st.button("⏱️ Benchmark AI Speed", width="stretch"):
        from core.ai.scorer import benchmark_ollama_models
        with st.status("Testing models...") as status:
            fastest = benchmark_ollama_models()
            status.update(label=f"Fastest local model: {fastest or 'None found'}", state="complete")
    
    st.divider()
    st.subheader("⚙️ AI Engine Settings")
    nim_batch_size = st.slider(
        "NIM Batch Size (Jobs/req)",
        min_value=1,
        max_value=20,
        value=int(os.getenv("NIM_BATCH_SIZE", "5")),
        key="nim_batch_size_search"
    )
    os.environ["NIM_BATCH_SIZE"] = str(nim_batch_size)

    st.divider()

    st.divider()
    st.info("""
    **Search Workflow**:
    1. Scrapers open a browser window.
    2. Solve any Cloudflare/Logins manually.
    3. AI scores jobs in the background.
    4. Results appear in **Job Feed** immediately.
    """)

if submitted:
    # Save config
    search_config = {
        "search": {
            "roles": [r.strip() for r in roles_text.split("\n") if r.strip()],
            "locations": [l.strip() for l in locations_text.split("\n") if l.strip()],
            "experience_years": int(experience),
            "salary_min_inr": int(salary_min),
            "max_pages": int(max_pages),
            "remote_ok": remote_ok,
        },
        "portals": platforms,
        "ai": {
            "score_threshold": score_threshold,
        }
    }
    with open(config_path, "w") as f:
        yaml.dump(search_config, f)

    with st.status("🚀 Orchestrating Search...", expanded=True) as status:
        try:
            from core.resume.parser import ResumeParser
            from core.ai.scorer import score_batch
            from core.tracker.db import JobCache
            from core.tracker.csv_tracker import CSVTracker
            from core.ai.deduplicator import Deduplicator
            from core.scraper import (
                LinkedInScraper, NaukriScraper, GreenhouseScraper,
                LeverScraper, WellfoundScraper, IndeedScraper,
                RemotiveScraper, WeWorkRemotely, InstahyreScraper,
                HackerNewsScraper, HiristScraper, ArbeitNowScraper,
                RelocateMeScraper, TheHubScraper
            )
            from datetime import datetime
            import asyncio, inspect
            import threading
            from concurrent.futures import ThreadPoolExecutor
            from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

            from core.ui.style import get_resume_path
            # Use the selected mission context for scoring (mode="score")
            resume_path = get_resume_path(mode="score", job_type=mission_context)
            
            if not resume_path:
                status.update(label=f"❌ Full Resume for '{mission_context}' not found in 'resume/Full Resumes'!", state="error")
                st.stop()

            status.write(f"📄 Analyzing Full Resume: {os.path.basename(resume_path)}...")
            parser = ResumeParser()
            resume_text = parser.parse(str(resume_path))
            
            # Store the mission context in session state for downstream pages (like Apply Queue)
            st.session_state["mission_context"] = mission_context
            
            db = JobCache()
            tracker = CSVTracker()
            scraper_map = {
                "linkedin": LinkedInScraper, "naukri": NaukriScraper, "greenhouse": GreenhouseScraper,
                "lever": LeverScraper, "wellfound": WellfoundScraper, "indeed_india": IndeedScraper,
                "remotive": RemotiveScraper, "weworkremotely": WeWorkRemotely, "instahyre": InstahyreScraper,
                "hacker_news": HackerNewsScraper, "hirist": HiristScraper, "arbeitnow": ArbeitNowScraper,
                "relocateme": RelocateMeScraper, "thehub": TheHubScraper
            }

            all_jobs = []
            all_jobs_lock = threading.Lock()
            status_lock = threading.Lock()
            _ctx = get_script_run_ctx()

            def log(msg):
                with status_lock:
                    try:
                        status.write(msg)
                    except Exception:
                        pass

            def run_platform(platform):
                add_script_run_ctx(threading.current_thread(), _ctx)
                if platform not in scraper_map:
                    return
                scraper = scraper_map[platform]()
                for role in search_config["search"]["roles"]:
                    for location in search_config["search"]["locations"]:
                        log(f"🔍 Searching {platform}: {role} in {location}...")
                        try:
                            if inspect.iscoroutinefunction(scraper.search):
                                jobs = asyncio.run(scraper.search(role=role, location=location, remote=remote_ok, max_pages=int(max_pages)))
                            else:
                                jobs = scraper.search(role=role, location=location, remote=remote_ok, max_pages=int(max_pages))
                            with all_jobs_lock:
                                all_jobs.extend(jobs)
                        except Exception as e:
                            log(f"⚠️ Error on {platform}: {e}")

            platform_workers = max(1, min(len(platforms), 8))
            with ThreadPoolExecutor(max_workers=platform_workers) as ex:
                list(ex.map(run_platform, platforms))

            if all_jobs:
                status.write(f"⭐ Found {len(all_jobs)} jobs. Commencing AI Scoring...")
                jobs_dicts = [j.to_dict() if hasattr(j, 'to_dict') else j for j in all_jobs]
                
                if skip_scoring:
                    status.write(f"💾 Saving {len(all_jobs)} unscored jobs...")
                    existing = tracker.get_all_jobs()
                    existing_ids = {str(ej.get("Job ID")) for ej in existing}
                    
                    new_count = 0
                    for job in all_jobs:
                        j_dict = job.to_dict() if hasattr(job, 'to_dict') else job.copy()
                        if str(j_dict.get("id")) not in existing_ids:
                            j_dict["status"] = "new"
                            j_dict["score"] = "" # Explicitly empty for unscored
                            db.add_job(j_dict)
                            tracker.update_job(j_dict)
                            new_count += 1
                    status.update(label=f"✅ Saved {new_count} new unscored jobs! (Skipped {len(all_jobs)-new_count} duplicates)", state="complete")
                else:
                    def on_chunk(chunk):
                        status.write(f"💾 Saving chunk of {len(chunk)} scored jobs...")
                        job_obj_map = {str(j.id if hasattr(j, 'id') else j.get('id')).strip(): j for j in all_jobs}
                        to_save = []
                        for res in chunk:
                            jid = str(res.get("id", "")).strip()
                            orig = job_obj_map.get(jid)
                            if not orig: continue
                            j_dict = orig.to_dict() if hasattr(orig, 'to_dict') else orig.copy()
                            j_dict.update({"score": int(float(res.get("score", 0))), "matching_skills": res.get("matching_skills", []), "missing_skills": res.get("missing_skills", []), "recommendation": res.get("recommendation", "")})
                            if j_dict["score"] >= score_threshold: to_save.append(j_dict)
                        
                        if to_save:
                            deduper = Deduplicator()
                            existing = tracker.get_all_jobs()
                            clean, dups = deduper.find_duplicates(to_save, [{"id": ej.get("Job ID"), "title": ej.get("Role"), "company": ej.get("Company")} for ej in existing])
                            for j in clean + dups:
                                j["status"] = "new" if j in clean else "potential_duplicate"
                                db.add_job(j); tracker.update_job(j)

                    score_batch(resume_text, jobs_dicts, on_chunk_complete=on_chunk)
                    status.update(label=f"✅ Search complete! {len(all_jobs)} processed.", state="complete")
                status.update(label=f"✅ Search complete! {len(all_jobs)} processed.", state="complete")
            else:
                status.update(label="⚠️ No jobs found.", state="complete")

        except Exception as e:
            status.update(label=f"❌ Failed: {e}", state="error")
            st.exception(e)
