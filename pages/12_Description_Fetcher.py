"""Fetch missing job descriptions by visiting application URLs."""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from core.tracker.db import JobCache
from core.scraper.description_fetcher import fetch_description, _SKIP_PLATFORMS

st.set_page_config(page_title="Description Fetcher", page_icon="🔍", layout="wide")
st.title("🔍 Description Fetcher")
st.caption("Visits job URLs to fetch missing descriptions, then extracts them with Claude.")

db = JobCache()

include_perm_failed = st.sidebar.checkbox("Show permanently failed URLs", value=False)
include_no_desc = st.sidebar.checkbox("Show 'no description found' jobs", value=False)

all_flagged = db.get_jobs_without_description(include_perm_failed=True, include_no_desc=True)
all_clean = db.get_jobs_without_description(include_perm_failed=False, include_no_desc=False)
perm_failed_count = sum(1 for j in all_flagged if j.get("desc_fetch_error") == "perm_failed")
no_desc_count = sum(1 for j in all_flagged if j.get("desc_fetch_error") == "no_desc")

jobs = db.get_jobs_without_description(include_perm_failed=include_perm_failed, include_no_desc=include_no_desc)
fetchable = [j for j in jobs if j.get("application_url") and j["application_url"].startswith("http")]
skippable_count = sum(
    1 for j in fetchable
    if (j.get("platform") or "").lower() in _SKIP_PLATFORMS
)
actionable = [j for j in fetchable if (j.get("platform") or "").lower() not in _SKIP_PLATFORMS]

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Missing descriptions", len(all_clean))
col2.metric("Have URL", len(fetchable))
col3.metric("Skipped (login-wall)", skippable_count)
col4.metric("Actionable", len(actionable))
col5.metric("Perm. failed", perm_failed_count, help="404/410/403 — won't be retried")
col6.metric("No description", no_desc_count, help="Page loaded but no job description found")

if not actionable:
    st.info("No actionable jobs — all missing-description jobs either have no URL or are on login-walled platforms (LinkedIn, Naukri, Instahyre).")
    st.stop()

st.divider()

# --- Job selection table ---
st.subheader("Jobs to fetch")

PAGE_SIZE = 25
total_pages = max(1, (len(actionable) + PAGE_SIZE - 1) // PAGE_SIZE)

ctrl_left, ctrl_mid, ctrl_right = st.columns([1, 2, 1])
with ctrl_left:
    select_all = st.checkbox("Select all pages", value=False)
    select_page = st.checkbox("Select this page", value=False)
with ctrl_mid:
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1, label_visibility="collapsed")
    st.caption(f"Page {page} / {total_pages}  ({len(actionable)} jobs total)")

page_jobs = actionable[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
page_job_ids = {j["id"] for j in page_jobs}

# Build a simple selection UI
selected_ids = set()
cols = st.columns([0.5, 2, 2, 1.5, 4])
cols[0].write("**✓**")
cols[1].write("**Company**")
cols[2].write("**Role**")
cols[3].write("**Platform**")
cols[4].write("**URL**")

for j in page_jobs:
    default = select_all or select_page or st.session_state.get(f"sel_{j['id']}", False)
    c0, c1, c2, c3, c4 = st.columns([0.5, 2, 2, 1.5, 4])
    checked = c0.checkbox("Select", key=f"sel_{j['id']}", value=default, label_visibility="collapsed")
    c1.write(j.get("company", "—"))
    c2.write(j.get("title", "—"))
    c3.write(j.get("platform", "—"))
    c4.write(j.get("application_url", "")[:60] + ("…" if len(j.get("application_url", "")) > 60 else ""))
    if checked or select_all or select_page:
        selected_ids.add(j["id"])

# include any previously-checked jobs from other pages
for j in actionable:
    if j["id"] not in page_job_ids:
        if select_all or st.session_state.get(f"sel_{j['id']}", False):
            selected_ids.add(j["id"])

st.divider()

col_a, col_b = st.columns(2)
fetch_selected = col_a.button(
    f"Fetch selected ({len(selected_ids)})",
    disabled=len(selected_ids) == 0,
    type="primary",
)
fetch_all = col_b.button(f"Fetch all actionable ({len(actionable)})")

if fetch_selected or fetch_all:
    targets = (
        [j for j in actionable if j["id"] in selected_ids]
        if fetch_selected
        else actionable
    )

    st.subheader("Fetching…")
    progress = st.progress(0)
    log_area = st.empty()
    summary = {"ok": 0, "skipped": 0, "no_url": 0, "fetch_failed": 0, "perm_failed": 0, "extract_failed": 0}
    log_lines = []

    for i, job in enumerate(targets):
        progress.progress((i + 1) / len(targets))
        company = job.get("company", "?")
        role = job.get("title", "?")

        description, status = fetch_description(job)
        summary[status] = summary.get(status, 0) + 1

        if status == "ok" and description:
            db.update_description(job["id"], description)
            icon = "✅"
        elif status == "perm_failed":
            db.mark_desc_fetch_error(job["id"], "perm_failed")
            icon = "🚫"
        elif status == "no_desc":
            db.mark_desc_fetch_error(job["id"], "no_desc")
            icon = "🔇"
        elif status == "skipped":
            icon = "⏭️"
        elif status == "no_url":
            icon = "🔗"
        else:
            icon = "❌"

        log_lines.append(f"{icon} [{status}] {company} — {role}")
        log_area.text("\n".join(log_lines[-20:]))
        time.sleep(0.1)

    progress.progress(1.0)
    st.success(
        f"Done — ✅ {summary['ok']} fetched · "
        f"🚫 {summary.get('perm_failed', 0)} perm. failed · "
        f"🔇 {summary.get('no_desc', 0)} no description · "
        f"❌ {summary.get('fetch_failed', 0) + summary.get('extract_failed', 0)} transient failed · "
        f"⏭️ {summary.get('skipped', 0) + summary.get('no_url', 0)} skipped"
    )
    st.rerun()
