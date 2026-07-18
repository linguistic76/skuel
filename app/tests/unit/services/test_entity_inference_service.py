"""
Unit tests for EntityInferenceService — the confidence scoring engine.

Testing-gap roadmap item 4: this ~893-line scoring engine (keyword / phrase /
contextual / complexity pattern detection, pattern merging, advanced confidence
scoring, cross-domain relationship discovery, and the basic inference fallback)
had ZERO test coverage despite being entirely synchronous and I/O-free.

These tests are mock-free: EntityInferenceService is a pure computation service,
so every test drives the real implementation with real inputs. Inputs are chosen
from the service's own knowledge mappings (self.knowledge_keywords,
self.knowledge_phrases, self.cross_domain_mappings) so tests stay stable against
copy edits elsewhere. Expected values assert against the symbolic constants in
core.constants (InferenceConfidence / ConfidenceLevel) rather than bare
literals, except where the source itself hardcodes literals (basic-path
0.95 / 0.90 / 0.60 connection scores).
"""

import pytest

from core.constants import ConfidenceLevel, InferenceConfidence
from core.models.task.task_dto import TaskDTO
from core.services.entity_inference_service import (
    EntityInferenceService,
    InferenceConfig,
    KuPattern,
)
from core.services.tasks.task_relationships import TaskRelationships

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> EntityInferenceService:
    """Advanced-engine service (default config)."""
    return EntityInferenceService(InferenceConfig())


@pytest.fixture
def basic_service() -> EntityInferenceService:
    """Basic-engine service (advanced engine disabled)."""
    return EntityInferenceService(InferenceConfig(enable_advanced_engine=False))


def make_pattern(
    pattern_type: str = "keyword_enhanced",
    knowledge_uid: str = "ku.programming.python",
    confidence: float = 0.8,
    evidence: list[str] | None = None,
    domain: str = "programming",
) -> KuPattern:
    """Construct a KuPattern with sensible defaults for scoring tests."""
    return KuPattern(
        pattern_type=pattern_type,
        knowledge_uid=knowledge_uid,
        confidence=confidence,
        evidence=evidence if evidence is not None else ["Direct keyword: 'python'"],
        domain=domain,
    )


def make_task(title: str, description: str | None = None) -> TaskDTO:
    """Construct a TaskDTO via the factory (updated_at defaults to now)."""
    return TaskDTO.create_task(user_uid="user_test", title=title, description=description)


# ---------------------------------------------------------------------------
# _detect_keyword_patterns
# ---------------------------------------------------------------------------


