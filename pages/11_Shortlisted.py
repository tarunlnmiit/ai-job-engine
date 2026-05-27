"""Shortlisted jobs — tailor resume and apply with Chrome."""

import streamlit as st
import threading
import pandas as pd
from pathlib import Path
from datetime import date

from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style, safe_score
from core.resume.picker import get_all_resume_options, classify_job, RESUME_TYPES
from core.resume.docx_generator import generate_tailored_resume
from core.apply.chrome_apply import launch_and_stage

st.set_page_config(page_title="Shortlisted Jobs", page_icon="⭐", layout="wide")
apply_custom_style()

st.title("⭐ Shortlisted Jobs")
st.markdown("##### *Tailor your resume and apply with Chrome assistance.*")

tracker = CSVTracker()
all_jobs = tracker.get_all_jobs()
shortlisted = [
    j for j in all_jobs
    if j.get("Status") == "shortlisted"
    and j.get("Job ID", "").strip()
    and j.get("Role", "").strip()
]

if not shortlisted:
    st.info("No shortlisted jobs yet. Go to **Job Feed** and click ⭐ SHORTLIST on jobs you want to apply to.")
    st.stop()

# --- Metrics ---
m1, m2, m3 = st.columns(3)
m1.metric("Shortlisted", len(shortlisted))
m2.metric("With Description", sum(1 for j in shortlisted if len(str(j.get("Description", ""))) > 50))
m3.metric("High Score (≥80)", sum(1 for j in shortlisted if safe_score(j.get("Score (%)")) >= 80))

cols = ["Job ID", "Role", "Company", "Location", "Platform", "Score (%)", "Application URL", "Date Found"]
csv_cols = [c for c in cols if c in pd.DataFrame(shortlisted).columns]
csv_data = pd.DataFrame(shortlisted)[csv_cols].to_csv(index=False)
st.download_button("⬇️ Download Shortlisted CSV", csv_data, "shortlisted_jobs.csv", "text/csv")

st.divider()

# --- Session state for tailored resumes ---
if "tailored_paths" not in st.session_state:
    st.session_state.tailored_paths = {}

if "apply_results" not in st.session_state:
    st.session_state.apply_results = {}

RESUME_TYPE_LABELS = {
    "IN": "🇮🇳 India Resume",
    "EU": "🌍 EU/International Resume",
    "remote_contractual": "💼 Contractual Resume",
}

all_resume_options = get_all_resume_options()

# --- Sort by score ---
shortlisted_sorted = sorted(shortlisted, key=lambda j: safe_score(j.get("Score (%)")), reverse=True)

