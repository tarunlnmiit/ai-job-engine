"""Export resumes to PDF format."""

from typing import Optional
import os


class PDFExporter:
    """Convert DOCX resumes to PDF."""

    def docx_to_pdf(self, docx_path: str, output_dir: str = "data") -> Optional[str]:
        """
        Convert DOCX to PDF.

        Requires python-docx and reportlab, or LibreOffice CLI.
        """
        if not os.path.exists(docx_path):
            return None

        try:
            # Try using libreoffice command line
            import subprocess
            output_pdf = docx_path.replace(".docx", ".pdf")

            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", output_dir, docx_path],
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0 and os.path.exists(output_pdf):
                return output_pdf
        except Exception as e:
            print(f"LibreOffice conversion failed: {e}")

        # Fallback: reportlab approach (limited formatting)
        return self._convert_with_reportlab(docx_path, output_dir)

    def _convert_with_reportlab(self, docx_path: str, output_dir: str) -> Optional[str]:
        """Fallback conversion using reportlab (basic formatting only)."""
        try:
            from docx import Document
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.units import inch

            doc = Document(docx_path)
            output_path = docx_path.replace(".docx", ".pdf")

            pdf = SimpleDocTemplate(output_path, pagesize=letter)
            story = []
            styles = getSampleStyleSheet()

            for para in doc.paragraphs:
                if para.text.strip():
                    story.append(Paragraph(para.text, styles["BodyText"]))
                    story.append(Spacer(1, 0.1 * inch))

            pdf.build(story)
            return output_path
        except Exception as e:
            print(f"ReportLab conversion failed: {e}")
            return None