class TestDetectKeywordPatterns:
    """Keyword tier confidences and multi-factor boosting."""

    def test_direct_keyword_scores_direct_confidence(self, service: EntityInferenceService) -> None:
        # Guard: keyword really lives in the service's own mapping.
        assert "python" in service.knowledge_keywords["ku.programming.python"]["direct"]

        patterns = service._detect_keyword_patterns("python")

        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.knowledge_uid == "ku.programming.python"
        assert pattern.pattern_type == "keyword_enhanced"
        assert pattern.domain == "programming"
        assert pattern.confidence == pytest.approx(InferenceConfidence.DIRECT_KEYWORD)
        assert pattern.evidence == ["Direct keyword: 'python'"]

    def test_advanced_keyword_scores_advanced_confidence(
        self, service: EntityInferenceService
    ) -> None:
        assert "asyncio" in service.knowledge_keywords["ku.programming.python"]["advanced"]

        patterns = service._detect_keyword_patterns("asyncio")

        assert len(patterns) == 1
        assert patterns[0].confidence == pytest.approx(InferenceConfidence.ADVANCED_KEYWORD)

    def test_contextual_keyword_scores_contextual_confidence(
        self, service: EntityInferenceService
    ) -> None:
        assert (
            "virtual environment"
            in service.knowledge_keywords["ku.programming.python"]["contextual"]
        )

        patterns = service._detect_keyword_patterns("virtual environment")

        assert len(patterns) == 1
        assert patterns[0].confidence == pytest.approx(InferenceConfidence.CONTEXTUAL_KEYWORD)

    def test_two_factor_match_boosts_from_max_factor(self, service: EntityInferenceService) -> None:
        # "python" (direct 0.8) + "asyncio" (advanced 0.9): base = max = 0.9,
        # boosted by MULTI_MATCH_BOOST_PER * (2 - 1), capped at MULTI_MATCH_CAP.
        patterns = service._detect_keyword_patterns("python asyncio")

        assert len(patterns) == 1
        expected = min(
            InferenceConfidence.MULTI_MATCH_CAP,
            InferenceConfidence.ADVANCED_KEYWORD + InferenceConfidence.MULTI_MATCH_BOOST_PER,
        )
        assert patterns[0].confidence == pytest.approx(expected)
        assert len(patterns[0].evidence) == 2

    def test_three_factor_match_hits_multi_match_cap(self, service: EntityInferenceService) -> None:
        # direct "python" + contextual "import " + advanced "asyncio" would be
        # 0.9 + 0.1 * 2 = 1.1 uncapped; the cap keeps it at MULTI_MATCH_CAP.
        patterns = service._detect_keyword_patterns("python import asyncio")

        assert len(patterns) == 1
        assert patterns[0].confidence == pytest.approx(InferenceConfidence.MULTI_MATCH_CAP)
        assert len(patterns[0].evidence) == 3

    def test_empty_content_returns_no_patterns(self, service: EntityInferenceService) -> None:
        assert service._detect_keyword_patterns("") == []

    def test_non_matching_content_returns_no_patterns(
        self, service: EntityInferenceService
    ) -> None:
        assert service._detect_keyword_patterns("watering the garden tulips") == []


# ---------------------------------------------------------------------------
# _detect_phrase_patterns
# ---------------------------------------------------------------------------


class TestDetectPhrasePatterns:
    """Regex phrase detection: confidence = min(cap, base + per_evidence * n)."""

    def test_single_phrase_match(self, service: EntityInferenceService) -> None:
        assert "ku.programming.api" in service.knowledge_phrases

        patterns = service._detect_phrase_patterns("rest api")

        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.knowledge_uid == "ku.programming.api"
        assert pattern.pattern_type == "phrase_pattern"
        assert pattern.domain == "programming"
        expected = InferenceConfidence.PHRASE_BASE + InferenceConfidence.PHRASE_PER_EVIDENCE
        assert pattern.confidence == pytest.approx(expected)
        assert pattern.evidence == ["Phrase pattern: 'rest api'"]

    def test_multiple_matches_raise_confidence(self, service: EntityInferenceService) -> None:
        # "rest api" (one regex) + "swagger" (another regex) = 2 evidence items.
        patterns = service._detect_phrase_patterns("rest api and swagger")

        assert len(patterns) == 1
        expected = InferenceConfidence.PHRASE_BASE + 2 * InferenceConfidence.PHRASE_PER_EVIDENCE
        assert patterns[0].confidence == pytest.approx(expected)
        assert len(patterns[0].evidence) == 2

    def test_many_matches_hit_phrase_cap(self, service: EntityInferenceService) -> None:
        # 4 evidence items would be 0.7 + 0.2 = 0.9 uncapped; capped at PHRASE_CAP.
        patterns = service._detect_phrase_patterns("rest api endpoint swagger openapi")

        assert len(patterns) == 1
        assert len(patterns[0].evidence) == 4
        assert patterns[0].confidence == pytest.approx(InferenceConfidence.PHRASE_CAP)

    def test_no_match_returns_empty(self, service: EntityInferenceService) -> None:
        assert service._detect_phrase_patterns("watering the garden") == []


# ---------------------------------------------------------------------------
# _detect_contextual_patterns
# ---------------------------------------------------------------------------


