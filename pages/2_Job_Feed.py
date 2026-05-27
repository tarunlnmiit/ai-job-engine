"""Job feed with filtered view and scoring."""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style, safe_score
import os

st.set_page_config(page_title="Job Feed", page_icon="📋", layout="wide")
apply_custom_style()

st.title("📋 Your Personalized Job Feed")
st.markdown("##### *Curated opportunities prioritized by AI match scores.*")

if not os.path.exists("data/jobs_tracker.csv"):
    st.info("No jobs found yet. Go to Search tab to find jobs.")
    st.stop()

tracker = CSVTracker()
jobs = tracker.get_all_jobs()

if not jobs:
    st.info("No jobs in tracker. Run a search first.")
    st.stop()

df = pd.DataFrame(jobs)

STATUS_COLORS = {
    "new": "#4a9eff",
    "shortlisted": "#f59e0b",
    "potential_duplicate": "#f0a500",
    "applied": "#22c55e",
    "manual_required": "#f59e0b",
    "interview": "#a855f7",
    "rejected": "#ef4444",
    "skipped": "#6b7280",
}

def normalize_location(loc: str) -> str:
    if not loc or not str(loc).strip():
        return "Unknown"
    s = str(loc).strip()
    if s.lower().startswith("applicant location allowed"):
        return "Remote (Worldwide)"
    return s

def days_ago(date_str: str) -> int:
    try:
        d = datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return -1

# Normalize location column for filtering
df["_loc_norm"] = df["Location"].apply(normalize_location)

# --- Summary Metrics ---
total = len(df)
new_count = len(df[df["Status"] == "new"])
applied_count = len(df[df["Status"] == "applied"])
manual_count = len(df[df["Status"] == "manual_required"])
interview_count = len(df[df["Status"] == "interview"])

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total", total)
m2.metric("New", new_count)
m3.metric("Applied", applied_count)
m4.metric("Manual Queue", manual_count)
m5.metric("Interview", interview_count)

st.divider()

# --- Sidebar Filters ---
with st.sidebar:
    st.header("🔍 Refine Results")
    search_query = st.text_input("Search Role/Company", "")

    job_category = st.selectbox("Job Category", ["All", "India Fulltime", "EU Fulltime", "Remote Contractual"])

    min_score = st.slider("Min Match Score %", 0, 100, 0)

    statuses = ["new", "shortlisted", "potential_duplicate", "applied", "manual_required", "interview", "rejected", "skipped"]
    selected_statuses = st.multiselect("Status", options=statuses, default=["new", "shortlisted", "potential_duplicate"])

    from core.tracker.db import JobCache
    db_cache = JobCache()
    platforms = db_cache.get_unique_platforms()
    selected_platforms = st.multiselect("Platforms", options=platforms, default=platforms)

    # Location filter — normalized values
    all_locs = sorted(df["_loc_norm"].dropna().unique().tolist())
    selected_locs = st.multiselect("Locations", options=all_locs, default=[])

    days_filter = st.selectbox("Posted Within", ["All time", "Last 1 day", "Last 3 days", "Last 7 days", "Last 14 days", "Last 30 days"])

    sort_by = st.selectbox("Sort By", ["Score (High→Low)", "Date Found (Newest)", "Date Found (Oldest)"])

    group_by_company = st.toggle("Group by Company", value=True)

# --- Apply Filters ---
contract_plats = ["uplers", "braintrust", "andela", "arc_dev", "mercor", "turing", "pro5"]
eu_plats = ["relocateme", "thehub", "arbeitnow", "WorkInLuxembourg"]
eu_countries = "Germany|Netherlands|Luxembourg|France|Denmark|Norway|Sweden|Finland|Switzerland|UK|Europe"

filtered_df = df.copy()

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
    filtered_df = filtered_df[
        filtered_df["Role"].str.contains(search_query, case=False, na=False) |
        filtered_df["Company"].str.contains(search_query, case=False, na=False)
    ]

if selected_platforms:
    filtered_df = filtered_df[filtered_df["Platform"].isin(selected_platforms)]

if "Score (%)" in filtered_df.columns:
    filtered_df = filtered_df[pd.to_numeric(filtered_df["Score (%)"], errors="coerce").fillna(0) >= min_score]

