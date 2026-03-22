"""
Journal Domain Models
=====================

Standalone domain models for journal entries — user-initiated reflective practice.

Journal is NOT a submission (no authority receives it) and its processed form
is NOT a report (transformation, not interpretation — the user remains sole interpreter).

Two entity types:
    JE_INPUT  → Raw user content (audio or text). Deepgram transcribes audio→text,
                but both forms are still je_input.
    JE_OUTPUT → LLM-processed transformation of a je_input text file.

Pipeline: JE_INPUT(audio) → Deepgram → JE_INPUT(text) → LLM → JE_OUTPUT

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from core.models.journal.je_input import JeInput
from core.models.journal.je_input_dto import JeInputDTO
from core.models.journal.je_output import JeOutput
from core.models.journal.je_output_dto import JeOutputDTO

__all__ = [
    "JeInput",
    "JeInputDTO",
    "JeOutput",
    "JeOutputDTO",
]