class TestDetectContextualPatterns:
    """Integration and learning contextual signals."""

    def test_integration_words_detect_architecture_integration(
        self, service: EntityInferenceService
    ) -> None:
        patterns = service._detect_contextual_patterns("Integrate the two systems", "")

        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.pattern_type == "contextual_integration"
        assert pattern.knowledge_uid == "ku.architecture.integration"
        assert pattern.confidence == pytest.approx(ConfidenceLevel.MEDIUM)
        assert pattern.domain == "architecture"

    def test_learning_words_detect_self_directed_learning(
        self, service: EntityInferenceService
    ) -> None:
        patterns = service._detect_contextual_patterns("Study the material", "")

        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.pattern_type == "contextual_learning"
        assert pattern.knowledge_uid == "ku.learning.self_directed"
        assert pattern.confidence == pytest.approx(ConfidenceLevel.LOW)
        assert pattern.domain == "learning"

    def test_both_contexts_yield_two_patterns(self, service: EntityInferenceService) -> None:
        patterns = service._detect_contextual_patterns("Connect the parts", "then study them")

        assert len(patterns) == 2
        pattern_types = {p.pattern_type for p in patterns}
        assert pattern_types == {"contextual_integration", "contextual_learning"}

    def test_description_alone_can_trigger_detection(self, service: EntityInferenceService) -> None:
        patterns = service._detect_contextual_patterns("Do the thing", "merge both halves")

        assert len(patterns) == 1
        assert patterns[0].pattern_type == "contextual_integration"

    def test_neither_context_returns_empty(self, service: EntityInferenceService) -> None:
        assert service._detect_contextual_patterns("Water the plants", "daily chore") == []


# ---------------------------------------------------------------------------
# _detect_complexity_patterns
# ---------------------------------------------------------------------------


class TestDetectComplexityPatterns:
    """Depth-keyword complexity detection."""

    def test_depth_keyword_detects_complexity_pattern(
        self, service: EntityInferenceService
    ) -> None:
        patterns = service._detect_complexity_patterns("optimization work ahead")

        assert len(patterns) == 1
        pattern = patterns[0]
        assert pattern.pattern_type == "complexity_based"
        assert pattern.knowledge_uid == "ku.programming.advanced"
        assert pattern.confidence == pytest.approx(ConfidenceLevel.MEDIUM)
        assert pattern.domain == "programming"
        assert pattern.evidence == ["Complexity indicators: optimization"]

    def test_multiple_domains_detected_independently(self, service: EntityInferenceService) -> None:
        patterns = service._detect_complexity_patterns("a distributed vulnerability scan")

        detected_uids = {p.knowledge_uid for p in patterns}
        assert detected_uids == {"ku.architecture.advanced", "ku.security.advanced"}

    def test_no_depth_keywords_returns_empty(self, service: EntityInferenceService) -> None:
        assert service._detect_complexity_patterns("simple everyday errand") == []


# ---------------------------------------------------------------------------
# _merge_similar_patterns
# ---------------------------------------------------------------------------


