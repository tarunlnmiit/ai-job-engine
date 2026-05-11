import streamlit as st
import yaml
import os
from pathlib import Path
from datetime import datetime
import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from core.ui.style import apply_custom_style, safe_score

load_dotenv()

st.set_page_config(page_title="Europe Relocation", page_icon="🇪🇺", layout="wide")
apply_custom_style()

from core.ui.components import render_role_expander

st.title("🇪🇺 Europe Relocation Hub")
st.markdown("##### *Specialized engine for Indian professionals targeting EU markets.*")

# --- Global Role Expander ---
roles_text_val = render_role_expander(config_key="eu_roles_text")

# Load existing config for defaults
config_path = Path("config.yaml")
if config_path.exists():
    with open(config_path) as f:
        config = yaml.safe_load(f)
else:
    config = {}

# Sidebar for User Profile
with st.sidebar:
    st.header("👤 Your EU Profile")
    has_german_degree = st.toggle("Master's from German University", value=True)
    has_previous_blue_card = st.toggle("Previous EU Blue Card Holder", value=True)
    german_work_exp = st.number_input("Years of Work Exp in Germany", value=5.0, step=0.5)
    
    st.info("These settings will be used by the AI Scorer to prioritize German/EU opportunities.")
    
    st.divider()
    st.subheader("🌍 Official Portals")
    st.markdown("""
    - [Germany: Make it in Germany](https://www.make-it-in-germany.com/en/)
    - [Luxembourg: Work in Luxembourg](https://workinluxembourg.com)
    - [Denmark: Working in Denmark](https://denmark.dk/working-in-denmark)
    - [Norway: Info Norden](https://www.norden.org/en/info-norden/looking-work-norway)
    - [Switzerland: CH.ch Guide](https://www.ch.ch/en/foreign-nationals-in-switzerland/working-in-switzerland/)
    """)
    
    st.subheader("🛡️ Blue Card Toolkit")
    st.markdown("""
    - [Germany Tax Calculator](https://www.arbeitnow.com/tools/salary-calculator/germany)
    """)
    
    st.divider()
    st.subheader("⚙️ AI Engine Settings")
    nim_batch_size = st.slider(
        "NIM Batch Size",
        min_value=1,
        max_value=20,
        value=int(os.getenv("NIM_BATCH_SIZE", "5")),
        key="nim_batch_size_eu"
    )
    os.environ["NIM_BATCH_SIZE"] = str(nim_batch_size)

col_main, col_info = st.columns([2, 1])

with col_main:
    with st.form("europe_search"):
        st.subheader("🎯 Mission Parameters")
        
        c1, c2 = st.columns(2)
        with c1:
            roles_text = st.text_area(
                "Roles to search",
                value=st.session_state.get("eu_roles_text", "\n".join(config.get("search", {}).get("roles", ["Python Developer", "Software Engineer"]))),
                height=120,
                help="Use the AI Role Variant Generator above to expand this list."
            )
        with c2:
            countries = st.multiselect(
                "Target Countries",
                options=["Germany", "Netherlands", "Luxembourg", "France", "Denmark", "Norway", "Sweden", "Finland", "Switzerland"],
                default=["Germany", "Netherlands", "Luxembourg", "Denmark", "Norway"]
            )
            
        st.subheader("🌐 Specialized Platforms")
        platforms = st.multiselect(
            "Select Europe-focused portals",
            options=[
                "relocateme", "thehub", "arbeitnow", "workinluxembourg", "linkedin", "greenhouse", "lever", "wellfound"
            ],
            default=["relocateme", "thehub", "arbeitnow", "workinluxembourg", "linkedin"]
        )
        
        max_pages = st.number_input("Search Depth (Pages per country)", value=1, min_value=1, max_value=5)
        skip_scoring = st.checkbox("🚀 Save Only (Skip AI Scoring)", value=False, help="Fast mode: Scrape jobs now and score them later.")
        
        submitted = st.form_submit_button("🚀 INITIATE EUROPEAN MISSION", width="stretch")

with col_info:
    st.subheader("ℹ️ Relocation Logic")
    st.markdown("""
    - **Sponsorship First**: Focuses on `Relocate.me` and `Arbeitnow` for verified sponsorship.
    - **Context Injection**: Your Blue Card history is added to every AI scoring prompt.
    - **Nordic Focus**: `The Hub` is used for high-growth startups in Denmark and Norway.
    """)
    st.divider()
    st.warning("Ensure your resume explicitly mentions your German Master's to maximize match scores.")

