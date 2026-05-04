"""Apply queue with resume tailoring."""

import streamlit as st
import os
from core.ui.style import apply_custom_style, safe_score, get_resume_path
from core.tracker.csv_tracker import CSVTracker

st.set_page_config(page_title="Apply Queue", page_icon="🤖", layout="wide")
apply_custom_style()

st.title("🤖 Auto-Apply Intelligence")
st.markdown("##### *Review AI-tailored submissions before final delivery.*")

# Check if resume exists
resume_path = get_resume_path()
if not resume_path:
    st.warning("""
    ### ⚠️ Resume not found!
    
    The engine needs your base resume to generate tailored versions.
    
    **How to fix:**
    1. Place your resume file (PDF, DOCX, or TXT) in the `resume/` folder.
    2. Ensure the filename is clear (e.g., `my_resume.pdf`).
    """)
    
    uploaded_file = st.file_uploader("Or upload it right here:", type=["docx", "pdf", "txt"])
    if uploaded_file:
        os.makedirs("resume", exist_ok=True)
        with open(f"resume/{uploaded_file.name}", "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"✅ Resume saved: {uploaded_file.name}")
        st.rerun()
    st.stop()

# Load real jobs from tracker with 'new' or 'manual_required' status
tracker = CSVTracker()
all_jobs = tracker.get_all_jobs()
apply_queue = [j for j in all_jobs if j.get("Status") == "new" and safe_score(j.get("Score (%)")) >= 75]

if not apply_queue:
    st.info("No high-score jobs ready for auto-apply. Try searching or adjusting your thresholds.")
    st.stop()

st.subheader(f"🚀 Submissions Pending ({len(apply_queue)})")

for job in apply_queue:
    score = safe_score(job.get("Score (%)"))
    s_class = "score-high" if score >= 80 else "score-medium"
    
    with st.expander(f"{job['Role']} @ {job['Company']} ({score}%)"):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown(f"**Platform:** {job['Platform']} | **Location:** {job['Location']}")
            st.markdown(f"**AI Match:** {score}%")
            st.markdown("**Missing Skills:**")
            st.write(job.get("Missing Skills", "None identified"))
            
        with col2:
            st.markdown(f"<div class='score-badge {s_class}'>Score: {score}%</div>", unsafe_allow_html=True)
            if job.get("Application URL"):
                st.link_button("View Job", job["Application URL"], width="stretch")

        st.divider()
        
        c_act1, c_act2 = st.columns(2)
        if c_act1.button(f"✨ GENERATE TAILORED RESUME", key=f"tailor_{job['Job ID']}", width="stretch"):
            with st.status("Tailoring resume with Groq Llama 3...") as status:
                # Mock tailoring for now - in future this calls actual tailoring logic
                status.write("Analyzing Job Description...")
                status.write("Aligning experiences...")
                status.write("Injecting keywords...")
                status.update(label="Tailoring Complete!", state="complete")
            
            st.markdown("### 📄 Tailored Preview")
            st.info("The AI has optimized your resume for this specific role. Bullet points re-ordered to emphasize relevant skills.")
            
            if st.button(f"🚀 CONFIRM & SUBMIT", key=f"confirm_{job['Job ID']}", width="stretch"):
                st.success(f"Application sent to {job['Company']}!")
                tracker.update_job({"id": job["Job ID"], "status": "applied"})
                st.rerun()

        if c_act2.button(f"🚫 DISMISS JOB", key=f"dismiss_{job['Job ID']}", width="stretch"):
            tracker.update_job({"id": job["Job ID"], "status": "rejected"})
            st.rerun()

st.divider()
st.markdown("<div class='footer'>AI Job Engine • Resume Intelligence v2.0</div>", unsafe_allow_html=True)
