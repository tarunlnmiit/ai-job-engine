"""Search configuration page."""

import streamlit as st
import yaml
import os
from pathlib import Path
from dotenv import load_dotenv
from core.ui.style import apply_custom_style, safe_score

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
                value=st.session_state.get("roles_text", ""),
                height=150,
                key="final_roles_list"
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

        st.subheader("🌐 Platforms")
        platforms = st.multiselect(
            "Scrapers to engage",
            options=[
                "linkedin", "naukri", "wellfound", "indeed_india",
                "greenhouse", "lever", "remotive", "weworkremotely", "instahyre", "hacker_news", "hirist", "arbeitnow"
            ],
            default=config.get("portals", ["linkedin", "naukri", "greenhouse", "lever", "hacker_news"])
        )

        st.subheader("⚙️ Execution Settings")
        e1, e2 = st.columns(2)
        with e1:
            max_pages = st.number_input("Depth (Pages per target)", value=config.get("search", {}).get("max_pages", 1), min_value=1, max_value=20)
        with e2:
            remote_ok = st.checkbox("Include Remote Global", value=config.get("search", {}).get("remote_ok", True))

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
                HackerNewsScraper, HiristScraper, ArbeitNowScraper
            )
            from datetime import datetime
            import asyncio, inspect

            from core.ui.style import get_resume_path
            resume_path = get_resume_path()
            status.write(f"📄 Analyzing {os.path.basename(resume_path)}...")
            parser = ResumeParser()
            
            if not resume_path:
                status.update(label="❌ No resume found!", state="error")
                st.stop()
            
            resume_text = parser.parse(str(resume_path))
            
            db = JobCache()
            tracker = CSVTracker()
            scraper_map = {
                "linkedin": LinkedInScraper, "naukri": NaukriScraper, "greenhouse": GreenhouseScraper,
                "lever": LeverScraper, "wellfound": WellfoundScraper, "indeed_india": IndeedScraper,
                "remotive": RemotiveScraper, "weworkremotely": WeWorkRemotely, "instahyre": InstahyreScraper,
                "hacker_news": HackerNewsScraper, "hirist": HiristScraper, "arbeitnow": ArbeitNowScraper
            }

            all_jobs = []
            for platform in platforms:
                if platform not in scraper_map: continue
                scraper = scraper_map[platform]()
                for role in search_config["search"]["roles"]:
                    for location in search_config["search"]["locations"]:
                        status.write(f"🔍 Searching {platform}: {role} in {location}...")
                        try:
                            if inspect.iscoroutinefunction(scraper.search):
                                jobs = asyncio.run(scraper.search(role=role, location=location, remote=remote_ok, max_pages=int(max_pages)))
                            else:
                                jobs = scraper.search(role=role, location=location, remote=remote_ok, max_pages=int(max_pages))
                            all_jobs.extend(jobs)
                        except Exception as e:
                            status.write(f"⚠️ Error on {platform}: {e}")

            if all_jobs:
                status.write(f"⭐ Found {len(all_jobs)} jobs. Commencing AI Scoring...")
                jobs_dicts = [j.to_dict() if hasattr(j, 'to_dict') else j for j in all_jobs]
                
                def on_chunk(chunk):
                    status.write(f"💾 Saving chunk of {len(chunk)} scored jobs...")
                    job_obj_map = {j.id if hasattr(j, 'id') else j.get('id'): j for j in all_jobs}
                    to_save = []
                    for res in chunk:
                        orig = job_obj_map.get(res.get("id"))
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
            else:
                status.update(label="⚠️ No jobs found.", state="complete")

        except Exception as e:
            status.update(label=f"❌ Failed: {e}", state="error")
            st.exception(e)