if selected_statuses:
    filtered_df = filtered_df[filtered_df["Status"].isin(selected_statuses)]

if selected_locs:
    filtered_df = filtered_df[filtered_df["_loc_norm"].isin(selected_locs)]

DAYS_FILTER_MAP = {
    "Last 1 day": 1,
    "Last 3 days": 3,
    "Last 7 days": 7,
    "Last 14 days": 14,
    "Last 30 days": 30,
}
if days_filter in DAYS_FILTER_MAP:
    max_days = DAYS_FILTER_MAP[days_filter]
    filtered_df = filtered_df[
        filtered_df["Date Found"].apply(lambda d: 0 <= days_ago(d) <= max_days)
    ]

# Sort
if sort_by == "Score (High→Low)":
    filtered_df = filtered_df.copy()
    filtered_df["_score_num"] = pd.to_numeric(filtered_df["Score (%)"], errors="coerce").fillna(0)
    filtered_df = filtered_df.sort_values("_score_num", ascending=False)
elif sort_by == "Date Found (Newest)":
    filtered_df = filtered_df.sort_values("Date Found", ascending=False)
elif sort_by == "Date Found (Oldest)":
    filtered_df = filtered_df.sort_values("Date Found", ascending=True)

# --- Layout ---
if filtered_df.empty:
    st.warning("No jobs match your current filters.")
    st.stop()

if "selected_job_id" not in st.session_state or st.session_state.selected_job_id not in filtered_df["Job ID"].values:
    st.session_state.selected_job_id = filtered_df.iloc[0]["Job ID"]

col_list, col_detail = st.columns([1, 2], gap="large")

