"""Generic form filling for applications."""

from typing import Optional


class FormFiller:
    """Generic form filling for job application portals."""

    def __init__(self, profile_data: dict):
        """Initialize with user profile data."""
        self.profile_data = profile_data

    async def fill_form(self, page, form_fields: list[dict]) -> bool:
        """
        Fill form fields with profile data.
        TODO: Implement Playwright form filling
        """
        return False

    async def upload_resume(self, page, resume_path: str) -> bool:
        """Upload resume to file input."""
        # TODO: Implement file upload
        return False

    async def handle_form_steps(self, page) -> dict:
        """Handle multi-step form navigation."""
        # TODO: Implement step navigation
        return {"status": "manual_required", "reason": "Form steps not implemented"}
