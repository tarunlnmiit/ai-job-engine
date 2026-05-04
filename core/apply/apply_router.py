"""Route jobs to appropriate application method."""

from typing import Optional
from .linkedin_apply import LinkedInAutoApply
from .form_filler import FormFiller
from logger import get_logger

logger = get_logger("apply.router")


class ApplyRouter:
    """Route job applications to appropriate handler."""

    AUTO_APPLY_PLATFORMS = ["linkedin", "instahyre"]

    def __init__(self, linkedin_email: str, linkedin_password: str):
        self.linkedin_apply = LinkedInAutoApply(linkedin_email, linkedin_password)
        self.form_filler = FormFiller({})

    def should_auto_apply(self, job: dict) -> bool:
        """Determine if job should be auto-applied."""
        platform = job.get("platform", "").lower()
        is_easy_apply = job.get("is_easy_apply", False)
        return platform in self.AUTO_APPLY_PLATFORMS and is_easy_apply

    async def apply(self, job: dict) -> dict:
        """Route job application."""
        platform = job.get("platform", "").lower()
        url = job.get("application_url", "")
        title = job.get("title", "Unknown")

        logger.info("apply_router: '%s' | platform=%s | easy_apply=%s | url=%s",
                    title, platform, job.get("is_easy_apply"), url[:60])

        if not self.should_auto_apply(job):
            reason = f"No auto-apply for platform: {platform}"
            logger.info("Manual apply required: %s", reason)
            return {"status": "manual_required", "reason": reason}

        if platform == "linkedin":
            logger.info("Routing to LinkedIn auto-apply: %s", url[:60])
            result = await self.linkedin_apply.apply(url)
            logger.info("LinkedIn apply result: %s", result)
            return result
        elif platform == "instahyre":
            logger.info("Instahyre auto-apply not yet implemented — manual required")
            return {"status": "manual_required", "reason": "Instahyre auto-apply pending"}
        else:
            logger.warning("Unknown platform for auto-apply: %s", platform)
            return {"status": "manual_required", "reason": f"Unknown platform: {platform}"}
