"""Database view page showing all jobs from SQLite cache."""

import streamlit as st
import pandas as pd
from core.tracker.db import JobCache
import json

st.set_page_config(page_title="Database View", page_icon="🗄️", layout="wide")

st.header("🗄️ SQLite Database View")
st.markdown("View all jobs stored in the local SQLite cache (`data/jobs.db`).")

# Initialize database
db = JobCache()

# Load all jobs
jobs = db.get_all_jobs()

if not jobs:
    st.info("No jobs found in database cache. Run a search to populate it.")
    st.stop()

# Convert to DataFrame
df = pd.DataFrame(jobs)
if "score" in df.columns:
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)

# Summary metrics
col1, col2, col3 = st.columns(3)
col1.metric("Total Jobs in DB", len(df))
if "platform" in df.columns:
    col2.metric("Platforms", len(df["platform"].unique()))
if "score" in df.columns:
    avg_score = df["score"].mean()
    col3.metric("Avg Score", f"{avg_score:.1f}%")

st.divider()

# Filters
st.subheader("Filter Database")
f_col1, f_col2, f_col3 = st.columns(3)

platforms = db.get_unique_platforms()
sel_platforms = f_col1.multiselect("Platforms", platforms, default=platforms)

min_score = f_col2.slider("Min Score", 0, 100, 0)

search_term = f_col3.text_input("Search Title or Company", "")

# Apply filters
filtered_df = df.copy()
if sel_platforms:
    filtered_df = filtered_df[filtered_df["platform"].isin(sel_platforms)]

if "score" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["score"] >= min_score]

if search_term:
    filtered_df = filtered_df[
        filtered_df["title"].str.contains(search_term, case=False, na=False) |
        filtered_df["company"].str.contains(search_term, case=False, na=False)
    ]

st.markdown(f"**Showing {len(filtered_df)} jobs**")

# Field selection
st.subheader("Display Columns")
all_columns = df.columns.tolist()
default_columns = [col for col in ["date_found", "score", "title", "company", "location", "platform", "status"] if col in all_columns]
selected_columns = st.multiselect("Select Columns to Display", all_columns, default=default_columns)

# Display table
if selected_columns:
    # Sort and reset index so selection indices match row indices
    if "date_found" in filtered_df.columns:
        filtered_df = filtered_df.sort_values("date_found", ascending=False).reset_index(drop=True)
    else:
        filtered_df = filtered_df.reset_index(drop=True)

    selection = st.dataframe(
        filtered_df,
        column_order=selected_columns,
        hide_index=True,
        width="stretch",
        selection_mode="multi-row",
        on_select="rerun"
    )
    
    selected_rows = selection.selection.rows
    if selected_rows:
        st.write(f"**Selected {len(selected_rows)} jobs**")
        if st.button("🗑️ Delete Selected Rows", type="primary"):
            ids_to_delete = filtered_df.iloc[selected_rows]["id"].tolist()
            
            with st.spinner(f"Deleting {len(ids_to_delete)} jobs..."):
                from core.tracker.csv_tracker import CSVTracker
                tracker = CSVTracker()
                
                db_success = db.delete_jobs_by_ids(ids_to_delete)
                csv_success = tracker.delete_jobs_by_ids(ids_to_delete)
                
                if db_success and csv_success:
                    st.success(f"Successfully deleted {len(ids_to_delete)} jobs!")
                    st.rerun()
                else:
                    st.error("Partial or full failure in deletion. Check logs.")
else:
    st.warning("Please select at least one column to display.")

# Detailed View
if st.checkbox("Show Job Details"):
    selected_id = st.selectbox("Select Job to View", filtered_df["id"].tolist())
    if selected_id:
        job = next(j for j in jobs if j["id"] == selected_id)
        
        st.subheader(f"{job['title']} @ {job['company']}")
        
        d_col1, d_col2 = st.columns([2, 1])
        
        with d_col1:
            st.markdown(f"**Description Snippet:**")
            st.text(job.get("description", "No description")[:1000] + "...")
            
            st.markdown(f"**Skills Required:**")
            st.write(job.get("skills_required", []))
            
        with d_col2:
            st.metric("Score", f"{job.get('score', 0)}%")
            st.write("**Matching Skills:**", job.get("matching_skills", []))
            st.write("**Missing Skills:**", job.get("missing_skills", []))
            
            if job.get("application_url"):
                st.link_button("Apply Link", job["application_url"])

st.divider()

st.subheader("🧹 Maintenance")
m_col1, m_col2 = st.columns([2, 1])

with m_col1:
    clean_platform = st.selectbox("Select Platform to Clean", [""] + platforms)
    confirm_clean = st.checkbox(f"Confirm: Delete ALL jobs for {clean_platform if clean_platform else '...'} from DB and CSV Tracker")

if m_col2.button("🗑️ Clean Platform"):
    if not clean_platform:
        st.warning("Please select a platform first.")
    elif not confirm_clean:
        st.warning("Please confirm deletion by checking the box.")
    else:
        with st.spinner(f"Cleaning {clean_platform}..."):
            from core.tracker.csv_tracker import CSVTracker

            # Clean SQLite
            db_success = db.delete_jobs_by_platform(clean_platform)

            # Clean CSV
            tracker = CSVTracker()
            csv_success = tracker.delete_jobs_by_platform(clean_platform)

            if db_success and csv_success:
                st.success(f"Successfully cleaned all jobs for {clean_platform}!")
                st.rerun()
            else:
                st.error("Cleaning failed partially or fully. Check logs.")

st.divider()

confirm_clear_all = st.checkbox("I am sure I want to delete EVERY job from SQLite and CSV")
if st.button("🗑️ Clear ENTIRE Database (DANGEROUS)"):
    if not confirm_clear_all:
        st.warning("Please confirm deletion by checking the box.")
    else:
        with st.spinner("Clearing entire database..."):
            from core.tracker.csv_tracker import CSVTracker

            # Clear SQLite
            db_success = db.clear_all()

            # Clear CSV
            tracker = CSVTracker()
            csv_success = tracker.clear_all()

            if db_success and csv_success:
                st.success("Successfully cleared entire database!")
                st.rerun()
            else:
                st.error("Clearing failed partially or fully. Check logs.")
