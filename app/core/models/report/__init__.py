"""
Report Domain Models
=====================

File submission and processing pipeline models.

A Report represents any file submitted for processing:
- Transcripts (meeting notes, voice memos)
- Assignments (document processing)
- Images (visual analysis)
- Videos (content summarization)
"""

from core.models.report.report import (
    ProcessorType,
    Report,
    ReportDTO,
    ReportStatus,
    ReportType,
)
from core.models.report.report_converters import report_to_response

__all__ = [
    "Report",
    "ReportDTO",
    "ReportStatus",
    "ReportType",
    "ProcessorType",
    "report_to_response",
]
