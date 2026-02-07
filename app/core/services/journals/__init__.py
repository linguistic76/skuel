"""
Journals Service Package (Legacy)
==================================

NOTE: Journal domain merged into Reports (February 2026).
Journal entries are now Report nodes with report_type="journal".

Only JournalProjectService remains here — it's still used by
report_projects_api.py route file. Will be fully migrated to
core/services/reports/report_project_service.py.

For new code, use:
- ReportsCoreService.create_journal_report() for journal CRUD
- ReportProjectService for LLM project templates
- ReportFeedbackService for AI feedback generation
"""

from core.services.journals.journal_project_service import JournalProjectService

__all__ = [
    "JournalProjectService",
]
