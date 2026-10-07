"""Rendus d'un Rapport: HTML (source du PDF), PDF (Chromium headless), Word."""
from .docx import en_docx
from .html import en_html
from .pdf import ExportIndisponible, en_pdf

FORMATS = ("html", "pdf", "docx")
TYPES_MIME = {
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv; charset=utf-8",
}

__all__ = ["en_html", "en_pdf", "en_docx", "ExportIndisponible", "FORMATS", "TYPES_MIME"]
