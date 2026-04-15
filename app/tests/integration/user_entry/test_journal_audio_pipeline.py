"""
Journal-audio pipeline integration test — ADR-054 Commit 3
===========================================================

Exercises ``Pipeline.TRANSCRIBE_AND_STRUCTURE`` end-to-end against a real
Neo4j container:

    1. Student creates a ``UserEntry`` with ``pipeline=TRANSCRIBE_AND_STRUCTURE``
       pointing at an audio ``file_path``.
    2. ``UserEntryProcessingService.process(entry)`` runs with mocked
       Deepgram + LLM adapters (external I/O is not under test here —
       graph topology is).
    3. Assertions:
       - source entry has ``processed_content`` = transcript
       - a second ``:UserEntry`` exists carrying the structured LLM output
       - the structured entry ``-[:TRANSFORMS]->`` source entry
       - both entries are readable via ``list_for_user``
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.ports.output_generator_protocols import OutputInstruction
from core.services.user_entry.user_entry_processing_service import (
    UserEntryProcessingService,
)
from core.utils.result_simplified import Result


@dataclass
class _FakeTranscript:
    transcript_text: str
    confidence_score: float = 0.95
    duration_seconds: float = 1.5
    word_count: int = 10


def _fake_instruction() -> OutputInstruction:
    return OutputInstruction(
        prompt_text="STRUCTURE: {content}",
        source="template",
        model="gpt-4o-mini",
        temperature=0.5,
        max_tokens=2048,
    )


@pytest.mark.asyncio
async def test_transcribe_and_structure_creates_linked_pair(
    clean_neo4j,
    user_entry_service,
    neo4j_driver,
    seed_user,
) -> None:
    student_uid = await seed_user("user.ue_journaler", name="Journaler")

    # Mock the external I/O the processing service reaches out to.
    transcript_text = "Today I learned about protocols in Python."
    structured_text = "- Topic: protocols\n- Takeaway: duck typing without inheritance"

    transcription_adapter = MagicMock()
    transcription_adapter.transcribe = AsyncMock(
        return_value=Result.ok(_FakeTranscript(transcript_text=transcript_text))
    )

    llm_caller = MagicMock()
    llm_caller.generate = AsyncMock(return_value=Result.ok(structured_text))

    instruction_resolver = MagicMock()
    instruction_resolver.resolve = MagicMock(return_value=Result.ok(_fake_instruction()))

    dispatcher = UserEntryProcessingService(
        entry_service=user_entry_service,
        transcription_adapter=transcription_adapter,
        llm_caller=llm_caller,
        instruction_resolver=instruction_resolver,
    )

    # Source entry: a persisted audio upload awaiting processing
    source_result = await user_entry_service.create_entry(
        request=UserEntryCreateRequest(
            title="Morning audio reflection",
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            file_path="/tmp/does-not-matter.mp3",
            original_filename="reflection.mp3",
            file_type="audio/mpeg",
        ),
        user_uid=student_uid,
    )
    assert source_result.is_ok, source_result.expect_error()
    source = source_result.value

    # Run the pipeline
    process_result = await dispatcher.process(source)
    assert process_result.is_ok, process_result.expect_error()

    # Adapters were called with the expected inputs
    transcription_adapter.transcribe.assert_awaited_once_with(
        audio_path="/tmp/does-not-matter.mp3"
    )
    llm_caller.generate.assert_awaited_once()
    llm_kwargs = llm_caller.generate.await_args.kwargs
    assert transcript_text in llm_kwargs["prompt"]

    # Graph state — two UserEntry nodes linked by TRANSFORMS
    async with neo4j_driver.session() as session:
        pair = await (
            await session.run(
                """
                MATCH (src:UserEntry {uid: $src_uid})
                OPTIONAL MATCH (child:UserEntry)-[:TRANSFORMS]->(src)
                RETURN src.processed_content AS transcript,
                       child.uid             AS child_uid,
                       child.content         AS child_content,
                       child.pipeline        AS child_pipeline
                """,
                src_uid=source.uid,
            )
        ).single()
        assert pair is not None
        assert pair["transcript"] == transcript_text
        assert pair["child_uid"] is not None
        assert pair["child_uid"] != source.uid
        assert pair["child_content"] == structured_text
        assert pair["child_pipeline"] == Pipeline.NONE.value

        # No stray UserEntry nodes (exactly two for this user)
        count = await (
            await session.run(
                "MATCH (u:UserEntry {user_uid: $uid}) RETURN count(u) AS cnt",
                uid=student_uid,
            )
        ).single()
        assert count is not None and count["cnt"] == 2

    # list_for_user sees both entries
    listed = await user_entry_service.list_for_user(user_uid=student_uid)
    assert listed.is_ok
    uids = {e.uid for e in listed.value or []}
    assert source.uid in uids
    assert len(uids) == 2
