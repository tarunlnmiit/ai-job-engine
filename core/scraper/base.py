from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    description: str
    application_url: str
    platform: str
    salary: Optional[str] = None
    skills_required: list[str] = field(default_factory=list)
    experience_required: Optional[str] = None
    posted_date: Optional[datetime] = None
    is_remote: bool = False
    is_easy_apply: bool = False
    score: Optional[float] = None
    status: str = "new"
    contact_info: Optional[str] = None
    date_found: Optional[str] = None
    date_applied: Optional[str] = None
    matching_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    notes: Optional[str] = None
    linkedin_network_match: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary,
            "description": self.description,
            "skills_required": self.skills_required,
            "experience_required": self.experience_required,
            "posted_date": self.posted_date,
            "application_url": self.application_url,
            "platform": self.platform,
            "is_remote": self.is_remote,
            "is_easy_apply": self.is_easy_apply,
            "score": self.score,
            "status": self.status,
            "contact_info": self.contact_info,
            "date_found": self.date_found,
            "date_applied": self.date_applied,
            "matching_skills": self.matching_skills,
            "missing_skills": self.missing_skills,
            "notes": self.notes,
            "linkedin_network_match": self.linkedin_network_match,
        }


def group_jobs_by_company(jobs: list[dict]) -> dict[str, list[dict]]:
    """Group a list of job dicts by company name."""
    grouped: dict[str, list[dict]] = {}
    for job in jobs:
        company = job.get("company") or "Unknown"
        grouped.setdefault(company, []).append(job)
    return grouped


class BaseJobScraper:
    def search(self, role: str, location: str, max_pages: int = 1, **kwargs) -> list[Job]:
        """Search for jobs by role and location."""
        raise NotImplementedError
