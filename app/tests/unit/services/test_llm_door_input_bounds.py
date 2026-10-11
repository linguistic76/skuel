"""User-written documents reach an LLM prompt bounded, door by door.

The journal stages, the journal batch compile, an entry's LLM processing, the
two EntryReport doors, the DSL bridge, the LifePath vision reader and the
transcript editor each build their own prompt from text a user wrote — a note,
a stage output the client posts back, a conversation so far, an entry's
content or instructions. None of it passes a request model with a cap, so each
door bounds it where it enters the prompt: ``PromptInput.DOCUMENT_MAX_CHARS``
per document (``PromptInput.FIELD_MAX_CHARS`` for the vision statement, a
field), through ``truncate_to_budget``.

Every case runs the door twice — once with short text, once with 50 000
characters in every user-written slot — and reads the prompt the provider
port receives. The long prompt is at most the short one plus one budget per
slot, keeps the short prompt's instruction tail, and never carries the
over-long text whole.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.constants import PromptInput
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_enums import JournalMode
from core.models.exercises.exercise import Exercise
from core.models.user_entry.user_entry import UserEntry
from core.ports.llm_protocols import LLMCompletion
from core.services.content_enrichment_service import ContentEnrichmentService
from core.services.dsl.llm_dsl_bridge import LLMDSLBridgeService
from core.services.journal.instruction_loader import journal_mode_addendum
from core.services.journal.journal_batch_service import JournalBatchService
from core.services.journal.journal_service import JournalService
from core.services.lifepath.lifepath_vision_service import LifePathVisionService
from core.services.llm_caller import UnifiedLLMCaller
from core.services.llm_service import LLMConfig, LLMProvider, LLMService
from core.services.output.instruction_resolver import InstructionResolver
from core.services.report.entry_report_service import AdmittedReport, EntryReportService
from core.services.user_entry.user_entry_processing_service import UserEntryProcessingService
from core.utils.result_simplified import Errors, Result
from tests.fixtures.llm_doubles import ScriptedChatCaller

#: Far over every bound; words and sentences, so the cut has boundaries to find.
LONG_TEXT = ("A sentence of ordinary words that runs on. " * 1200)[:50_000]
SHORT_TEXT = "A short note about the morning walk."
USER = "user_bounds"
#: A vault with no exemplar folders, so the batch compile reads no settings and no files.
_NO_VAULT = Path(__file__).parent / "_no_vault_here"


def _port() -> ScriptedChatCaller:
    return ScriptedChatCaller(Result.ok(LLMCompletion(text="An answer.", model="gpt-4o-mini")))


def _sent(port: ScriptedChatCaller) -> str:
    assert len(port.calls) == 1, f"the door made {len(port.calls)} LLM calls, not one"
    return str(port.calls[0][-1]["content"])


class _VaultNotes:
    """The one ``UserEntryService`` read the journal grounding makes."""

    async def get_vault_notes_for_context(self, user_uid: str) -> Result[list[dict[str, str]]]:
        return Result.ok([])


def _journal(port: ScriptedChatCaller) -> JournalService:
    caller = UnifiedLLMCaller(openai=port, anthropic=port)
    return JournalService(llm_caller=caller, user_entry_service=_VaultNotes())


#: A door: given the provider port and the user text for every slot, run it once.
Door = Callable[[ScriptedChatCaller, str], Awaitable[object]]


async def _stage1(port: ScriptedChatCaller, text: str) -> object:
    return await _journal(port).run_stage1(text, USER)


async def _stage2(port: ScriptedChatCaller, text: str) -> object:
    return await _journal(port).run_stage2(text, text, text, USER)


async def _stage3(port: ScriptedChatCaller, text: str) -> object:
    return await _journal(port).run_stage3(text, text, text, USER)


async def _discussion(port: ScriptedChatCaller, text: str) -> object:
    return await _journal(port).run_discussion(text, USER)


async def _follow_up(port: ScriptedChatCaller, text: str) -> object:
    return await _journal(port).run_follow_up(text, text, text, USER)


async def _batch_compile(port: ScriptedChatCaller, text: str) -> object:
    batch = JournalBatchService(
        llm_caller=UnifiedLLMCaller(openai=port, anthropic=port), vault_root=_NO_VAULT
    )
    return await batch.compile_text(text, text, user_uid=USER, is_founder=False)


async def _entry_llm_summary(
    port: ScriptedChatCaller, text: str, journal_mode: str | None = None
) -> object:
    not_under_test: Result[object] = Result.fail(Errors.system("not under test"))
    entry_service = MagicMock()
    entry_service.update_processed_content = AsyncMock(return_value=not_under_test)
    entry_service.update_processing_state = AsyncMock(return_value=not_under_test)
    service = UserEntryProcessingService(
        entry_service=entry_service,
        llm_caller=UnifiedLLMCaller(openai=port, anthropic=port),
        instruction_resolver=InstructionResolver(),
    )
    entry = UserEntry(
        uid="ue_bounds",
        title="Bounds",
        user_uid=USER,
        content=text,
        instructions=text,
        pipeline=Pipeline.LLM_SUMMARY,
        journal_mode=journal_mode,
    )
    return await service.process(entry)


async def _entry_report(port: ScriptedChatCaller, text: str) -> object:
    service = EntryReportService(llm_caller=UnifiedLLMCaller(openai=port, anthropic=port))
    exercise = Exercise(
        uid="ex_bounds", title="Reflect", instructions="Respond to the entry.", model="gpt-4o-mini"
    )
    entry = UserEntry(uid="ue_bounds", title="Bounds", user_uid=USER, content=text)
    return await service.generate_report(
        AdmittedReport(entry=entry, exercise=exercise, caller_uid=USER)
    )


async def _entry_response(port: ScriptedChatCaller, text: str) -> object:
    entry = UserEntry(
        uid="ue_bounds",
        title="Bounds",
        user_uid=USER,
        content=text,
        pipeline=Pipeline.EXTRACT_ACTIVITIES,
    )
    entry_service = MagicMock()
    entry_service.get_entry = AsyncMock(return_value=Result.ok(entry))
    backend = MagicMock()
    backend.create_report_node = AsyncMock(
        return_value=Result.fail(Errors.system("not under test"))
    )
    service = EntryReportService(
        llm_caller=UnifiedLLMCaller(openai=port, anthropic=port),
        backend=backend,
        entry_service=entry_service,
    )
    return await service.generate_entry_response("ue_bounds", USER)


async def _dsl_transform(port: ScriptedChatCaller, text: str) -> object:
    return await LLMDSLBridgeService(chat_port=port).transform(text, USER)


async def _vision(port: ScriptedChatCaller, text: str) -> object:
    llm = LLMService(
        config=LLMConfig(provider=LLMProvider.OPENAI, model_name="gpt-4o-mini"), caller=port
    )
    return await LifePathVisionService(llm_service=llm).capture_vision(USER, text)


#: door → (the door, how many user-written slots its prompt carries, the bound per slot)
DOORS: dict[str, tuple[Door, int, int]] = {
    "journal.run_stage1": (_stage1, 1, PromptInput.DOCUMENT_MAX_CHARS),
    "journal.run_stage2": (_stage2, 3, PromptInput.DOCUMENT_MAX_CHARS),
    "journal.run_stage3": (_stage3, 3, PromptInput.DOCUMENT_MAX_CHARS),
    "journal.run_discussion": (_discussion, 1, PromptInput.DOCUMENT_MAX_CHARS),
    "journal.run_follow_up": (_follow_up, 3, PromptInput.DOCUMENT_MAX_CHARS),
    "journal_batch.compile_text": (_batch_compile, 2, PromptInput.DOCUMENT_MAX_CHARS),
    "user_entry_processing.llm_summary": (_entry_llm_summary, 2, PromptInput.DOCUMENT_MAX_CHARS),
    "entry_report.generate_report": (_entry_report, 1, PromptInput.DOCUMENT_MAX_CHARS),
    "entry_report.generate_entry_response": (_entry_response, 1, PromptInput.DOCUMENT_MAX_CHARS),
    "dsl_bridge.transform": (_dsl_transform, 1, PromptInput.DOCUMENT_MAX_CHARS),
    "lifepath_vision.capture_vision": (_vision, 1, PromptInput.FIELD_MAX_CHARS),
}


@pytest.mark.parametrize("name", list(DOORS))
@pytest.mark.asyncio
async def test_a_door_bounds_every_user_written_slot(name: str) -> None:
    door, slots, bound = DOORS[name]
    short_port, long_port = _port(), _port()

    await door(short_port, SHORT_TEXT)
    await door(long_port, LONG_TEXT)
    short_prompt, long_prompt = _sent(short_port), _sent(long_port)

    assert SHORT_TEXT in short_prompt, "the control's text never reached the prompt"
    assert LONG_TEXT not in long_prompt
    assert len(long_prompt) <= len(short_prompt) + slots * bound
    tail = short_prompt.rsplit(SHORT_TEXT, 1)[-1]
    assert long_prompt.endswith(tail), "the instructions after the text were cut"


@pytest.mark.asyncio
async def test_long_entry_instructions_keep_the_response_mode() -> None:
    """The mode the user chose is appended after the bound, so the cut never takes it."""
    port = _port()

    await _entry_llm_summary(port, LONG_TEXT, journal_mode=JournalMode.SCRIBE.value)

    prompt = _sent(port)
    assert LONG_TEXT not in prompt
    assert f"## Response Mode\n\n{journal_mode_addendum(JournalMode.SCRIBE)}" in prompt


def test_the_transcript_editor_bounds_the_transcript() -> None:
    """The staged transcript editor (no caller yet) builds its prompt synchronously."""
    service = ContentEnrichmentService(backend=MagicMock())

    short_prompt = service._build_editing_prompt(SHORT_TEXT, "Tidy it.", None)
    long_prompt = service._build_editing_prompt(LONG_TEXT, "Tidy it.", None)

    assert SHORT_TEXT in short_prompt
    assert LONG_TEXT not in long_prompt
    assert len(long_prompt) <= len(short_prompt) + PromptInput.DOCUMENT_MAX_CHARS
    assert long_prompt.endswith(short_prompt.rsplit(SHORT_TEXT, 1)[-1])


def test_the_transcript_editor_bounds_the_transcript_beside_a_goal_with_no_description() -> None:
    """A goal stored without a description is valid; the context it shapes is still built."""
    service = ContentEnrichmentService(backend=MagicMock())
    context = {"active_goals": [{"title": "Run a marathon", "description": None}]}

    prompt = service._build_editing_prompt(LONG_TEXT, "Tidy it.", context)

    assert "Run a marathon" in prompt
    assert LONG_TEXT not in prompt
    assert len(prompt) <= PromptInput.DOCUMENT_MAX_CHARS + 5_000


def test_a_document_at_the_bound_reaches_the_prompt_whole() -> None:
    document = ("word " * 9000)[: PromptInput.DOCUMENT_MAX_CHARS]
    assert len(document) == PromptInput.DOCUMENT_MAX_CHARS
    service = ContentEnrichmentService(backend=MagicMock())

    assert document in service._build_editing_prompt(document, "Tidy it.", None)
