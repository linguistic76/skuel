"""Arc E (G10) — honest ingestion: stats plumbing, relaxation scoping, skip reasons.

Pins the five seams this arc opened:
1. VaultReconciler stats merge — IncrementalStats errors/warnings/failed survive
   into VaultSyncStats (they were discarded by the old ``_count_ingested``).
1a. Sync fragment render — the edge-file and deletion counts the merge carries
   reach the panel. Edge YAMLs create no nodes, so an unrendered count is
   indistinguishable from a sync that did nothing.
2. Ingestion-context date relaxation — the EXTRACT_ACTIVITIES converters accept
   past dates (historical notes); interactive request construction still rejects.
3. Skip-reason bookkeeping — collect_files_detailed counts walled/unsupported
   files instead of letting them vanish from totals.
4. Per-line extraction warnings — pulled off the completed entry's metadata
   into the ingestion result dict.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fasthtml.common import to_xml
from pydantic import ValidationError

from core.models.enums.entity_enums import EntityType
from core.models.task.task_request import TaskCreateRequest
from core.ports.vault_bridge_protocol import VaultSyncStats
from core.services.dsl.activity_domain_converters import (
    activity_to_goal_request,
    activity_to_task_request,
)
from core.services.dsl.activity_dsl_parser import ParsedActivityLine
from core.services.ingestion.config import (
    SyncAllowlist,
    collect_files_detailed,
)
from core.services.ingestion.types import IncrementalStats, IngestionStats
from core.services.ingestion.user_entry_ingestion import _extraction_warnings_from_entry
from core.services.vault.vault_reconciler import _format_ingest_error, _merge_ingest_stats
from ui.vault.sync_fragments import sync_stats_fragment

# ============================================================================
# 1. VaultSyncStats merge (the G10 core: nothing discarded)
# ============================================================================


class TestMergeIngestStats:
    def test_errors_warnings_and_counts_survive(self):
        stats = VaultSyncStats()
        ingest = IncrementalStats(
            nodes_created=3,
            nodes_updated=1,
            files_failed=2,
            files_walled=5,
            files_unsupported=7,
            edges_created=3,
            edges_updated=4,
            entities_deleted=1,
            edges_deleted=2,
            warnings=["lp.x: relationship target 'ps.phantom' does not exist — edge not created"],
            errors=[
                {"file": "bad.md", "error": "boom", "stage": "parsing"},
                {"message": "Deletion reconciliation failed: x", "operation": "reconcile"},
            ],
        )
        _merge_ingest_stats(stats, ingest, Path("/vault"))

        assert stats.entries_ingested == 4
        # The parsing-stage failure is content-caused → ignored, leaving one
        # genuine (system) failure.
        assert stats.files_failed == 1
        assert stats.files_ignored == 1
        assert stats.ignored == ["bad.md — boom"]
        assert stats.files_walled == 5
        assert stats.files_unsupported == 7
        # Distinct values per field: a merge that carried one edge count into
        # both slots would satisfy any pair that happened to be equal.
        assert stats.edges_created == 3
        assert stats.edges_updated == 4
        assert stats.entities_deleted == 1
        assert stats.edges_deleted == 2
        assert stats.warnings == ingest.warnings
        assert stats.errors == ["reconcile: Deletion reconciliation failed: x"]
        assert not stats.is_clean

    def test_clean_run_is_clean(self):
        stats = VaultSyncStats()
        _merge_ingest_stats(stats, IncrementalStats(nodes_created=2), Path("/vault"))
        assert stats.is_clean
        assert stats.entries_ingested == 2

    def test_full_mode_stats_also_merge(self):
        stats = VaultSyncStats()
        _merge_ingest_stats(
            stats,
            IngestionStats(nodes_created=1, failed=1, errors=[{"file": "f.md", "error": "e"}]),
            Path("/vault"),
        )
        assert stats.files_failed == 1
        assert stats.errors == ["f.md: e"]

    def test_warnings_alone_flip_is_clean(self):
        stats = VaultSyncStats(warnings=["dangling target"])
        assert not stats.is_clean

    def test_format_ingest_error_falls_back_to_str(self):
        assert _format_ingest_error({"weird": True}, Path("/vault")) == "{'weird': True}"

    def test_absolute_vault_paths_relativized(self, tmp_path: Path):
        """Ingest errors/warnings carry absolute host paths — the merge must
        strip the vault root before they reach the user-facing stats
        (system-stage errors and content-stage ignored lines alike)."""
        stats = VaultSyncStats()
        ingest = IncrementalStats(
            nodes_created=0,
            warnings=[f"deletion skipped for {tmp_path}/notes/gone.md: entity mismatch"],
            errors=[
                {"file": str(tmp_path / "notes" / "bad.md"), "error": "boom", "stage": "parsing"},
                {"file": str(tmp_path / "notes" / "db.md"), "error": "down", "stage": "ingestion"},
            ],
        )
        _merge_ingest_stats(stats, ingest, tmp_path)

        assert stats.ignored == ["notes/bad.md — boom"]
        assert stats.errors == ["notes/db.md: down [ingestion]"]
        assert stats.warnings == ["deletion skipped for notes/gone.md: entity mismatch"]
        for line in stats.errors + stats.warnings + stats.ignored:
            assert str(tmp_path.resolve()) not in line

    def test_full_mode_carries_no_edge_or_deletion_counts(self):
        """Only the tracked modes have them, so the fields must stay at zero.

        Deletion reconciliation and edge-file tracking do not run in full mode,
        and ``IngestionStats`` has no field for either — the merge reads them off
        ``IncrementalStats`` alone. A carry moved out of that branch would report
        counts a full-mode run never measured.
        """
        stats = VaultSyncStats()
        _merge_ingest_stats(stats, IngestionStats(nodes_created=1), Path("/vault"))
        assert (stats.edges_created, stats.edges_updated, stats.edges_deleted) == (0, 0, 0)


class TestSyncStatsFragment:
    """The sync panel reports edge-file work in both directions.

    Edge YAMLs move no node count, so before these lines a sync that wrote or
    removed relationships rendered identically to one that did nothing. Each
    line appears only when its count is non-zero (the file's existing idiom).
    """

    def test_edge_and_deletion_counts_render(self):
        xml = to_xml(
            sync_stats_fragment(
                asdict(
                    VaultSyncStats(
                        edges_created=2,
                        edges_updated=3,
                        entities_deleted=4,
                        edges_deleted=5,
                    )
                )
            )
        )
        # Each count is asserted next to its own label: a fragment that rendered
        # the right four numbers against swapped labels would pass on counts
        # alone, and "5 relationships created" is a lie about a deletion.
        assert '<span class="font-semibold">2</span> relationships created from edges/' in xml
        assert '<span class="font-semibold">3</span> relationships refreshed' in xml
        assert '<span class="font-semibold">4</span> notes removed' in xml
        assert '<span class="font-semibold">5</span> relationships removed' in xml

    def test_untouched_counts_render_nothing(self):
        xml = to_xml(sync_stats_fragment(asdict(VaultSyncStats(entries_ingested=1))))
        # The always-on line proves the fragment rendered — without it the
        # absence assertions below would also hold for an empty string.
        assert '<span class="font-semibold">1</span> notes ingested' in xml
        assert "relationships" not in xml
        assert "removed" not in xml
        assert "re-opened" not in xml

    def test_reopened_tasks_render_beside_the_done_count(self):
        """The reopen's vault surface reaches the user through this line.

        Conditional like the edge/deletion counts, and never confusable with
        the always-shown done count — a sync that un-checked three lines and
        one that checked three lines say opposite things about the vault.
        """
        xml = to_xml(
            sync_stats_fragment(asdict(VaultSyncStats(tasks_marked_done=2, tasks_marked_undone=3)))
        )
        assert '<span class="font-semibold">2</span> tasks marked done in vault' in xml
        assert '<span class="font-semibold">3</span> tasks re-opened in vault' in xml


class TestRetrievabilityHonesty:
    """Sync-honesty ruling: unretrievable content and probe failures never
    flip cleanliness — the clean header VARIANT carries the signal, and a
    probe outage is invisible to the banner entirely."""

    def test_unretrievable_content_does_not_flip_is_clean(self):
        stats = VaultSyncStats(
            retrievability_delta=5,
            chunks_awaiting_embedding=3,
            entities_awaiting_embedding=2,
        )
        assert stats.is_clean

    def test_coverage_probe_failed_does_not_flip_is_clean(self):
        assert VaultSyncStats(coverage_probe_failed=True).is_clean

    def test_clean_sync_with_unretrievable_content_gets_variant_header(self):
        xml = to_xml(
            sync_stats_fragment(asdict(VaultSyncStats(entries_ingested=2, retrievability_delta=7)))
        )
        assert "Sync complete — 7 items not yet searchable" in xml
        assert "text-warning" in xml
        assert "Sync finished with problems" not in xml

    def test_clean_sync_with_zero_delta_keeps_success_header(self):
        xml = to_xml(sync_stats_fragment(asdict(VaultSyncStats(entries_ingested=1))))
        assert ">Sync complete</h3>" in xml
        assert "text-success" in xml
        assert "not yet searchable" not in xml

    def test_problem_header_wins_over_delta(self):
        """A sync with real problems reports the problems — the retrievability
        variant exists only on the clean path."""
        xml = to_xml(
            sync_stats_fragment(
                asdict(
                    VaultSyncStats(files_failed=1, errors=["x.md: boom"], retrievability_delta=4)
                )
            )
        )
        assert "Sync finished with problems" in xml
        assert "not yet searchable" not in xml

    def test_probe_failure_renders_no_warning_section(self):
        xml = to_xml(sync_stats_fragment(asdict(VaultSyncStats(coverage_probe_failed=True))))
        assert ">Sync complete</h3>" in xml
        assert "Warnings" not in xml


class TestIgnoredClassification:
    """2026-07-23 ruling: content-caused failures are ignored-with-reason,
    never sync errors; ``errors``/``files_failed`` keep only system faults."""

    def _merge(self, errors: list[dict[str, Any]], failed: int) -> VaultSyncStats:
        stats = VaultSyncStats()
        _merge_ingest_stats(
            stats,
            IncrementalStats(files_failed=failed, errors=errors),
            Path("/vault"),
        )
        return stats

    def test_all_content_stages_classify_as_ignored(self):
        errors = [
            {"file": f"{stage}.md", "error": "reason", "stage": stage}
            for stage in ("parsing", "type_detection", "validation", "preparation")
        ]
        stats = self._merge(errors, failed=4)
        assert stats.files_ignored == 4
        assert stats.files_failed == 0
        assert stats.errors == []
        assert stats.is_clean  # ignored-only sync IS clean

    def test_system_stages_stay_errors(self):
        errors = [
            {"file": "batch.md", "error": "neo4j down", "stage": "ingestion"},
            {"file": "note.md", "error": "denied", "stage": "file_io"},
            {"file": "ue.md", "error": "unreviewable", "stage": "user_entry_pipeline"},
            {"file": "weird.md", "error": "boom", "stage": "unknown"},
        ]
        stats = self._merge(errors, failed=4)
        assert stats.files_ignored == 0
        assert stats.files_failed == 4
        assert len(stats.errors) == 4
        assert not stats.is_clean

    def test_declared_type_flavor_names_the_type(self):
        """A file that opted in (declared a type) but has a malformed field is
        called out with the type up front, so it's easy to spot for fixing."""
        stats = self._merge(
            [
                {
                    "file": "/vault/Ku/ku_sel.md",
                    "error": "'uid:' field is present but empty",
                    "stage": "validation",
                    "entity_type": "ku",
                }
            ],
            failed=1,
        )
        assert stats.ignored == [
            "Ku/ku_sel.md — declared 'type: ku' but not ingested: 'uid:' field is present but empty"
        ]

    def test_missing_type_flavor_is_plain_reason(self):
        stats = self._merge(
            [{"file": "Research.md", "error": "no 'type:' field", "stage": "type_detection"}],
            failed=1,
        )
        assert stats.ignored == ["Research.md — no 'type:' field"]

    def test_stageless_error_dicts_stay_errors(self):
        """Ad-hoc ``{"message": ...}`` dicts (deletion reconciliation) carry
        no stage — they are system reports and must never be ignored."""
        stats = self._merge([{"message": "Deletion reconciliation failed: x"}], failed=0)
        assert stats.files_ignored == 0
        assert len(stats.errors) == 1

    def test_ignored_files_do_not_flip_is_clean(self):
        stats = VaultSyncStats(files_ignored=3, ignored=["a — r", "b — r", "c — r"])
        assert stats.is_clean


# ============================================================================
# 2. Ingestion-context past-date relaxation (scoped, not global)
# ============================================================================


class TestPastDateRelaxation:
    def test_interactive_task_request_still_rejects_past_due_date(self):
        with pytest.raises(ValidationError, match="past"):
            TaskCreateRequest(title="t", due_date=date.today() - timedelta(days=30))

    def test_model_validate_without_context_still_rejects(self):
        with pytest.raises(ValidationError, match="past"):
            TaskCreateRequest.model_validate(
                {"title": "t", "due_date": date.today() - timedelta(days=30)}
            )

    def test_converter_accepts_past_due_date(self):
        activity = ParsedActivityLine(
            description="historical task",
            contexts=[EntityType.TASK],
            when=datetime.now() - timedelta(days=30),
            raw_line="- [ ] historical task 📅 old",
        )
        result = activity_to_task_request(activity)
        assert result.is_ok, f"converter rejected past due date: {result}"
        request = result.value
        assert isinstance(request, TaskCreateRequest)
        assert request.due_date == (datetime.now() - timedelta(days=30)).date()

    def test_goal_converter_accepts_past_target_date(self):
        activity = ParsedActivityLine(
            description="historical goal",
            contexts=[EntityType.GOAL],
            when=datetime.now() - timedelta(days=30),
            raw_line="- [ ] historical goal",
        )
        result = activity_to_goal_request(activity)
        assert result.is_ok, f"goal converter rejected past target date: {result}"


# ============================================================================
# 3. Skip-reason bookkeeping (collect_files_detailed)
# ============================================================================


class TestCollectFilesDetailed:
    def test_walled_and_unsupported_counted(self, tmp_path: Path):
        allowed = tmp_path / "allowed"
        walled = tmp_path / "private"
        allowed.mkdir()
        walled.mkdir()
        (allowed / "a.md").write_text("a")
        (walled / "b.md").write_text("b")
        (tmp_path / "image.png").write_bytes(b"x")
        hidden = tmp_path / ".obsidian"
        hidden.mkdir()
        (hidden / "config.json").write_text("{}")

        allowlist = SyncAllowlist(
            governed_root=tmp_path.resolve(), allowed_dirs=frozenset({allowed.resolve()})
        )
        files, skips = collect_files_detailed(tmp_path, "*", allowlist)

        assert [f.name for f in files] == ["a.md"]
        assert skips.walled == 1  # private/b.md
        assert skips.unsupported == 1  # image.png; .obsidian/ is hidden → not counted

    def test_no_wall_means_zero_walled(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("a")
        files, skips = collect_files_detailed(tmp_path, "*", None)
        assert len(files) == 1
        assert skips.walled == 0
        assert skips.unsupported == 0

    def test_targeted_pattern_does_not_claim_unsupported(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("a")
        (tmp_path / "image.png").write_bytes(b"x")
        _, skips = collect_files_detailed(tmp_path, "*.md", None)
        assert skips.unsupported == 0


# ============================================================================
# 4. Per-line extraction warnings off the entry metadata
# ============================================================================


@dataclass
class _EntryStub:
    metadata: dict[str, Any] | None = field(default_factory=dict)


class TestExtractionWarnings:
    def test_collects_all_three_error_channels(self):
        entry = _EntryStub(
            metadata={
                "activity_extraction": {
                    "parse_errors": ["line 3: bad @context"],
                    "creation_errors": ["Task 'x...': due date rejected"],
                    "link_errors": ["APPLIES_KNOWLEDGE ue_1 -> ku.x: not found"],
                }
            }
        )
        warnings = _extraction_warnings_from_entry(entry)  # type: ignore[arg-type]
        assert len(warnings) == 3

    def test_clean_summary_yields_no_warnings(self):
        entry = _EntryStub(
            metadata={"activity_extraction": {"parse_errors": [], "creation_errors": []}}
        )
        assert _extraction_warnings_from_entry(entry) == []  # type: ignore[arg-type]

    def test_missing_summary_and_none_entry_are_safe(self):
        assert _extraction_warnings_from_entry(None) == []
        assert _extraction_warnings_from_entry(_EntryStub(metadata=None)) == []  # type: ignore[arg-type]
