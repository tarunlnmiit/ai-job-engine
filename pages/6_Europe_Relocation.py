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
    german_work_exp = st.number_input("Years of Work Exp in Germany", value=2.0, step=0.5)
    
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
    - [ArbeitNow Blue Card Guide](https://www.arbeitnow.com/blog/blue-card-germany)
    - [Germany Tax Calculator](https://www.arbeitnow.com/tools/salary-calculator/germany)
    """)

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
                "relocateme", "thehub", "arbeitnow", "linkedin", "greenhouse", "lever", "wellfound"
            ],
            default=["relocateme", "thehub", "arbeitnow", "linkedin"]
        )
        
        max_pages = st.number_input("Search Depth (Pages per country)", value=1, min_value=1, max_value=5)
        
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
            ArbeitNowScraper
        )
        from core.tracker.db import JobCache
        from core.tracker.csv_tracker import CSVTracker
        from core.ai.scorer import score_batch
        from core.resume.parser import ResumeParser
        
        scraper_map = {
            "relocateme": RelocateMeScraper, "thehub": TheHubScraper, "linkedin": LinkedInScraper,
            "greenhouse": GreenhouseScraper, "lever": LeverScraper, "wellfound": WellfoundScraper,
            "arbeitnow": ArbeitNowScraper
        }
        
        from core.ui.style import get_resume_path
        # Europe page uses EU resume for scoring
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
        
        all_jobs = []
        roles = [r.strip() for r in roles_text.split("\n") if r.strip()]
        
        for platform in platforms:
            if platform not in scraper_map: continue
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
                        all_jobs.extend(jobs)
                    except Exception as e:
                        status.write(f"⚠️ Error on {platform}: {e}")
        
        if all_jobs:
            status.write(f"⭐ Found {len(all_jobs)} jobs. Commencing AI Scoring...")
            jobs_dicts = [j.to_dict() for j in all_jobs]
            db = JobCache(); tracker = CSVTracker()
            
            def on_save(results):
                job_obj_map = {j.id: j for j in all_jobs}
                for res in results:
                    orig = job_obj_map.get(res["id"])
                    if not orig: continue
                    j_dict = orig.to_dict()
                    j_dict.update({"score": int(float(res.get("score", 0))), "matching_skills": res.get("matching_skills", []), "missing_skills": res.get("missing_skills", []), "recommendation": res.get("recommendation", "")})
                    db.add_job(j_dict); tracker.update_job(j_dict)
            
            score_batch(resume_text, jobs_dicts, on_chunk_complete=on_save)
            status.update(label=f"✅ Mission Complete! {len(all_jobs)} jobs processed.", state="complete")
        else:
            status.update(label="⚠️ No jobs found.", state="complete")
