import streamlit as st

def apply_custom_style():
    """Apply premium CSS to the Streamlit dashboard."""
    st.markdown("""
    <style>
        /* Modern Typography */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        
        h1, h2, h3, h4, h5, h6, p, span, label, .stMetric, .stButton {
            font-family: 'Inter', sans-serif;
        }

        /* Fix for expander overlap and icon text showing */
        [data-testid="stExpander"] summary {
            list-style: none;
        }
        [data-testid="stExpander"] summary::-webkit-details-marker {
            display: none;
        }
        [data-testid="stExpander"] summary:focus {
            outline: none;
        }
        [data-testid="stExpander"] summary div[role="button"] {
            display: flex !important;
            align-items: center !important;
            gap: 10px !important;
        }
        /* Custom Expander Title Styling */
        [data-testid="stExpander"] summary div[role="button"] p {
            font-size: 1.05rem;
            font-weight: 600;
            margin: 0 !important;
        }

        /* Glassmorphism Sidebar */
        [data-testid="stSidebar"] {
            background-color: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border-right: 1px solid rgba(255, 255, 255, 0.1);
        }

        /* Main Container Styling */
        .main {
            background: radial-gradient(circle at top right, #1a1c2c, #0d0e1a);
            color: #ffffff;
        }

        /* Custom Cards for Job Feed */
        .job-card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            transition: transform 0.2s, background 0.2s;
        }
        
        .job-card:hover {
            transform: translateY(-2px);
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.2);
        }

        /* Score Badge */
        .score-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.85rem;
            margin-bottom: 10px;
        }
        
        .score-high { background-color: #2ecc71; color: #fff; box-shadow: 0 0 10px rgba(46, 204, 113, 0.3); }
        .score-medium { background-color: #f1c40f; color: #000; }
        .score-low { background-color: #e74c3c; color: #fff; }

        /* Metric Styling */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem;
            font-weight: 700;
            color: #1071ff;
        }

        /* Status Containers */
        .stStatus {
            border-radius: 10px;
            background: rgba(16, 113, 255, 0.1);
            border-left: 5px solid #1071ff;
        }

        /* Buttons */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .stButton>button:hover {
            border-color: #1071ff;
            color: #1071ff;
            box-shadow: 0 0 15px rgba(16, 113, 255, 0.2);
        }

        /* Tabs Styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
            background: transparent;
        }
        
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            background-color: transparent;
            border-bottom: 2px solid transparent;
            color: #888;
            transition: all 0.3s;
        }
        
        .stTabs [data-baseweb="tab"]:hover {
            color: #1071ff;
        }
        
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            color: #1071ff;
            border-bottom-color: #1071ff;
        }

        /* Footer */
        .footer {
            text-align: center;
            padding: 20px;
            color: #555;
            font-size: 0.8rem;
        }
    </style>
    """, unsafe_allow_html=True)

def get_resume_path(mode="score", job_type="EU"):
    """
    Dynamically detect the resume path based on mode and job type.
    mode: "score" (Full Resumes) or "apply" (To apply with)
    job_type: "EU", "IN", or "remote_contractual"
    """
    from pathlib import Path
    
    # Map mode to folder
    folder_map = {
        "score": "Full Resumes",
        "apply": "To apply with"
    }
    subfolder = folder_map.get(mode, "Full Resumes")
    resume_dir = Path("resume") / subfolder
    
    if not resume_dir.exists():
        return None
        
    # Search for files matching the job_type in their name
    pattern = f"*{job_type}*"
    for ext in [".docx", ".pdf", ".txt"]:
        matches = list(resume_dir.glob(f"{pattern}{ext}"))
        if matches:
            # Prefer non-temp files if possible
            valid_matches = [m for m in matches if not m.name.startswith("~$")]
            if valid_matches:
                return str(valid_matches[0])
                
    # Fallback: if no specific match, try any resume in that folder
    for ext in [".docx", ".pdf", ".txt"]:
        match = list(resume_dir.glob(f"*{ext}"))
        if match:
            valid_matches = [m for m in match if not m.name.startswith("~$")]
            if valid_matches:
                return str(valid_matches[0])
                
    return None

def safe_score(score_val):
    """Safely convert score to integer, handling empty strings, floats, and None."""
    try:
        if score_val is None or str(score_val).strip() == "":
            return 0
        return int(float(str(score_val)))
    except (ValueError, TypeError):
        return 0

def inject_lottie_placeholder():
    """Placeholder for future Lottie animation integration."""
    pass
