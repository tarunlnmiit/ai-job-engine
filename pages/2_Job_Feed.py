"""Job feed with filtered view and scoring."""

import streamlit as st
import pandas as pd
from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style, safe_score
import os

st.set_page_config(page_title="Job Feed", page_icon="📋", layout="wide")
apply_custom_style()

st.title("📋 Your Personalized Job Feed")
st.markdown("##### *Curated opportunities prioritized by AI match scores.*")

# Load jobs from tracker
if not os.path.exists("data/jobs_tracker.csv"):
    st.info("No jobs found yet. Go to Search tab to find jobs.")
    st.stop()

tracker = CSVTracker()
jobs = tracker.get_all_jobs()

if not jobs:
    st.info("No jobs in tracker. Run a search first.")
    st.stop()

df = pd.DataFrame(jobs)

# --- Sidebar Filters ---
with st.sidebar:
    st.header("🔍 Refine Results")
    search_query = st.text_input("Search Role/Company", "")
    job_category = st.selectbox("Job Category", ["All", "India Fulltime", "EU Fulltime", "Remote Contractual"])
    min_score = st.slider("Min Match Score %", 0, 100, 40)
    
    statuses = ["new", "potential_duplicate", "applied", "manual_required", "interview", "rejected"]
    selected_statuses = st.multiselect("Status", options=statuses, default=["new", "potential_duplicate"])
    
    platforms = sorted(df["Platform"].unique().tolist()) if "Platform" in df.columns else []
    selected_platforms = st.multiselect("Platforms", options=platforms, default=platforms)

# --- Apply Filters ---
filtered_df = df.copy()

contract_plats = ["uplers", "braintrust", "andela", "arc_dev", "mercor", "turing", "pro5"]
eu_plats = ["relocateme", "thehub", "arbeitnow"]
eu_countries = "Germany|Netherlands|Luxembourg|France|Denmark|Norway|Sweden|Finland|Switzerland|UK|Europe"

if job_category == "Remote Contractual":
    filtered_df = filtered_df[filtered_df["Platform"].isin(contract_plats)]
elif job_category == "EU Fulltime":
    filtered_df = filtered_df[
        filtered_df["Platform"].isin(eu_plats) |
        filtered_df["Location"].str.contains(eu_countries, case=False, na=False)
    ]
elif job_category == "India Fulltime":
    filtered_df = filtered_df[
        ~filtered_df["Platform"].isin(contract_plats + eu_plats) &
        ~filtered_df["Location"].str.contains(eu_countries, case=False, na=False)
    ]

if search_query:
    filtered_df = filtered_df[filtered_df["Role"].str.contains(search_query, case=False, na=False) | filtered_df["Company"].str.contains(search_query, case=False, na=False)]
if selected_platforms:
    filtered_df = filtered_df[filtered_df["Platform"].isin(selected_platforms)]
if "Score (%)" in filtered_df.columns:
    filtered_df = filtered_df[pd.to_numeric(filtered_df["Score (%)"], errors="coerce").fillna(0) >= min_score]
if selected_statuses:
    filtered_df = filtered_df[filtered_df["Status"].isin(selected_statuses)]

# --- Layout ---
if filtered_df.empty:
    st.warning("No jobs match your current filters.")
    st.stop()

# Initialize selection
if "selected_job_id" not in st.session_state or st.session_state.selected_job_id not in filtered_df["Job ID"].values:
    st.session_state.selected_job_id = filtered_df.iloc[0]["Job ID"]

col_list, col_detail = st.columns([1, 2], gap="large")

with col_list:
    st.markdown(f"**Showing {len(filtered_df)} jobs**")
    sorted_df = filtered_df.sort_values("Score (%)", ascending=False)
    
    with st.container(height=800):
        for _, job in sorted_df.iterrows():
            jid = job["Job ID"]
            is_sel = st.session_state.selected_job_id == jid
            score = safe_score(job.get("Score (%)"))
            
            # Use custom badge class
            s_class = "score-high" if score >= 80 else ("score-medium" if score >= 60 else "score-low")
            
            # Card UI
            card_bg = "rgba(16, 113, 255, 0.1)" if is_sel else "rgba(255, 255, 255, 0.03)"
            card_border = "1px solid #1071ff" if is_sel else "1px solid rgba(255, 255, 255, 0.1)"
            
            st.markdown(f"""
            <div class="job-card" style="background: {card_bg}; border: {card_border};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div style="font-weight: 600; font-size: 1rem;">{job['Role']}</div>
                    <div class="score-badge {s_class}">{score}%</div>
                </div>
                <div style="font-size: 0.85rem; color: #aaa; margin-top: 5px;">{job['Company']}</div>
                <div style="font-size: 0.75rem; color: #888; margin-top: 2px;">{job['Location']} • {job['Platform']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("Review Details", key=f"btn_{jid}", width="stretch"):
                st.session_state.selected_job_id = jid
                st.rerun()

with col_detail:
    selected_row = filtered_df[filtered_df["Job ID"] == st.session_state.selected_job_id]
    if not selected_row.empty:
        job = selected_row.iloc[0]
        
        # Detail Header
        st.markdown(f"## {job['Role']}")
        st.markdown(f"#### {job['Company']}")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Match Score", f"{safe_score(job.get('Score (%)'))}%")
        m2.metric("Platform", job["Platform"])
        m3.metric("Status", job["Status"].upper())
        m4.metric("Location", job["Location"][:15] + ".." if len(job["Location"]) > 15 else job["Location"])
        
        st.divider()
        
        t1, t2, t3 = st.tabs(["📄 Description", "🤖 AI Insights", "📝 Notes & Actions"])
        
        with t1:
            if job.get("Application URL"):
                st.link_button("🌐 VIEW ORIGINAL LISTING", job["Application URL"], width="stretch")
            st.markdown("---")
            st.info(job.get("Description", "No snippet available."))
            
        with t2:
            c1, c2 = st.columns(2)
            with c1:
                st.success("✅ **Matching Skills**")
                st.write(job.get("Matching Skills", "N/A"))
            with c2:
                st.warning("⚠️ **Missing Skills**")
                st.write(job.get("Missing Skills", "N/A"))
            
            st.info(f"**AI Recommendation**: {job.get('Recommendation', 'Apply if role looks interesting.')}")
            
        with t3:
            st.text_area("Internal Notes", value=job.get("Notes", ""), key=f"note_{job['Job ID']}")
            st.markdown("---")
            a1, a2, a3 = st.columns(3)
            if a1.button("✅ MARK APPLIED", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "applied"})
                st.rerun()
            if a2.button("🚫 DISMISS", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "rejected"})
                st.rerun()
            if a3.button("🚩 REQUIRE MANUAL", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "manual_required"})
                st.rerun()