class TestMergeSimilarPatterns:
    """Same-UID merge: max confidence + MERGE_BOOST (capped), evidence deduped."""

    def test_same_uid_patterns_merge_with_boost(self, service: EntityInferenceService) -> None:
        shared_evidence = "Direct keyword: 'python'"
        first = make_pattern(confidence=0.8, evidence=[shared_evidence])
        second = make_pattern(
            pattern_type="phrase_pattern",
            confidence=0.6,
            evidence=["Phrase pattern: 'python api'", shared_evidence],
        )

        merged = service._merge_similar_patterns([first, second])

        assert len(merged) == 1
        result = merged[0]
        assert result.pattern_type == "merged"
        assert result.contributing_types == ["keyword_enhanced", "phrase_pattern"]
        assert result.source_types == ["keyword_enhanced", "phrase_pattern"]
        assert result.knowledge_uid == "ku.programming.python"
        assert result.confidence == pytest.approx(0.8 + InferenceConfidence.MERGE_BOOST)
        # Order-preserving dedup: first pattern's evidence, then new items.
        assert result.evidence == [shared_evidence, "Phrase pattern: 'python api'"]

    def test_merge_boost_is_capped(self, service: EntityInferenceService) -> None:
        first = make_pattern(confidence=0.94, evidence=["e1"])
        second = make_pattern(confidence=0.93, evidence=["e2"])

        merged = service._merge_similar_patterns([first, second])

        assert len(merged) == 1
        assert merged[0].confidence == pytest.approx(InferenceConfidence.MERGE_CAP)
        # Same detector type on both sides — recorded once.
        assert merged[0].contributing_types == ["keyword_enhanced"]

    def test_single_pattern_passes_through_unchanged(self, service: EntityInferenceService) -> None:
        # A lone pattern keeps its detector type (and confidence/evidence),
        # so PATTERN_RELIABILITY and the advanced_features counters see it.
        lone = make_pattern(confidence=0.8, evidence=["only evidence"])

        merged = service._merge_similar_patterns([lone])

        assert merged == [lone]
        assert merged[0].pattern_type == "keyword_enhanced"
        assert merged[0].contributing_types == []
        assert merged[0].source_types == ["keyword_enhanced"]

    def test_distinct_uids_do_not_merge(self, service: EntityInferenceService) -> None:
        first = make_pattern(knowledge_uid="ku.programming.python")
        second = make_pattern(knowledge_uid="ku.devops.docker", domain="devops")

        merged = service._merge_similar_patterns([first, second])

        assert len(merged) == 2
        assert {p.knowledge_uid for p in merged} == {
            "ku.programming.python",
            "ku.devops.docker",
        }

    def test_empty_input_returns_empty(self, service: EntityInferenceService) -> None:
        assert service._merge_similar_patterns([]) == []


# ---------------------------------------------------------------------------
# _calculate_advanced_confidence_score
# ---------------------------------------------------------------------------


