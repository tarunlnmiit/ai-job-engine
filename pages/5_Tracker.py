"""Application tracker and analytics."""

import streamlit as st
import pandas as pd
from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style, safe_score
import os

st.set_page_config(page_title="Application Tracker", page_icon="📊", layout="wide")
apply_custom_style()

st.title("📊 Application Performance Tracker")
st.markdown("##### *Data-driven insights into your job search funnel.*")

# Load tracker
if not os.path.exists("data/jobs_tracker.csv"):
    st.info("No applications yet. Start by running a search.")
    st.stop()

tracker = CSVTracker()
jobs = tracker.get_all_jobs()

if not jobs:
    st.info("Tracker is empty.")
    st.stop()

df = pd.DataFrame(jobs)

# --- Summary Metrics ---
st.subheader("📈 Performance Overview")
m1, m2, m3, m4, m5 = st.columns(5)

try:
    total = len(df)
    applied = len(df[df["Status"] == "applied"])
    interviews = len(df[df["Status"] == "interview"])
    manual = len(df[df["Status"] == "manual_required"])
    avg_score = pd.to_numeric(df["Score (%)"], errors="coerce").mean() if "Score (%)" in df.columns else 0
    resp_rate = (interviews / max(applied, 1) * 100) if applied > 0 else 0

    m1.metric("Total Applied", applied)
    m2.metric("In Interview", interviews)
    m3.metric("Pending Tasks", manual)
    m4.metric("Avg Match", f"{avg_score:.0f}%")
    m5.metric("Response Rate", f"{resp_rate:.0f}%")
except Exception as e:
    st.error(f"Metric error: {e}")

st.divider()

# --- Visuals ---
col_v1, col_v2 = st.columns(2)

with col_v1:
    st.subheader("Distribution by Status")
    if "Status" in df.columns:
        status_counts = df["Status"].value_counts().reset_index()
        st.bar_chart(status_counts, x="Status", y="count", color="#1071ff")

with col_v2:
    st.subheader("Platform Distribution")
    if "Platform" in df.columns:
        plat_counts = df["Platform"].value_counts().reset_index()
        st.bar_chart(plat_counts, x="Platform", y="count", color="#2ecc71")

st.divider()

# --- Table ---
st.subheader("📋 Master Job List")
f1, f2 = st.columns(2)
with f1:
    stat_filter = st.selectbox("Filter Status", ["All"] + sorted(df["Status"].unique().tolist()))
with f2:
    plat_filter = st.selectbox("Filter Platform", ["All"] + sorted(df["Platform"].unique().tolist()))

display_df = df.copy()
if stat_filter != "All": display_df = display_df[display_df["Status"] == stat_filter]
if plat_filter != "All": display_df = display_df[display_df["Platform"] == plat_filter]

st.dataframe(display_df, width="stretch", height=400)

# --- Export ---
st.divider()
st.subheader("📥 Data Export")
e1, e2 = st.columns(2)
with e1:
    csv = df.to_csv(index=False)
    st.download_button("Download CSV Report", csv, "job_search_report.csv", "text/csv", width="stretch")
with e2:
    st.info("💡 **Pro-Tip**: Use the CSV export for your weekly progress tracking.")
