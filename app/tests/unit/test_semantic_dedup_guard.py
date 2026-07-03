"""Guard 3 semantic dedup — systems-review G8 / R3 ruling (Arc C).

The LLM bridge generates activity lines non-deterministically, so Guard 2's
literal-line hash never matches across syncs and every re-sync duplicated the
entity. Guard 3 dedups bridge-generated lines by
``(source entry, node label, normalized title)`` and MERGEs on a match.
"""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.dsl.activity_domain_converters import (
    derive_choice_title,
    derive_principle_title,
)
from core.services.dsl.activity_dsl_parser import ParsedActivityLine
from core.services.dsl.activity_extractor import (
    ActivityExtractionResult,
    ActivityExtractorService,
    _candidate_title,
    normalized_activity_title,
    normalized_line_hash,
    semantic_dedup_key,
)
from core.utils.result_simplified import Result


class TestSemanticKey:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Meditate", "meditate"),
            ("  MEDITATE  daily ", "meditate daily"),
            ("prep\ttomorrow", "prep tomorrow"),
            ("Straße", "strasse"),  # casefold, not lower
        ],
    )
    def test_normalized_activity_title(self, raw, expected):
        assert normalized_activity_title(raw) == expected

    def test_key_shape(self):
        assert semantic_dedup_key("Habit", " Meditate ") == ("Habit", "meditate")

    def test_candidate_title_derives_like_the_converters(self):
        long = "Be honest - even when it costs something " + "x" * 100
        assert _candidate_title("Principle", long) == derive_principle_title(long)
        assert _candidate_title("Choice", long) == derive_choice_title(long)
        assert _candidate_title("Habit", long) == long

    def test_principle_title_derivation_rules(self):
        assert derive_principle_title("Integrity - do the right thing") == "Integrity"
        assert derive_principle_title("Honesty: always") == "Honesty"
        capped = derive_principle_title("y" * 150)
        assert len(capped) == 100 and capped.endswith("...")

    def test_choice_title_cap(self):
        capped = derive_choice_title("z" * 250)
        assert len(capped) == 200 and capped.endswith("...")


def _line(description: str, raw_line: str) -> ParsedActivityLine:
    return ParsedActivityLine(
        description=description,
        contexts=[EntityType.HABIT],
        raw_line=raw_line,
    )


class _CountingCreator:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, activity: ParsedActivityLine, user_uid: str) -> Result[str]:
        self.calls += 1
        return Result.ok(f"habit_created_{self.calls}")


@pytest.mark.asyncio
class TestCreateForDomainGuards:
    async def test_bridge_line_matching_existing_entity_merges(self):
        """Same title, different wording → resolves to existing entity, no new node."""
        extractor = ActivityExtractorService()
        extraction = ActivityExtractionResult(entry_uid="ue_x", user_uid="user_x")
        creator = _CountingCreator()
        line = _line("Meditate", "Meditate @context(habit) @priority(2)")

        created, uids = await extractor._create_for_domain(
            [line],
            creator,
            "Habit",
            "user_x",
            extraction,
            existing_line_hashes=frozenset(),
            bridge_line_hashes=frozenset({normalized_line_hash(line.raw_line)}),
            existing_extracted={("Habit", "meditate"): "habit_existing"},
        )

        assert creator.calls == 0
        assert created == 0 and uids == []
        assert extraction.lines_merged_existing == 1
        # The existing entity's EXTRACTED_FROM edge stays untouched: writing the
        # bridge line's provenance would overwrite a real checkbox
        # source_line_hash/vault_id on the single (entity, entry) edge.
        assert extraction.created_links == []

    async def test_non_bridge_line_is_not_semantically_deduped(self):
        """User-typed lines keep exact Guard-2 semantics — no title merging."""
        extractor = ActivityExtractorService()
        extraction = ActivityExtractionResult(entry_uid="ue_x", user_uid="user_x")
        creator = _CountingCreator()
        line = _line("Meditate", "Meditate @context(habit)")

        created, _uids = await extractor._create_for_domain(
            [line],
            creator,
            "Habit",
            "user_x",
            extraction,
            existing_line_hashes=frozenset(),
            bridge_line_hashes=frozenset(),
            existing_extracted={("Habit", "meditate"): "habit_existing"},
        )

        assert creator.calls == 1
        assert created == 1
        assert extraction.lines_merged_existing == 0

    async def test_same_run_bridge_duplicates_merge(self):
        """A created entity registers its key so a later reworded line merges."""
        extractor = ActivityExtractorService()
        extraction = ActivityExtractionResult(entry_uid="ue_x", user_uid="user_x")
        creator = _CountingCreator()
        first = _line("Meditate", "Meditate @context(habit) v1")
        second = _line("Meditate", "Meditate @context(habit) v2")
        bridge_hashes = frozenset(
            {normalized_line_hash(first.raw_line), normalized_line_hash(second.raw_line)}
        )

        created, uids = await extractor._create_for_domain(
            [first, second],
            creator,
            "Habit",
            "user_x",
            extraction,
            existing_line_hashes=frozenset(),
            bridge_line_hashes=bridge_hashes,
            existing_extracted={},
        )

        assert creator.calls == 1
        assert created == 1 and uids == ["habit_created_1"]
        assert extraction.lines_merged_existing == 1
        # Only the CREATING line writes provenance; the merged rewording does not.
        assert [link[0] for link in extraction.created_links] == ["habit_created_1"]

    async def test_exact_hash_guard_still_wins_first(self):
        extractor = ActivityExtractorService()
        extraction = ActivityExtractionResult(entry_uid="ue_x", user_uid="user_x")
        creator = _CountingCreator()
        line = _line("Meditate", "Meditate @context(habit)")

        created, _uids = await extractor._create_for_domain(
            [line],
            creator,
            "Habit",
            "user_x",
            extraction,
            existing_line_hashes=frozenset({normalized_line_hash(line.raw_line)}),
            bridge_line_hashes=frozenset({normalized_line_hash(line.raw_line)}),
            existing_extracted={("Habit", "meditate"): "habit_existing"},
        )

        assert creator.calls == 0
        assert created == 0
        assert extraction.lines_skipped_existing == 1
        assert extraction.lines_merged_existing == 0
        assert extraction.created_links == []


@pytest.mark.asyncio
class TestCurriculumBranchThreading:
    async def test_ku_branch_threads_guard3(self):
        """Kody #501 medium: the KU/PS/LP branches must thread Guard 3 too —
        a teacher force-rerun with reworded bridge KU lines must merge."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from core.models.user_entry.user_entry import UserEntry

        ku_service = MagicMock()
        ku_service.create_ku = AsyncMock(
            return_value=Result.ok(SimpleNamespace(uid="ku_should_not_create"))
        )
        extractor = ActivityExtractorService(ku_service=ku_service)
        entry = UserEntry(uid="ue_x", title="t", user_uid="user_x", content="x")
        line = "- [ ] New concept @context(ku)"

        result = await extractor.extract_and_create(
            entry,
            "user_x",
            content_override=line,
            allow_curriculum_creation=True,
            bridge_line_hashes=frozenset({normalized_line_hash(line)}),
            existing_extracted={("Ku", "new concept"): "ku_existing"},
        )

        assert result.is_ok
        extraction = result.value
        assert extraction.kus_found == 1
        assert extraction.kus_created == 0
        assert extraction.lines_merged_existing == 1
        ku_service.create_ku.assert_not_awaited()