class TestCalculateAdvancedConfidenceScore:
    """base + evidence quality + type reliability + domain boost, clamped [0, 1]."""

    def test_base_plus_evidence_plus_reliability(self, service: EntityInferenceService) -> None:
        pattern = make_pattern(pattern_type="phrase_pattern", confidence=0.5, evidence=["a", "b"])

        score = service._calculate_advanced_confidence_score(pattern, {})

        expected = (
            0.5
            + 2 * InferenceConfidence.EVIDENCE_QUALITY_PER_ITEM
            + InferenceConfidence.PATTERN_RELIABILITY["phrase_pattern"]
        )
        assert score == pytest.approx(expected)

    def test_evidence_quality_is_capped(self, service: EntityInferenceService) -> None:
        # 10 evidence items would contribute 0.5 uncapped; cap is EVIDENCE_QUALITY_CAP.
        pattern = make_pattern(
            pattern_type="unknown_type",
            confidence=0.3,
            evidence=[f"e{i}" for i in range(10)],
        )

        score = service._calculate_advanced_confidence_score(pattern, {})

        assert score == pytest.approx(0.3 + InferenceConfidence.EVIDENCE_QUALITY_CAP)

    def test_unknown_pattern_type_gets_zero_reliability(
        self, service: EntityInferenceService
    ) -> None:
        pattern = make_pattern(pattern_type="never_seen_before", confidence=0.4, evidence=["e"])

        score = service._calculate_advanced_confidence_score(pattern, {})

        assert score == pytest.approx(0.4 + InferenceConfidence.EVIDENCE_QUALITY_PER_ITEM)

    def test_domain_expertise_boost_applies_when_domain_matches(
        self, service: EntityInferenceService
    ) -> None:
        pattern = make_pattern(confidence=0.5, evidence=["e"], domain="programming")
        context = {"user_expertise": {"domains": ["programming", "devops"]}}

        score = service._calculate_advanced_confidence_score(pattern, context)

        expected = (
            0.5
            + InferenceConfidence.EVIDENCE_QUALITY_PER_ITEM
            + InferenceConfidence.PATTERN_RELIABILITY["keyword_enhanced"]
            + InferenceConfidence.DOMAIN_EXPERTISE_BOOST
        )
        assert score == pytest.approx(expected)

    def test_no_boost_when_domain_not_in_expertise(self, service: EntityInferenceService) -> None:
        pattern = make_pattern(confidence=0.5, evidence=["e"], domain="programming")
        context = {"user_expertise": {"domains": ["security"]}}

        score = service._calculate_advanced_confidence_score(pattern, context)

        expected = (
            0.5
            + InferenceConfidence.EVIDENCE_QUALITY_PER_ITEM
            + InferenceConfidence.PATTERN_RELIABILITY["keyword_enhanced"]
        )
        assert score == pytest.approx(expected)

    def test_no_boost_when_user_expertise_key_missing(
        self, service: EntityInferenceService
    ) -> None:
        pattern = make_pattern(confidence=0.5, evidence=["e"], domain="programming")

        score = service._calculate_advanced_confidence_score(pattern, {"entity_type": "task"})

        expected = (
            0.5
            + InferenceConfidence.EVIDENCE_QUALITY_PER_ITEM
            + InferenceConfidence.PATTERN_RELIABILITY["keyword_enhanced"]
        )
        assert score == pytest.approx(expected)

    def test_final_score_is_clamped_to_one(self, service: EntityInferenceService) -> None:
        # 0.9 + 0.25 (evidence cap) + 0.15 (merged) + 0.1 (domain) = 1.4 uncapped.
        pattern = make_pattern(
            pattern_type="merged",
            confidence=0.9,
            evidence=[f"e{i}" for i in range(6)],
            domain="programming",
        )
        context = {"user_expertise": {"domains": ["programming"]}}

        score = service._calculate_advanced_confidence_score(pattern, context)

        assert score == pytest.approx(1.0)

    def test_final_score_is_clamped_to_zero(self, service: EntityInferenceService) -> None:
        pattern = make_pattern(pattern_type="unknown_type", confidence=-0.7, evidence=[])

        score = service._calculate_advanced_confidence_score(pattern, {})

        assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _discover_cross_domain_relationships
# ---------------------------------------------------------------------------


