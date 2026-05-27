"""Auto-select resume based on job type."""

from pathlib import Path
from typing import Optional

CONTRACT_PLATFORMS = {"uplers", "braintrust", "andela", "arc_dev", "mercor", "turing", "pro5"}
EU_PLATFORMS = {"relocateme", "thehub", "arbeitnow", "workinluxembourg"}
EU_COUNTRIES = ("Germany", "Netherlands", "Luxembourg", "France", "Denmark", "Norway",
                "Sweden", "Finland", "Switzerland", "UK", "Europe")

RESUME_TYPES = {
    "IN": "CV_Tarun_Gupta_IN.docx",
    "EU": "CV_Tarun_Gupta_EU.docx",
    "remote_contractual": "CV_Tarun_Gupta_remote_contractual.docx",
}

RESUME_DIR = Path("resume") / "To apply with"


def classify_job(job: dict) -> str:
    """Return 'IN', 'EU', or 'remote_contractual' for a job dict."""
    platform = str(job.get("Platform", job.get("platform", ""))).lower()
    location = str(job.get("Location", job.get("location", "")))

    if platform in CONTRACT_PLATFORMS:
        return "remote_contractual"

    if platform in EU_PLATFORMS:
        return "EU"

    if any(country.lower() in location.lower() for country in EU_COUNTRIES):
        return "EU"

    return "IN"


def pick_resume(job: dict) -> tuple[Optional[Path], str]:
    """
    Return (path, resume_type) for a job.
    path is None if the file doesn't exist.
    """
    resume_type = classify_job(job)
    filename = RESUME_TYPES[resume_type]
    path = RESUME_DIR / filename
    return (path if path.exists() else None, resume_type)


def get_all_resume_options() -> dict[str, Optional[Path]]:
    """Return all three resume paths keyed by type."""
    return {
        rtype: (RESUME_DIR / fname if (RESUME_DIR / fname).exists() else None)
        for rtype, fname in RESUME_TYPES.items()
    }
