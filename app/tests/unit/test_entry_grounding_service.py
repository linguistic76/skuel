"""Tests for EntryGroundingService (Entry-Enrichment PR 3).

Covers:
- Candidate stage: threshold + limit forwarded to the Ku vector index;
  already-applied and user-rejected Kus excluded
- Eager write: provenance confidence = similarity; one substance event per
  genuinely NEW edge; matched-existing write (race) publishes nothing
- CORE degrade: no chat port → vector-only eager writes, verdict=None
- Judge: engages=false filtered (no write, no event); malformed JSON /
  incomplete coverage → entry skipped un-stamped with error, other entries land
- Stamp: embedding_text_hash + GROUNDING_VERSION after an applied pass;
  dry-run (apply=False) writes/stamps/publishes nothing but reports the plan
- remove(): ownership-scoped backend row → True; None → False (route 404s)
- Missing vector search → unavailable error
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.knowledge_substance_events import KnowledgeReflectedInEntry
from core.ports.query_types import GroundingEntryRow, GroundingRemovalRow
from core.services.entry_grounding_service import (
    GROUNDING_VERSION,
    EntryGroundingConfig,
    EntryGroundingService,
)
from core.utils.result_simplified import Result


def _row(
    uid: str = "ue_abc123",
    applied: list[str] | None = None,
    rejected: list[str] | None = None,
) -> GroundingEntryRow:
    return GroundingEntryRow(
        uid=uid,
        user_uid="user_mike",
        title=f"title of {uid}",
        content="I practiced attention on my breath while journaling today.",
        embedding=[0.1, 0.2, 0.3],
        embedding_text_hash="hash-v3-abc",
        applied_ku_uids=applied or [],
        rejected_ku_uids=rejected or [],
    )


def _hit(ku_uid: str, score: float) -> dict:
    return {"node": {"uid": ku_uid, "title": f"Ku {ku_uid}"}, "score": score}


def _backend(rows: list[GroundingEntryRow]) -> MagicMock:
    backend = MagicMock()
    backend.get_pending_entries = AsyncMock(return_value=Result.ok(rows))
    backend.write_applies_knowledge = AsyncMock(return_value=Result.ok(True))
    backend.stamp_grounded = AsyncMock(return_value=Result.ok(None))
    return backend


def _vector(hits: list[dict]) -> MagicMock:
    vector = MagicMock()
    vector.find_similar_by_vector = AsyncMock(return_value=Result.ok(hits))
    return vector


def _bus() -> MagicMock:
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return bus


def _llm_with_response(text: str) -> MagicMock:
    llm = MagicMock()
    completion = MagicMock()
    completion.text = text
    llm.chat_port.complete = AsyncMock(return_value=Result.ok(completion))
    return llm


def _service(
    backend: MagicMock,
    vector_search: MagicMock | None,
    llm: MagicMock | None = None,
    event_bus: MagicMock | None = None,
) -> EntryGroundingService:
    return EntryGroundingService(
        backend=backend,
        vector_search=vector_search,
        event_bus=event_bus,
        llm_service=llm,
    )


# ============================================================================
# Candidate stage
# ============================================================================


@pytest.mark.anyio
async def test_threshold_and_limit_forwarded_to_ku_index() -> None:
    vector = _vector([])
    service = _service(_backend([_row()]), vector)

    result = await service.ground_pending()

    assert not result.is_error
    call = vector.find_similar_by_vector.await_args
    assert call.kwargs["label"] == "Ku"
    assert call.kwargs["min_score"] == EntryGroundingConfig().threshold == 0.72
    assert call.kwargs["limit"] == EntryGroundingConfig().max_candidates


@pytest.mark.anyio
async def test_applied_and_rejected_kus_excluded() -> None:
    """An existing edge never re-writes (or re-counts); a user-removed link never re-infers."""
    bus = _bus()
    backend = _backend([_row(applied=["ku.a.linked"], rejected=["ku.a.removed"])])
    hits = [_hit("ku.a.linked", 0.9), _hit("ku.a.removed", 0.85), _hit("ku.a.fresh", 0.8)]
    service = _service(backend, _vector(hits), event_bus=bus)

    result = await service.ground_pending()

    assert not result.is_error
    outcome = result.value.outcomes[0]
    assert [c.ku_uid for c in outcome.written] == ["ku.a.fresh"]
    assert outcome.skipped_existing == 1
    assert outcome.skipped_rejected == 1
    backend.write_applies_knowledge.assert_awaited_once_with("ue_abc123", "ku.a.fresh", 0.8)
    assert bus.publish_async.await_count == 1


# ============================================================================
# Eager write + substance event
# ============================================================================


@pytest.mark.anyio
async def test_new_edge_publishes_substance_event_with_provenance() -> None:
    bus = _bus()
    backend = _backend([_row()])
    service = _service(backend, _vector([_hit("ku.a.one", 0.7654321)]), event_bus=bus)

    result = await service.ground_pending()

    assert not result.is_error
    # Confidence is the (rounded) similarity — the MEGA-QUERY min_confidence contract.
    backend.write_applies_knowledge.assert_awaited_once_with("ue_abc123", "ku.a.one", 0.7654)
    event = bus.publish_async.await_args.args[0]
    assert isinstance(event, KnowledgeReflectedInEntry)
    assert event.knowledge_uid == "ku.a.one"
    assert event.entry_uid == "ue_abc123"
    assert event.user_uid == "user_mike"


@pytest.mark.anyio
async def test_matched_existing_edge_publishes_nothing() -> None:
    """A race that MERGE-matches an existing edge must not double-count substance."""
    bus = _bus()
    backend = _backend([_row()])
    backend.write_applies_knowledge = AsyncMock(return_value=Result.ok(False))
    service = _service(backend, _vector([_hit("ku.a.one", 0.8)]), event_bus=bus)

    result = await service.ground_pending()

    assert not result.is_error
    bus.publish_async.assert_not_awaited()
    assert result.value.outcomes[0].written == ()


@pytest.mark.anyio
async def test_stamp_after_applied_pass_uses_hash_and_version() -> None:
    backend = _backend([_row()])
    service = _service(backend, _vector([_hit("ku.a.one", 0.8)]))

    result = await service.ground_pending()

    assert not result.is_error
    backend.stamp_grounded.assert_awaited_once_with("ue_abc123", "hash-v3-abc", GROUNDING_VERSION)


@pytest.mark.anyio
async def test_dry_run_writes_stamps_publishes_nothing() -> None:
    bus = _bus()
    backend = _backend([_row()])
    service = _service(backend, _vector([_hit("ku.a.one", 0.8)]), event_bus=bus)

    result = await service.ground_pending(apply=False)

    assert not result.is_error
    backend.write_applies_knowledge.assert_not_awaited()
    backend.stamp_grounded.assert_not_awaited()
    bus.publish_async.assert_not_awaited()
    # ... but the report shows exactly what --apply would write.
    report = result.value
    assert report.applied is False
    assert report.edges_written == 1
    assert [c.ku_uid for c in report.outcomes[0].written] == ["ku.a.one"]


# ============================================================================
# CORE degrade + judge
# ============================================================================


@pytest.mark.anyio
async def test_core_tier_writes_vector_only_unjudged() -> None:
    backend = _backend([_row()])
    service = _service(backend, _vector([_hit("ku.a.one", 0.8)]), llm=None)

    result = await service.ground_pending()

    assert not result.is_error
    assert service.judge_available is False
    outcome = result.value.outcomes[0]
    assert outcome.judged is False
    assert [c.verdict for c in outcome.written] == [None]
    backend.write_applies_knowledge.assert_awaited_once()


@pytest.mark.anyio
async def test_judge_filters_brush_past_candidates() -> None:
    bus = _bus()
    verdicts = json.dumps(
        [
            {"index": 1, "engages": True, "rationale": "applies the practice directly"},
            {"index": 2, "engages": False, "rationale": "shared vocabulary only"},
        ]
    )
    llm = _llm_with_response(f"```json\n{verdicts}\n```")
    backend = _backend([_row()])
    service = _service(
        backend, _vector([_hit("ku.a.one", 0.8), _hit("ku.a.two", 0.75)]), llm=llm, event_bus=bus
    )

    result = await service.ground_pending()

    assert not result.is_error
    outcome = result.value.outcomes[0]
    assert [c.ku_uid for c in outcome.written] == ["ku.a.one"]
    assert [c.ku_uid for c in outcome.rejected_by_judge] == ["ku.a.two"]
    assert outcome.rejected_by_judge[0].rationale == "shared vocabulary only"
    backend.write_applies_knowledge.assert_awaited_once_with("ue_abc123", "ku.a.one", 0.8)
    assert bus.publish_async.await_count == 1


@pytest.mark.anyio
async def test_judge_malformed_json_skips_entry_unstamped() -> None:
    """A failed judge must not write or stamp that entry — retried next pass."""
    llm = MagicMock()
    good = MagicMock()
    good.text = json.dumps([{"index": 1, "engages": True, "rationale": "ok"}])
    bad = MagicMock()
    bad.text = "I think candidate 1 is great!"
    # First entry gets the malformed response, second the valid one —
    # per-entry fail-soft, not per-pass.
    llm.chat_port.complete = AsyncMock(side_effect=[Result.ok(bad), Result.ok(good)])
    backend = _backend([_row(), _row(uid="ue_good99")])
    service = _service(backend, _vector([_hit("ku.a.one", 0.8)]), llm=llm)

    result = await service.ground_pending()

    assert not result.is_error
    report = result.value
    assert report.entries_failed == 1
    failed = next(o for o in report.outcomes if o.error is not None)
    ok = next(o for o in report.outcomes if o.error is None)
    assert "judge failed" in str(failed.error)
    assert [c.ku_uid for c in ok.written] == ["ku.a.one"]
    # Only the successful entry was written + stamped.
    backend.write_applies_knowledge.assert_awaited_once()
    backend.stamp_grounded.assert_awaited_once_with(ok.entry_uid, "hash-v3-abc", GROUNDING_VERSION)


@pytest.mark.anyio
async def test_judge_incomplete_coverage_fails_entry() -> None:
    """A half-judged entry must not write the unjudged half."""
    llm = _llm_with_response(json.dumps([{"index": 1, "engages": True, "rationale": "ok"}]))
    backend = _backend([_row()])
    service = _service(backend, _vector([_hit("ku.a.one", 0.8), _hit("ku.a.two", 0.75)]), llm=llm)

    result = await service.ground_pending()

    assert not result.is_error
    assert result.value.entries_failed == 1
    backend.write_applies_knowledge.assert_not_awaited()
    backend.stamp_grounded.assert_not_awaited()


# ============================================================================
# remove() + unavailability
# ============================================================================


@pytest.mark.anyio
async def test_remove_returns_true_on_backend_row() -> None:
    backend = _backend([])
    backend.remove_grounded_edge = AsyncMock(
        return_value=Result.ok(
            GroundingRemovalRow(ku_uid="ku.a.one", confidence=0.74, inferred=True)
        )
    )
    service = _service(backend, _vector([]))

    result = await service.remove("ue_abc123", "ku.a.one", "user_mike")

    assert not result.is_error
    assert result.value is True
    backend.remove_grounded_edge.assert_awaited_once_with("ue_abc123", "ku.a.one", "user_mike")


@pytest.mark.anyio
async def test_remove_returns_false_when_nothing_matched() -> None:
    """Not-owned entry or absent edge → False, so the route 404s (never 403)."""
    backend = _backend([])
    backend.remove_grounded_edge = AsyncMock(return_value=Result.ok(None))
    service = _service(backend, _vector([]))

    result = await service.remove("ue_abc123", "ku.a.one", "user_other")

    assert not result.is_error
    assert result.value is False


@pytest.mark.anyio
async def test_missing_vector_search_is_unavailable() -> None:
    service = _service(_backend([_row()]), vector_search=None)

    result = await service.ground_pending()

    assert result.is_error
    assert "vector" in str(result.expect_error()).lower()
