"""
Journal Services
=================

Standalone service layer for the Journal domain (JE_INPUT + JE_OUTPUT).

Journal processing reuses shared LLM infrastructure (UnifiedLLMCaller,
InstructionResolver, OutputGeneratorOperations) but owns its own
service orchestration.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from core.services.journal.journal_input_service import JournalInputService
from core.services.journal.journal_output_service import JournalOutputService

__all__ = ["JournalInputService", "JournalOutputService"]
