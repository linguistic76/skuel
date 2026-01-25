"""
Assignment Domain Models
========================

File submission and processing pipeline models.

An Assignment represents any file submitted for processing:
- Journals (daily diary entries)
- Transcripts (meeting notes, voice memos)
- Reports (document processing)
- Images (visual analysis)
- Videos (content summarization)
"""

from core.models.assignment.assignment import (
    Assignment,
    AssignmentDTO,
    AssignmentStatus,
    AssignmentType,
    ProcessorType,
)
from core.models.assignment.assignment_converters import assignment_to_response

__all__ = [
    "Assignment",
    "AssignmentDTO",
    "AssignmentStatus",
    "AssignmentType",
    "ProcessorType",
    "assignment_to_response",
]