class TestDiscoverCrossDomainRelationships:
    """Relationship strength, sorting, and one-sided skips."""

    def test_both_sides_present_creates_relationship(self, service: EntityInferenceService) -> None:
        # Guard: the mapping really exists in the service's own table.
        mapping_key = ("ku.programming.python", "ku.devops.docker")
        assert mapping_key in service.cross_domain_mappings
        mapping = service.cross_domain_mappings[mapping_key]

        python_pattern = make_pattern(knowledge_uid="ku.programming.python", confidence=0.8)
        docker_pattern = make_pattern(
            knowledge_uid="ku.devops.docker", confidence=0.6, domain="devops"
        )

        result = service._discover_cross_domain_relationships([python_pattern, docker_pattern])

        assert result.is_ok
        relationships = result.value
        assert len(relationships) == 1
        rel = relationships[0]
        assert rel.from_knowledge_uid == "ku.programming.python"
        assert rel.to_knowledge_uid == "ku.devops.docker"
        assert rel.from_domain == "programming"
        assert rel.to_domain == "devops"
        assert rel.relationship_type == mapping["type"]
        # strength = mean of the two confidences x mapping strength
        assert rel.strength == pytest.approx((0.8 + 0.6) / 2 * mapping["strength"])
        # Evidence = mapping evidence + one detection line per side.
        assert len(rel.evidence) == len(mapping["evidence"]) + 2

    def test_relationships_sorted_by_strength_descending(
        self, service: EntityInferenceService
    ) -> None:
        db_mapping = service.cross_domain_mappings[("ku.data.database", "ku.ml.data_science")]
        py_mapping = service.cross_domain_mappings[("ku.programming.python", "ku.devops.docker")]

        detected = [
            make_pattern(knowledge_uid="ku.programming.python", confidence=0.8),
            make_pattern(knowledge_uid="ku.devops.docker", confidence=0.6, domain="devops"),
            make_pattern(knowledge_uid="ku.data.database", confidence=0.9, domain="data"),
            make_pattern(knowledge_uid="ku.ml.data_science", confidence=0.9, domain="ml"),
        ]

        result = service._discover_cross_domain_relationships(detected)

        assert result.is_ok
        relationships = result.value
        assert len(relationships) == 2
        assert relationships[0].from_knowledge_uid == "ku.data.database"
        assert relationships[0].strength == pytest.approx(0.9 * db_mapping["strength"])
        assert relationships[1].from_knowledge_uid == "ku.programming.python"
        assert relationships[1].strength == pytest.approx(0.7 * py_mapping["strength"])
        assert relationships[0].strength >= relationships[1].strength

    def test_one_sided_detection_is_skipped(self, service: EntityInferenceService) -> None:
        only_python = [make_pattern(knowledge_uid="ku.programming.python", confidence=0.8)]

        result = service._discover_cross_domain_relationships(only_python)

        assert result.is_ok
        assert result.value == []

    def test_no_patterns_yields_empty_ok_result(self, service: EntityInferenceService) -> None:
        result = service._discover_cross_domain_relationships([])

        assert result.is_ok
        assert result.value == []


# ---------------------------------------------------------------------------
# Basic inference path helpers
# ---------------------------------------------------------------------------


