# Job Hunt Tool Core Module
from .scraper import BaseJobScraper, Job
from .ai import scorer, resume_tailor, ats_checker, contact_finder
from .apply import linkedin_apply, form_filler, apply_router
from .resume import parser, modifier, pdf_exporter
from .tracker import db
try:
    from .tracker import excel
except ImportError:
    excel = None

__all__ = [
    "BaseJobScraper",
    "Job",
    "scorer",
    "resume_tailor",
    "ats_checker",
    "contact_finder",
    "linkedin_apply",
    "form_filler",
    "apply_router",
    "parser",
    "modifier",
    "pdf_exporter",
    "db",
    "excel",
]