if submitted:
    if not countries:
        st.error("Please select at least one country.")
        st.stop()

    with st.status("🌍 Orchestrating European Search...", expanded=True) as status:
        from core.scraper import (
            RelocateMeScraper, TheHubScraper, LinkedInScraper,
            GreenhouseScraper, LeverScraper, WellfoundScraper,
            ArbeitNowScraper, WorkInLuxembourgScraper
        )
        from core.tracker.db import JobCache
        from core.tracker.csv_tracker import CSVTracker
        from core.ai.scorer import score_batch_nim
        from core.resume.parser import ResumeParser

        scraper_map = {
            "relocateme": RelocateMeScraper, "thehub": TheHubScraper, "linkedin": LinkedInScraper,
            "greenhouse": GreenhouseScraper, "lever": LeverScraper, "wellfound": WellfoundScraper,
            "arbeitnow": ArbeitNowScraper, "workinluxembourg": WorkInLuxembourgScraper
        }

        from core.ui.style import get_resume_path
        resume_path = get_resume_path(mode="score", job_type="EU")

        if not resume_path:
            status.update(label="❌ EU Full Resume not found in 'resume/Full Resumes'!", state="error")
            st.stop()

        status.write(f"📄 Analyzing EU Full Resume: {os.path.basename(resume_path)}...")
        parser = ResumeParser()
        resume_text = parser.parse(str(resume_path))
        degree_type = "German Master's" if has_german_degree else "International"
        blue_card_type = "Yes" if has_previous_blue_card else "No"
        eu_context = f"\n\n[EU RELOCATION CONTEXT]\n- Degree: {degree_type}\n- Previous Blue Card: {blue_card_type}\n- German Work Exp: {german_work_exp} years\n"
        resume_text += eu_context

        db = JobCache()
        tracker = CSVTracker()
        csv_lock = threading.Lock()

        existing_ids = {str(ej.get("Job ID")) for ej in tracker.get_all_jobs()}
        roles = [r.strip() for r in roles_text.split("\n") if r.strip()]

        total_scraped = 0
        total_saved = 0
        scoring_futures = []

        def score_and_save(r_text, jobs_dicts):
            """Score a batch and write scores back to DB+CSV. Runs in thread."""
            results = score_batch_nim(r_text, jobs_dicts)
            job_map = {j["id"]: j for j in jobs_dicts}
            count = 0
            for res in results:
                jid = res.get("id")
                base = job_map.get(jid)
                if not base:
                    continue
                scored = {
                    **base,
                    "score": int(float(res.get("score", 0))),
                    "matching_skills": res.get("matching_skills", []),
                    "missing_skills": res.get("missing_skills", []),
                    "recommendation": res.get("recommendation", ""),
                }
                db.add_job(scored)
                with csv_lock:
                    tracker.update_job(scored)
                count += 1
            return count

        executor = ThreadPoolExecutor(max_workers=4) if not skip_scoring else None

        for platform in platforms:
            if platform not in scraper_map:
                continue
            scraper = scraper_map[platform]()
            for country in countries:
                for role in roles:
                    status.write(f"🔍 {platform}: {role} in {country}...")
                    try:
                        search_role = f"{role} sponsorship" if platform == "linkedin" else role
                        if inspect.iscoroutinefunction(scraper.search):
                            jobs = asyncio.run(scraper.search(role=search_role, location=country, max_pages=max_pages))
                        else:
                            jobs = scraper.search(role=search_role, location=country, max_pages=max_pages)

                        total_scraped += len(jobs)

                        # Save new jobs immediately — dedup by ID
                        new_jobs_dicts = []
                        for job in jobs:
                            if str(job.id) not in existing_ids:
                                j_dict = job.to_dict()
                                j_dict["status"] = "new"
                                j_dict["score"] = ""
                                db.add_job(j_dict)
                                with csv_lock:
                                    tracker.update_job(j_dict)
                                existing_ids.add(str(job.id))
                                new_jobs_dicts.append(j_dict)
                                total_saved += 1

                        if new_jobs_dicts:
                            status.write(f"  💾 {len(new_jobs_dicts)} new saved ({platform}/{country})")

                        # Submit batch for parallel scoring
                        if not skip_scoring and new_jobs_dicts and executor:
                            scoring_futures.append(executor.submit(score_and_save, resume_text, new_jobs_dicts))

                    except Exception as e:
                        status.write(f"⚠️ Error on {platform}/{country}: {e}")

        status.write(f"🔎 Scraping done — {total_saved} new jobs saved from {total_scraped} found. Waiting for scoring...")

        total_scored = 0
        if executor:
            executor.shutdown(wait=True)
            for future in scoring_futures:
                try:
                    total_scored += future.result()
                except Exception:
                    pass

        if skip_scoring:
            status.update(label=f"✅ Done! {total_saved} new jobs saved (score later in Batch Scorer).", state="complete")
        else:
            status.update(label=f"✅ Done! {total_saved} saved, {total_scored} scored.", state="complete")
