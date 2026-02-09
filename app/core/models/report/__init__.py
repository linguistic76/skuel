"""
Report Domain Models
=====================

Unified domain for all user-submitted content:
- File submissions (transcripts, assignments, images, videos)
- Journal entries (voice, curated text) — merged February 2026
- Report Projects (LLM feedback instruction sets)
"""

from core.models.enums.report_enums import (
    AnalysisDepth,
    ContentStatus,
    ContentType,
    ContextEnrichmentLevel,
    FormattingStyle,
    JournalCategory,
    JournalType,
    ProcessorType,
    ReportStatus,
    ReportType,
)
from core.models.report.report import (
    Report,
    ReportDTO,
    report_dto_to_pure,
    report_pure_to_dto,
)
from core.models.report.report_converters import report_to_response
from core.models.report.report_project import (
    ReportProjectDTO,
    ReportProjectPure,
    create_report_project,
    report_project_dto_to_pure,
    report_project_pure_to_dto,
)
from core.models.report.report_project_request import (
    ReportFeedbackRequest,
    ReportProjectCreateRequest,
    ReportProjectUpdateRequest,
)
from core.models.report.report_schedule import (
    ReportDepth,
    ReportSchedule,
    ReportScheduleDTO,
    ScheduleType,
    schedule_dto_to_pure,
    schedule_pure_to_dto,
)

__all__ = [
    # Enums
    "AnalysisDepth",
    "ContentStatus",
    "ContentType",
    "ContextEnrichmentLevel",
    "FormattingStyle",
    "JournalCategory",
    "JournalType",
    "ProcessorType",
    "ReportStatus",
    "ReportType",
    # Domain models
    "Report",
    "ReportDTO",
    "report_dto_to_pure",
    "report_pure_to_dto",
    "report_to_response",
    # Report Projects
    "ReportProjectDTO",
    "ReportProjectPure",
    "create_report_project",
    "report_project_dto_to_pure",
    "report_project_pure_to_dto",
    # Report Project Requests
    "ReportFeedbackRequest",
    "ReportProjectCreateRequest",
    "ReportProjectUpdateRequest",
    # Report Schedule
    "ReportDepth",
    "ReportSchedule",
    "ReportScheduleDTO",
    "ScheduleType",
    "schedule_dto_to_pure",
    "schedule_pure_to_dto",
]
