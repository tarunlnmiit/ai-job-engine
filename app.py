"""Job Hunt Automation Dashboard - Main App."""

import streamlit as st
from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style, safe_score
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Job Hunt Automation",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply premium styling
apply_custom_style()

st.title("🎯 Job Hunt Command Center")
st.markdown("##### *Your AI-powered engine for global career growth.*")

# Initialize session state
if "jobs_found" not in st.session_state:
    st.session_state.jobs_found = 0
if "auto_applied" not in st.session_state:
    st.session_state.auto_applied = 0
if "manual_queue" not in st.session_state:
    st.session_state.manual_queue = 0
if "avg_score" not in st.session_state:
    st.session_state.avg_score = 0

# Load tracker to get stats
interview_count = 0
if os.path.exists("data/jobs_tracker.csv"):
    tracker = CSVTracker()
    jobs = tracker.get_all_jobs()

    if jobs:
        total_jobs = len(jobs)
        applied_count = len([j for j in jobs if j.get("Status") == "applied"])
        manual_count = len([j for j in jobs if j.get("Status") == "manual_required"])
        interview_count = len([j for j in jobs if j.get("Status") == "interview"])

        scores = [safe_score(j.get("Score (%)")) for j in jobs if j.get("Score (%)")]

        avg_score = sum(scores) / len(scores) if scores else 0

        st.session_state.jobs_found = total_jobs
        st.session_state.auto_applied = applied_count
        st.session_state.manual_queue = manual_count
        st.session_state.avg_score = avg_score

# Summary Section
st.markdown("### 📊 Key Performance Metrics")
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)

with m_col1:
    st.metric("🔍 Total Scraped", st.session_state.jobs_found)
with m_col2:
    st.metric("✅ Applied", st.session_state.auto_applied)
with m_col3:
    st.metric("📝 Pending", st.session_state.manual_queue)
with m_col4:
    st.metric("⭐ Avg Score", f"{st.session_state.avg_score:.0f}%")
with m_col5:
    st.metric("💼 Interviews", interview_count)

st.divider()

# Interactive Section
col_l, col_r = st.columns([2, 1])

with col_l:
    st.markdown("### 🗺️ System Overview")
    
    # Progress overview (Mocked or pulled from last search)
    st.info("💡 **Tip**: Navigate to the **Search** tab to trigger a fresh scan across 12 platforms.")
    
    tabs = st.tabs(["🚀 Quick Start", "📈 Application Funnel", "🛠️ Tooling"])
    
    with tabs[0]:
        st.markdown("""
        1. **Config**: Set your target roles in `config.yaml` or via the **Search** tab.
        2. **Search**: Trigger AI-powered scrapers.
        3. **Review**: Check the **Job Feed** for your best matches (>75% recommended).
        4. **Apply**: Use the **Apply Queue** for one-click tailored submissions.
        """)
        
    with tabs[1]:
        import pandas as pd
        if os.path.exists("data/jobs_tracker.csv"):
            df = pd.read_csv("data/jobs_tracker.csv")
            if not df.empty and "Status" in df.columns:
                status_counts = df["Status"].value_counts().reset_index()
                st.bar_chart(status_counts, x="Status", y="count", color="#1071ff")
            else:
                st.write("No application data yet.")
        else:
            st.write("Start searching to see your funnel!")

    with tabs[2]:
        st.markdown("""
        - **LLM**: Gemini 1.5 Flash (Primary Scorer)
        - **Scrapers**: 12 Platforms (LinkedIn, Hirist, ArbeitNow, etc.)
        - **Browser**: Playwright CDP (Persistent Session)
        - **Storage**: SQLite (Cache) + CSV (Tracking)
        """)

with col_r:
    st.markdown("### 🔔 Activity Log")
    log_container = st.container(height=300)
    if os.path.exists("data/jobs_tracker.csv"):
        # Show last 5 activity items
        df = pd.read_csv("data/jobs_tracker.csv")
        if not df.empty:
            last_5 = df.tail(5)
            for _, row in last_5.iterrows():
                log_container.write(f"🔹 **{row.get('Company', 'N/A')}**: {row.get('Role', 'N/A')} (Score: {row.get('Score (%)', '0')}%)")
        else:
            log_container.write("No recent activity.")
    else:
        log_container.write("Waiting for first search...")

st.markdown("---")
st.markdown("<div class='footer'>AI Job Engine v2.0 • Powered by Google DeepMind Agentic Coding</div>", unsafe_allow_html=True)
