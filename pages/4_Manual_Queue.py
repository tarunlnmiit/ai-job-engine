"""Manual application queue with contact finding."""

import streamlit as st
from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style, safe_score
import os

st.set_page_config(page_title="Manual Queue", page_icon="🚩", layout="wide")
apply_custom_style()

st.title("🚩 Manual Application Mission")
st.markdown("##### *Strategic outreach for high-value targets.*")

# Load real jobs from tracker with 'manual_required' status
tracker = CSVTracker()
all_jobs = tracker.get_all_jobs()
manual_queue = [j for j in all_jobs if j.get("Status") == "manual_required"]

if not manual_queue:
    st.info("Your manual queue is empty. Flag jobs in the Job Feed to see them here.")
    st.stop()

st.subheader(f"💼 High-Touch Targets ({len(manual_queue)})")

for job in manual_queue:
    score = safe_score(job.get("Score (%)"))
    
    with st.expander(f"{job['Role']} @ {job['Company']} ({score}%)"):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown(f"**Reason for Manual**: Requires custom portal or high-value referral.")
            st.markdown(f"**Platform:** {job['Platform']} | **Location:** {job['Location']}")
            if job.get("Application URL"):
                st.link_button("🌐 OPEN APPLICATION PORTAL", job["Application URL"], width="stretch")
            
        with col2:
            st.metric("Match Score", f"{score}%")
            
        st.divider()
        
        # Action Footer
        t_note = st.text_area("Outreach Notes", value=job.get("Notes", ""), key=f"note_{job['Job ID']}")
        
        c1, c2 = st.columns(2)
        if c1.button("✅ MARK AS SUBMITTED", key=f"sub_{job['Job ID']}", width="stretch"):
            tracker.update_job({"id": job["Job ID"], "status": "applied", "notes": t_note})
            st.rerun()
        if c2.button("💾 SAVE PROGRESS", key=f"save_{job['Job ID']}", width="stretch"):
            tracker.update_job({"id": job["Job ID"], "notes": t_note})
            st.success("Notes saved!")

st.divider()
st.markdown("<div class='footer'>AI Job Engine • Manual Outreach Support</div>", unsafe_allow_html=True)