class TestBasicInferenceHelpers:
    """Keyword UID inference, connection scoring, patterns, opportunity count."""

    def test_infer_knowledge_uids_all_four_checks(
        self, basic_service: EntityInferenceService
    ) -> None:
        uids = basic_service._infer_knowledge_uids_from_content(
            "Write python tests", "uses sql and rest"
        )

        assert uids == [
            "ku.programming.python",
            "ku.data.database",
            "ku.programming.api",
            "ku.programming.testing",
        ]

    def test_infer_knowledge_uids_alternate_keywords(
        self, basic_service: EntityInferenceService
    ) -> None:
        # "database" and "api" are the other halves of the OR checks.
        uids = basic_service._infer_knowledge_uids_from_content("Design the database api", "")

        assert uids == ["ku.data.database", "ku.programming.api"]

    def test_infer_knowledge_uids_no_keywords(self, basic_service: EntityInferenceService) -> None:
        assert basic_service._infer_knowledge_uids_from_content("Water the plants", "") == []

    def test_connection_confidence_scores_explicit_beats_inferred(
        self, basic_service: EntityInferenceService
    ) -> None:
        rels = TaskRelationships(
            applies_knowledge_uids=["ku.a"],
            prerequisite_knowledge_uids=["ku.b"],
        )
        inferred = ["ku.a", "ku.c"]  # ku.a already scored explicitly — must not downgrade

        scores = basic_service._calculate_connection_confidence_scores(rels, inferred)

        # 0.95 / 0.90 / 0.60 are inline literals in the source (not constants).
        assert scores["ku.a"] == pytest.approx(0.95)
        assert scores["ku.b"] == pytest.approx(0.90)
        assert scores["ku.c"] == pytest.approx(0.60)
        assert len(scores) == 3

    def test_connection_confidence_scores_empty_inputs(
        self, basic_service: EntityInferenceService
    ) -> None:
        scores = basic_service._calculate_connection_confidence_scores(
            TaskRelationships.empty(), []
        )

        assert scores == {}

    def test_knowledge_bridge_needs_both_lists(self, basic_service: EntityInferenceService) -> None:
        both = TaskRelationships(
            applies_knowledge_uids=["ku.a"],
            prerequisite_knowledge_uids=["ku.b"],
        )
        applies_only = TaskRelationships(applies_knowledge_uids=["ku.a"])
        prereq_only = TaskRelationships(prerequisite_knowledge_uids=["ku.b"])

        assert basic_service._detect_knowledge_patterns(both) == ["knowledge_bridge"]
        assert basic_service._detect_knowledge_patterns(applies_only) == []
        assert basic_service._detect_knowledge_patterns(prereq_only) == []

    def test_knowledge_integration_needs_strictly_more_than_two_applies(
        self, basic_service: EntityInferenceService
    ) -> None:
        two_applies = TaskRelationships(applies_knowledge_uids=["ku.a", "ku.b"])
        three_applies = TaskRelationships(applies_knowledge_uids=["ku.a", "ku.b", "ku.c"])

        assert basic_service._detect_knowledge_patterns(two_applies) == []
        assert basic_service._detect_knowledge_patterns(three_applies) == ["knowledge_integration"]

    def test_both_patterns_together(self, basic_service: EntityInferenceService) -> None:
        rels = TaskRelationships(
            applies_knowledge_uids=["ku.a", "ku.b", "ku.c"],
            prerequisite_knowledge_uids=["ku.d"],
        )

        patterns = basic_service._detect_knowledge_patterns(rels)

        assert patterns == ["knowledge_bridge", "knowledge_integration"]

    def test_count_learning_opportunities(self, basic_service: EntityInferenceService) -> None:
        rels = TaskRelationships(
            applies_knowledge_uids=["ku.a", "ku.b"],
            prerequisite_knowledge_uids=["ku.c"],
            inferred_knowledge_uids=["ku.d"],  # inferred does NOT count
        )

        assert basic_service._count_learning_opportunities(rels) == 3
        assert basic_service._count_learning_opportunities(TaskRelationships.empty()) == 0

    def test_infer_from_content_uses_low_confidence(
        self, basic_service: EntityInferenceService
    ) -> None:
        # Quirk: the source comment says "Medium confidence for keyword matches"
        # but the code assigns ConfidenceLevel.LOW (0.6) — assert actual behavior.
        connections = basic_service._infer_from_content("Deploy python service", "")

        assert len(connections) == 2  # "python" + "deploy" keywords
        for connection in connections:
            assert connection.confidence == pytest.approx(ConfidenceLevel.LOW)
            assert connection.connection_type == "applies"
            assert connection.source == "inferred"


# ---------------------------------------------------------------------------
# enhance_task_dto_with_inference (end-to-end)
# ---------------------------------------------------------------------------