for job in shortlisted_sorted:
    jid = job["Job ID"]
    score = safe_score(job.get("Score (%)"))
    s_class = "score-high" if score >= 80 else ("score-medium" if score >= 60 else "score-low")
    description = str(job.get("Description", ""))
    has_description = len(description) > 50

    with st.expander(f"**{job['Role']}** @ {job['Company']}  ·  {score}%  ·  {job['Platform']}", expanded=False):

        col_info, col_actions = st.columns([2, 1], gap="large")

        with col_info:
            st.markdown(f"**Location:** {job.get('Location', 'N/A')}")
            st.markdown(f"**Match Score:** `{score}%`")
            if job.get("Matching Skills"):
                st.markdown(f"**Matching:** {job['Matching Skills']}")
            if job.get("Missing Skills"):
                st.markdown(f"**Missing:** {job['Missing Skills']}")
            if job.get("Application URL"):
                st.link_button("🔗 View Original Listing", job["Application URL"])
            if has_description:
                with st.expander("Job Description", expanded=False):
                    st.write(description[:2000] + ("..." if len(description) > 2000 else ""))
            else:
                st.warning("⚠️ No description available — resume tailoring may be generic.")

        with col_actions:
            # --- Resume picker ---
            auto_type = classify_job(job)
            resume_type_options = list(RESUME_TYPES.keys())
            default_idx = resume_type_options.index(auto_type)
            selected_type = st.selectbox(
                "Resume",
                options=resume_type_options,
                format_func=lambda t: RESUME_TYPE_LABELS[t],
                index=default_idx,
                key=f"rtype_{jid}",
            )
            base_resume_path = all_resume_options.get(selected_type)
            if base_resume_path:
                st.caption(f"📁 `{base_resume_path.name}`")
            else:
                st.error(f"Resume file not found: {RESUME_TYPES[selected_type]}")

            tailored_path = st.session_state.tailored_paths.get(jid)

            # --- Tailor Resume ---
            tailor_disabled = base_resume_path is None
            if st.button("✨ Tailor Resume", key=f"tailor_{jid}", disabled=tailor_disabled, width="stretch"):
                with st.status("Tailoring resume with AI…", expanded=True) as status:
                    st.write("Reading original resume…")
                    st.write("Sending to AI (Groq/OpenRouter)…")
                    out = generate_tailored_resume(
                        original_docx_path=base_resume_path,
                        job=job,
                    )
                    if out:
                        st.session_state.tailored_paths[jid] = out
                        tailored_path = out
                        status.update(label="✅ Resume tailored!", state="complete")
                    else:
                        status.update(label="❌ Tailoring failed — check AI API keys", state="error")

            # --- Download tailored ---
            if tailored_path and Path(tailored_path).exists():
                with open(tailored_path, "rb") as f:
                    st.download_button(
                        label="📥 Download Tailored Resume",
                        data=f,
                        file_name=Path(tailored_path).name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_{jid}",
                        width="stretch",
                    )
                st.caption(f"Tailored: `{Path(tailored_path).name}`")
            else:
                # Offer original as download fallback
                if base_resume_path and base_resume_path.exists():
                    with open(base_resume_path, "rb") as f:
                        st.download_button(
                            label="📥 Download Original Resume",
                            data=f,
                            file_name=base_resume_path.name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_orig_{jid}",
                            width="stretch",
                        )

            st.markdown("---")

            # --- Open in Chrome ---
            apply_resume = tailored_path or base_resume_path
            url = job.get("Application URL", "")
            chrome_disabled = not url

            if chrome_disabled:
                st.warning("No application URL — cannot open Chrome.")
            else:
                if st.button("🌐 Open in Chrome", key=f"chrome_{jid}", disabled=chrome_disabled, width="stretch"):
                    st.info("Opening Chrome… complete & submit in the browser window.")

                    result = {}

                    def _run_chrome():
                        result.update(launch_and_stage(
                            job_url=url,
                            resume_path=Path(apply_resume) if apply_resume else None,
                            job=job,
                        ))

                    t = threading.Thread(target=_run_chrome, daemon=True)
                    t.start()
                    t.join(timeout=35)

                    st.session_state.apply_results[jid] = result
                    st.rerun()

            # Show Chrome result if available
            chrome_result = st.session_state.apply_results.get(jid)
            if chrome_result:
                if chrome_result.get("status") == "staged":
                    staged = chrome_result.get("staged_fields", [])
                    st.success(f"Chrome opened. Staged: {', '.join(staged) if staged else 'URL only'}")
                    if chrome_result.get("resume_uploaded"):
                        st.caption("✅ Resume uploaded to form")
                elif chrome_result.get("status") == "failed":
                    st.error(f"Chrome error: {chrome_result.get('reason', 'unknown')}")

            st.markdown("---")

            # --- Status actions ---
            b1, b2 = st.columns(2)
            if b1.button("✅ Mark Applied", key=f"app_{jid}", width="stretch"):
                tracker.update_job({
                    "id": jid,
                    "status": "applied",
                    "date_applied": date.today().strftime("%Y-%m-%d"),
                })
                st.success("Marked as applied!")
                st.rerun()

            if b2.button("🚫 Remove", key=f"rm_{jid}", width="stretch"):
                tracker.update_job({"id": jid, "status": "new"})
                st.rerun()

st.divider()
st.markdown("<div style='text-align:center; color:#666; font-size:0.75rem;'>AI Job Engine • Shortlist & Apply</div>", unsafe_allow_html=True)