with col_list:
    st.markdown(f"**Showing {len(filtered_df)} jobs**")

    # --- Bulk action bar (only in group-by-company mode) ---
    if group_by_company:
        selected_ids = [
            jid for jid in filtered_df["Job ID"].tolist()
            if st.session_state.get(f"sel_{jid}", False)
        ]
        if selected_ids:
            if st.button(f"⭐ Shortlist {len(selected_ids)} selected", key="bulk_shortlist"):
                for jid in selected_ids:
                    tracker.update_job({"id": jid, "status": "shortlisted"})
                for jid in filtered_df["Job ID"].tolist():
                    st.session_state[f"sel_{jid}"] = False
                st.success(f"Shortlisted {len(selected_ids)} jobs!")
                st.rerun()

    def render_job_card(job, show_checkbox: bool = False):
        jid = job["Job ID"]
        is_sel = st.session_state.selected_job_id == jid
        score = safe_score(job.get("Score (%)"))
        status = str(job.get("Status", "new")).lower()
        status_color = STATUS_COLORS.get(status, "#6b7280")

        s_class = "score-high" if score >= 80 else ("score-medium" if score >= 60 else "score-low")
        card_bg = "rgba(16, 113, 255, 0.1)" if is_sel else "rgba(255, 255, 255, 0.03)"
        card_border = "1px solid #1071ff" if is_sel else "1px solid rgba(255, 255, 255, 0.1)"

        age = days_ago(job.get("Date Found", ""))
        age_str = f"{age}d ago" if age >= 0 else ""

        loc_display = normalize_location(job.get("Location", ""))
        if len(loc_display) > 25:
            loc_display = loc_display[:22] + "..."

        if show_checkbox:
            col_check, col_card = st.columns([0.08, 1])
            with col_check:
                st.checkbox("", key=f"sel_{jid}", label_visibility="collapsed")
            with col_card:
                _render_card_html(job, jid, card_bg, card_border, score, s_class, status, status_color, loc_display, age_str)
        else:
            _render_card_html(job, jid, card_bg, card_border, score, s_class, status, status_color, loc_display, age_str)

    def _render_card_html(job, jid, card_bg, card_border, score, s_class, status, status_color, loc_display, age_str):
        st.markdown(f"""
        <div class="job-card" style="background: {card_bg}; border: {card_border};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div style="font-weight: 600; font-size: 1rem;">{job['Role']}</div>
                <div class="score-badge {s_class}">{score}%</div>
            </div>
            <div style="font-size: 0.85rem; color: #aaa; margin-top: 5px;">{job['Company']}</div>
            <div style="font-size: 0.75rem; color: #888; margin-top: 2px;">{loc_display} • {job['Platform']}</div>
            <div style="display: flex; justify-content: space-between; margin-top: 6px; align-items: center;">
                <span style="font-size: 0.7rem; color: {status_color}; font-weight: 600;">● {status.upper()}</span>
                <span style="font-size: 0.7rem; color: #666;">{age_str}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Review Details", key=f"btn_{jid}", width="stretch"):
            st.session_state.selected_job_id = jid
            st.rerun()

    with st.container(height=800):
        if group_by_company:
            for company, group_df in filtered_df.groupby("Company", sort=True):
                company_ids = group_df["Job ID"].tolist()

                # "Select All" checkbox for this company — set before rendering job checkboxes
                col_head, col_sel = st.columns([3, 1])
                with col_head:
                    st.markdown(
                        f"<div style='font-size:0.8rem; font-weight:700; color:#888; "
                        f"text-transform:uppercase; letter-spacing:0.08em; margin:12px 0 4px;'>"
                        f"{company} ({len(group_df)})</div>",
                        unsafe_allow_html=True,
                    )
                with col_sel:
                    all_checked = all(st.session_state.get(f"sel_{jid}", False) for jid in company_ids)
                    if st.checkbox("All", key=f"all_{company}", value=all_checked,
                                   label_visibility="visible"):
                        for jid in company_ids:
                            st.session_state[f"sel_{jid}"] = True
                    else:
                        # Only uncheck if the "all" box itself was just unchecked (was True before)
                        if all_checked:
                            for jid in company_ids:
                                st.session_state[f"sel_{jid}"] = False

                for _, job in group_df.iterrows():
                    render_job_card(job, show_checkbox=True)
        else:
            for _, job in filtered_df.iterrows():
                render_job_card(job, show_checkbox=False)

with col_detail:
    selected_row = filtered_df[filtered_df["Job ID"] == st.session_state.selected_job_id]
    if not selected_row.empty:
        job = selected_row.iloc[0]
        status = str(job.get("Status", "new")).lower()
        status_color = STATUS_COLORS.get(status, "#6b7280")

        st.markdown(f"## {job['Role']}")
        st.markdown(f"#### {job['Company']}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Match Score", f"{safe_score(job.get('Score (%)'))}%")
        m2.metric("Platform", job["Platform"])
        m3.metric("Location", normalize_location(job.get("Location", ""))[:20])
        age = days_ago(job.get("Date Found", ""))
        m4.metric("Found", f"{age}d ago" if age >= 0 else job.get("Date Found", ""))

        st.markdown(
            f"<span style='color:{status_color}; font-weight:700; font-size:1rem;'>● {status.upper()}</span>",
            unsafe_allow_html=True
        )

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
            notes_val = st.text_area("Internal Notes", value=job.get("Notes", ""), key=f"note_{job['Job ID']}")

            st.markdown("---")
            a1, a2, a3, a4, a5 = st.columns(5)

            if a1.button("⭐ SHORTLIST", key=f"shl_{job['Job ID']}", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "shortlisted", "notes": notes_val})
                st.success("Added to shortlist!")
                st.rerun()

            if a2.button("✅ APPLIED", key=f"app_{job['Job ID']}", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "applied", "notes": notes_val, "date_applied": date.today().strftime("%Y-%m-%d")})
                st.success("Marked applied!")
                st.rerun()

            if a3.button("🚩 MANUAL", key=f"man_{job['Job ID']}", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "manual_required", "notes": notes_val})
                st.success("Added to manual queue!")
                st.rerun()

            if a4.button("🎯 INTERVIEW", key=f"int_{job['Job ID']}", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "interview", "notes": notes_val})
                st.success("Marked interview!")
                st.rerun()

            if a5.button("🚫 DISMISS", key=f"dis_{job['Job ID']}", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "status": "rejected", "notes": notes_val})
                st.rerun()

            st.markdown("---")
            if st.button("💾 SAVE NOTES", key=f"save_{job['Job ID']}", width="stretch"):
                tracker.update_job({"id": job["Job ID"], "notes": notes_val})
                st.success("Notes saved!")
