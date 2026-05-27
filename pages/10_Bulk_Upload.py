"""Bulk upload jobs from Excel or CSV file."""

import io
import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime
from core.tracker.db import JobCache
from core.tracker.csv_tracker import CSVTracker
from core.ui.style import apply_custom_style

st.set_page_config(page_title="Bulk Upload", page_icon="📤", layout="wide")
apply_custom_style()

st.title("📤 Bulk Job Upload")
st.markdown("Upload jobs from Excel or CSV. Integrate with database + tracker.")

# Column mapping
REQUIRED_COLS = ["Company", "Role", "Location", "Application URL"]
OPTIONAL_COLS = [
    "Date Found", "Remote", "Salary", "Score (%)",
    "Matching Skills", "Missing Skills", "Status",
    "Contact Person", "Contact Email", "LinkedIn Network Match", "Notes", "Platform"
]

def generate_job_id(company: str, title: str, location: str) -> str:
    """Generate unique ID from company+title+location hash."""
    key = f"{company}_{title}_{location}".lower().strip()
    hash_val = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"manual_{hash_val}"

def parse_excel(file) -> tuple[pd.DataFrame, list]:
    """Parse Excel file, return df + validation errors."""
    errors = []

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return None, [f"Failed to read Excel: {str(e)}"]

    # Check required columns
    missing = [col for col in REQUIRED_COLS if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return None, errors

    # Strip whitespace
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    # Validate rows
    for idx, row in df.iterrows():
        if pd.isna(row["Company"]) or not str(row["Company"]).strip():
            errors.append(f"Row {idx+2}: Company empty")
        if pd.isna(row["Role"]) or not str(row["Role"]).strip():
            errors.append(f"Row {idx+2}: Role empty")
        if pd.isna(row["Location"]) or not str(row["Location"]).strip():
            errors.append(f"Row {idx+2}: Location empty")
        if pd.isna(row["Application URL"]) or not str(row["Application URL"]).strip():
            errors.append(f"Row {idx+2}: Application URL empty")

    if errors:
        return None, errors

    return df, []

VALID_STATUSES = {"new", "potential_duplicate", "applied", "manual_required", "interview", "rejected", "skipped"}

def _normalize_status(status: str) -> str:
    """Map Excel status values to valid internal statuses."""
    s = status.lower().strip()
    if s in VALID_STATUSES:
        return s
    if s in ("not applied", "not_applied", "todo", "pending", ""):
        return "new"
    if s in ("applied", "submitted"):
        return "applied"
    return "new"

def row_to_job(row: pd.Series, job_id: str) -> dict:
    """Convert Excel row to job dict for DB."""
    is_remote = False
    if pd.notna(row.get("Remote")):
        remote_val = str(row["Remote"]).lower().strip()
        is_remote = remote_val in ["yes", "y", "true", "1"]

    score = None
    if pd.notna(row.get("Score (%)")):
        try:
            score = float(row["Score (%)"])
        except:
            pass

    matching = ""
    if pd.notna(row.get("Matching Skills")):
        matching = str(row["Matching Skills"]).strip()

    missing = ""
    if pd.notna(row.get("Missing Skills")):
        missing = str(row["Missing Skills"]).strip()

    job = {
        "id": job_id,
        "title": str(row["Role"]).strip(),
        "company": str(row["Company"]).strip(),
        "location": str(row["Location"]).strip(),
        "application_url": str(row["Application URL"]).strip(),
        "platform": str(row.get("Platform", "manual")).strip() if pd.notna(row.get("Platform")) else "manual",
        "is_remote": is_remote,
        "salary": str(row.get("Salary", "")).strip() or None,
        "score": score,
        "status": _normalize_status(str(row.get("Status", "new")).strip()),
        "date_found": str(row.get("Date Found", "")).strip() or datetime.now().strftime("%Y-%m-%d"),
        "matching_skills": [s.strip() for s in matching.split(",") if s.strip()],
        "missing_skills": [s.strip() for s in missing.split(",") if s.strip()],
        "notes": str(row.get("Notes", "")).strip() or "",
        "contact_info": str(row.get("Contact Person", "")).strip() or "",
        "linkedin_network_match": str(row.get("LinkedIn Network Match", "")).strip() or "",
        "insert_ts": datetime.now().isoformat(),
    }
    return job

def _do_upload(jobs: list[dict]) -> None:
    """Upload a list of job dicts to DB + CSV tracker."""
    db = JobCache()
    tracker = CSVTracker()
    success_count = 0
    error_count = 0
    errors_list: list[str] = []

    with st.spinner(f"Uploading {len(jobs)} jobs..."):
        for job in jobs:
            existing = db.get_job(job["id"])
            if existing:
                st.warning(f"Job {job['id']} already exists. Skipping.")
                continue
            if db.add_job(job):
                success_count += 1
            else:
                error_count += 1
                errors_list.append(f"DB error for {job['id']}")
            try:
                tracker.update_job(job)
            except Exception as e:
                errors_list.append(f"CSV error for {job['id']}: {str(e)}")

    st.divider()
    if success_count > 0:
        st.success(f"✅ Successfully uploaded {success_count} jobs!")
    if error_count > 0:
        st.error(f"❌ {error_count} jobs failed to upload")
        for err in errors_list:
            st.write(f"  • {err}")
    st.info(f"**Summary:** {success_count} added | {error_count} failed")


def parse_csv(file) -> tuple[pd.DataFrame | None, list[str]]:
    """Parse CSV (tinyfish export format or generic). Returns df + errors."""
    errors: list[str] = []
    try:
        content = file.read().decode("utf-8")
        df = pd.read_csv(io.StringIO(content))
    except Exception as e:
        return None, [f"Failed to read CSV: {e}"]

    # Remap tinyfish export column names to expected schema
    tinyfish_map = {
        "Role": "Role",
        "Company": "Company",
        "Location": "Location",
        "Application URL": "Application URL",
        "Score (%)": "Score (%)",
        "Stack": "Matching Skills",
        "Worth Applying": "Notes",
    }
    df = df.rename(columns={k: v for k, v in tinyfish_map.items() if k in df.columns and k != v})

    # Require at minimum: Company, Role, Location, Application URL
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
        return None, errors

    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    for idx, row in df.iterrows():
        for col in REQUIRED_COLS:
            if pd.isna(row.get(col)) or not str(row.get(col, "")).strip():
                errors.append(f"Row {idx + 2}: {col} empty")

    if errors:
        return None, errors
    return df, []


# UI — tabbed
tab_excel, tab_csv = st.tabs(["📊 Excel Upload", "📄 CSV Upload"])

# ── Excel tab ──────────────────────────────────────────────────────────────
with tab_excel:
    st.subheader("Step 1: Upload Excel File")
    uploaded_file = st.file_uploader("Choose Excel file (.xlsx, .xls)", type=["xlsx", "xls"], key="excel_uploader")

    if uploaded_file:
        st.divider()
        st.subheader("Step 2: Validate & Preview")
        df, errors = parse_excel(uploaded_file)
        if errors:
            st.error("Validation errors found:")
            for err in errors:
                st.write(f"❌ {err}")
            st.stop()

        st.success(f"✅ Valid! {len(df)} rows to upload")
        with st.expander("Preview data", expanded=True):
            st.dataframe(df, use_container_width=True)

        st.divider()
        st.subheader("Step 3: Generate IDs & Review")
        jobs = [row_to_job(row, generate_job_id(row["Company"], row["Role"], row["Location"]))
                for _, row in df.iterrows()]

        preview_cols = ["id", "title", "company", "location", "score", "status"]
        with st.expander("Generated IDs & metadata", expanded=False):
            st.dataframe(
                pd.DataFrame([{k: j.get(k) for k in preview_cols} for j in jobs]),
                use_container_width=True,
            )

        st.divider()
        st.subheader("Step 4: Upload to Database")
        if st.button("✅ Upload All Jobs", type="primary", key="excel_upload_btn"):
            _do_upload(jobs)

# ── CSV tab ────────────────────────────────────────────────────────────────
with tab_csv:
    st.subheader("Step 1: Upload CSV File")
    st.caption("Accepts tinyfish `python main.py export` output or any CSV with Company, Role, Location, Application URL columns.")
    csv_file = st.file_uploader("Choose CSV file (.csv)", type=["csv"], key="csv_uploader")

    if csv_file:
        st.divider()
        st.subheader("Step 2: Validate & Preview")
        df_csv, csv_errors = parse_csv(csv_file)
        if csv_errors:
            st.error("Validation errors found:")
            for err in csv_errors:
                st.write(f"❌ {err}")
            st.stop()

        st.success(f"✅ Valid! {len(df_csv)} rows to upload")
        with st.expander("Preview data", expanded=True):
            st.dataframe(df_csv, use_container_width=True)

        st.divider()
        st.subheader("Step 3: Generate IDs & Review")
        csv_jobs = [row_to_job(row, generate_job_id(row["Company"], row["Role"], row["Location"]))
                    for _, row in df_csv.iterrows()]

        preview_cols = ["id", "title", "company", "location", "score", "status"]
        with st.expander("Generated IDs & metadata", expanded=False):
            st.dataframe(
                pd.DataFrame([{k: j.get(k) for k in preview_cols} for j in csv_jobs]),
                use_container_width=True,
            )

        st.divider()
        st.subheader("Step 4: Upload to Database")
        if st.button("✅ Upload All Jobs", type="primary", key="csv_upload_btn"):
            _do_upload(csv_jobs)

st.divider()
st.subheader("📋 Expected Format")

format_df = pd.DataFrame([
    {
        "Column": "Company",
        "Required": "✅",
        "Format": "Text",
        "Example": "TechCorp Inc"
    },
    {
        "Column": "Role",
        "Required": "✅",
        "Format": "Text",
        "Example": "Senior Backend Engineer"
    },
    {
        "Column": "Location",
        "Required": "✅",
        "Format": "Text",
        "Example": "San Francisco, CA"
    },
    {
        "Column": "Application URL",
        "Required": "✅",
        "Format": "URL",
        "Example": "https://example.com/jobs/123"
    },
    {
        "Column": "Date Found",
        "Required": "❌",
        "Format": "YYYY-MM-DD",
        "Example": "2026-05-22"
    },
    {
        "Column": "Remote",
        "Required": "❌",
        "Format": "Yes/No/True/False",
        "Example": "Yes"
    },
    {
        "Column": "Salary",
        "Required": "❌",
        "Format": "Text",
        "Example": "$100k-$130k"
    },
    {
        "Column": "Score (%)",
        "Required": "❌",
        "Format": "Number 0-100",
        "Example": "85"
    },
    {
        "Column": "Matching Skills",
        "Required": "❌",
        "Format": "CSV",
        "Example": "Python, AWS, Docker"
    },
    {
        "Column": "Missing Skills",
        "Required": "❌",
        "Format": "CSV",
        "Example": "Rust"
    },
    {
        "Column": "Status",
        "Required": "❌",
        "Format": "Text",
        "Example": "new"
    },
    {
        "Column": "Contact Person",
        "Required": "❌",
        "Format": "Text",
        "Example": "John Doe"
    },
    {
        "Column": "Contact Email",
        "Required": "❌",
        "Format": "Email",
        "Example": "john@example.com"
    },
    {
        "Column": "LinkedIn Network Match",
        "Required": "❌",
        "Format": "Text",
        "Example": "2nd degree"
    },
    {
        "Column": "Notes",
        "Required": "❌",
        "Format": "Text",
        "Example": "Found via Hacker News"
    },
])

st.dataframe(format_df, use_container_width=True, hide_index=True)

st.divider()
st.subheader("📄 Tinyfish CSV Export Columns")
st.caption("Columns produced by `python main.py export` in tinyfish_job_hunt_tool — upload directly in the CSV tab.")
tinyfish_fmt = pd.DataFrame([
    {"Column": "Company",         "Maps To": "Company",          "Required": "✅"},
    {"Column": "Role",            "Maps To": "Role",             "Required": "✅"},
    {"Column": "Location",        "Maps To": "Location",         "Required": "✅"},
    {"Column": "Application URL", "Maps To": "Application URL",  "Required": "✅"},
    {"Column": "Score (%)",       "Maps To": "Score (%)",        "Required": "❌"},
    {"Column": "Stack",           "Maps To": "Matching Skills",  "Required": "❌"},
    {"Column": "Region",          "Maps To": "(info only)",      "Required": "❌"},
    {"Column": "Reason",          "Maps To": "(ignored)",        "Required": "❌"},
    {"Column": "Worth Applying",  "Maps To": "Notes",            "Required": "❌"},
])
st.dataframe(tinyfish_fmt, use_container_width=True, hide_index=True)

st.divider()
st.markdown("<div class='footer'>AI Job Engine • Bulk Upload</div>", unsafe_allow_html=True)