class TestEnhanceTaskDtoWithInference:
    """Full pipeline through both engines with real TaskDTOs."""

    def test_advanced_engine_produces_versioned_result(
        self, service: EntityInferenceService
    ) -> None:
        task = make_task("Learn python asyncio", description="Build a rest api with docker")
        assert task.updated_at is not None  # create_task defaults updated_at to now

        result = service.enhance_task_dto_with_inference(task)

        assert result.is_ok
        inference = result.value
        metadata = inference.knowledge_inference_metadata
        assert metadata is not None
        assert metadata["inference_version"] == "2.4_advanced"
        assert metadata["inference_timestamp"] == task.updated_at.isoformat()

        scores = inference.knowledge_confidence_scores
        assert scores is not None
        # python keyword, docker keyword, rest-api phrase, "learn" contextual.
        assert set(scores) == {
            "ku.programming.python",
            "ku.devops.docker",
            "ku.programming.api",
            "ku.learning.self_directed",
        }
        for score in scores.values():
            assert 0.0 <= score <= 1.0
        assert metadata["algorithm_confidence"] == pytest.approx(max(scores.values()))

        # 4 patterns + 1 cross-domain relationship (python -> docker).
        assert metadata["cross_domain_relationships"] == 1
        assert inference.learning_opportunities_count == 5

        # Each UID here is detected by exactly one algorithm, so every
        # pattern keeps its detector type (no "merged" rewrite).
        assert metadata["patterns_detected"] == [
            "contextual_learning",
            "keyword_enhanced",
            "phrase_pattern",
        ]
        assert metadata["advanced_features"] == {
            "phrase_patterns": 1,  # rest-api phrase
            "contextual_analysis": 1,  # "learn" contextual
            "complexity_detection": 0,
        }

    def test_advanced_engine_with_no_signal_content(self, service: EntityInferenceService) -> None:
        task = make_task("Water the plants")

        result = service.enhance_task_dto_with_inference(task)

        assert result.is_ok
        inference = result.value
        assert inference.knowledge_confidence_scores is None
        assert inference.learning_opportunities_count == 0
        metadata = inference.knowledge_inference_metadata
        assert metadata is not None
        assert metadata["algorithm_confidence"] == pytest.approx(0.0)

    def test_basic_engine_produces_versioned_result(
        self, basic_service: EntityInferenceService
    ) -> None:
        task = make_task("Test the python database layer")

        result = basic_service.enhance_task_dto_with_inference(task)

        assert result.is_ok
        inference = result.value
        metadata = inference.knowledge_inference_metadata
        assert metadata is not None
        assert metadata["inference_version"] == "1.0_basic"

        scores = inference.knowledge_confidence_scores
        assert scores is not None
        assert set(scores) == {
            "ku.programming.python",
            "ku.data.database",
            "ku.programming.testing",
        }
        # Inferred-only connections score 0.60 (inline literal in source).
        for score in scores.values():
            assert score == pytest.approx(0.60)
        # New task -> empty TaskRelationships -> no graph-based opportunities.
        assert inference.learning_opportunities_count == 0
        assert metadata["patterns_detected"] == []


# ---------------------------------------------------------------------------
# analyze_inference_confidence
# ---------------------------------------------------------------------------


class TestAnalyzeInferenceConfidence:
    """Both engine branches of the read-only confidence analysis."""

    def test_advanced_branch_reports_pattern_factors(self, service: EntityInferenceService) -> None:
        result = service.analyze_inference_confidence("python asyncio rest api")

        assert result.is_ok
        analysis = result.value
        assert analysis["engine_type"] == "advanced"
        assert analysis["content_length"] == len("python asyncio rest api")
        assert analysis["word_count"] == 4
        assert analysis["estimated_inferences"] == 2  # python keywords + api phrase
        factors = analysis["confidence_factors"]
        assert set(factors) == {"ku.programming.python", "ku.programming.api"}
        # Singletons keep their detector type through _merge_similar_patterns.
        assert factors["ku.programming.python"]["pattern_type"] == "keyword_enhanced"
        assert factors["ku.programming.api"]["pattern_type"] == "phrase_pattern"
        for factor in factors.values():
            assert 0.0 < factor["confidence"] <= 1.0
            assert factor["evidence_count"] >= 1

    def test_basic_branch_uses_flat_keyword_scan(
        self, basic_service: EntityInferenceService
    ) -> None:
        result = basic_service.analyze_inference_confidence("python and docker")

        assert result.is_ok
        analysis = result.value
        assert analysis["engine_type"] == "basic"
        assert analysis["estimated_inferences"] == 2
        assert analysis["confidence_factors"] == {
            "ku.python": {"confidence": 0.6},
            "ku.docker": {"confidence": 0.6},
        }

    def test_empty_content_yields_zero_inferences(self, service: EntityInferenceService) -> None:
        result = service.analyze_inference_confidence("")

        assert result.is_ok
        analysis = result.value
        assert analysis["estimated_inferences"] == 0
        assert analysis["confidence_factors"] == {}
