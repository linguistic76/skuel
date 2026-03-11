"""
Unit Tests for GraphQL Mapper Functions
=======================================

Tests each mapper with minimal protocol-satisfying objects (no Neo4j needed).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from routes.graphql.mappers import (
    knowledge_node_from_dto,
    knowledge_node_from_search_dict,
    learning_path_from_dto,
    learning_step_from_domain,
    task_from_dto,
)
from routes.graphql.types import KnowledgeNode, LearningPath, LearningStep, Task

# --------------------------------------------------------------------------
# Minimal protocol-satisfying stubs
# --------------------------------------------------------------------------


class FakeDomain(StrEnum):
    TECH = "tech"


class FakeStatus(StrEnum):
    ACTIVE = "active"


@dataclass
class FakeKnowledgeNode:
    uid: str = "ku_test_abc"
    title: str = "Test KU"
    summary: str | None = "A summary"
    domain: FakeDomain = FakeDomain.TECH
    tags: list[str] | None = None
    quality_score: float = 0.95


@dataclass
class FakeTask:
    uid: str = "task_test_abc"
    title: str = "Test Task"
    description: str | None = "Task desc"
    status: FakeStatus = FakeStatus.ACTIVE
    priority: str | None = "high"


@dataclass
class FakeLearningPath:
    uid: str = "lp_test_abc"
    title: str = "Test Path"
    description: str | None = "Path desc"
    estimated_hours: float | None = 5.0


@dataclass
class FakeLearningStep:
    uid: str = "ls_test_abc"
    title: str = "Test Step"
    primary_knowledge_uids: tuple[str, ...] = ("ku_primary",)
    mastery_threshold: float = 0.8
    estimated_hours: float = 2.5


# --------------------------------------------------------------------------
# knowledge_node_from_dto
# --------------------------------------------------------------------------


class TestKnowledgeNodeFromDto:
    def test_basic_conversion(self) -> None:
        dto = FakeKnowledgeNode()
        result = knowledge_node_from_dto(dto)

        assert isinstance(result, KnowledgeNode)
        assert result.uid == "ku_test_abc"
        assert result.title == "Test KU"
        assert result.summary == "A summary"
        assert result.domain == "tech"
        assert result.tags == []  # None -> []
        assert result.quality_score == 0.95

    def test_none_summary_becomes_empty_string(self) -> None:
        dto = FakeKnowledgeNode(summary=None)
        result = knowledge_node_from_dto(dto)
        assert result.summary == ""

    def test_tags_preserved(self) -> None:
        dto = FakeKnowledgeNode(tags=["a", "b"])
        result = knowledge_node_from_dto(dto)
        assert result.tags == ["a", "b"]

    def test_zero_quality_score(self) -> None:
        dto = FakeKnowledgeNode(quality_score=0.0)
        result = knowledge_node_from_dto(dto)
        assert result.quality_score == 0.0


# --------------------------------------------------------------------------
# knowledge_node_from_search_dict
# --------------------------------------------------------------------------


class TestKnowledgeNodeFromSearchDict:
    def test_full_dict(self) -> None:
        item = {
            "uid": "ku_s1",
            "title": "Search Result",
            "summary": "Found it",
            "_domain": "science",
            "tags": ["x"],
            "quality_score": 0.7,
        }
        result = knowledge_node_from_search_dict(item)

        assert result.uid == "ku_s1"
        assert result.title == "Search Result"
        assert result.summary == "Found it"
        assert result.domain == "science"
        assert result.tags == ["x"]
        assert result.quality_score == 0.7

    def test_empty_dict_uses_defaults(self) -> None:
        result = knowledge_node_from_search_dict({})

        assert result.uid == ""
        assert result.title == ""
        assert result.summary == ""
        assert result.domain == "knowledge"
        assert result.tags == []
        assert result.quality_score == 0.5

    def test_partial_dict(self) -> None:
        result = knowledge_node_from_search_dict({"uid": "ku_partial", "title": "Partial"})
        assert result.uid == "ku_partial"
        assert result.title == "Partial"
        assert result.domain == "knowledge"  # default


# --------------------------------------------------------------------------
# task_from_dto
# --------------------------------------------------------------------------


class TestTaskFromDto:
    def test_basic_conversion(self) -> None:
        dto = FakeTask()
        result = task_from_dto(dto)

        assert isinstance(result, Task)
        assert result.uid == "task_test_abc"
        assert result.title == "Test Task"
        assert result.description == "Task desc"
        assert result.status == "active"
        assert result.priority == "high"

    def test_none_description_becomes_empty(self) -> None:
        dto = FakeTask(description=None)
        result = task_from_dto(dto)
        assert result.description == ""

    def test_none_priority_becomes_medium(self) -> None:
        dto = FakeTask(priority=None)
        result = task_from_dto(dto)
        assert result.priority == "medium"


# --------------------------------------------------------------------------
# learning_path_from_dto
# --------------------------------------------------------------------------


class TestLearningPathFromDto:
    def test_basic_conversion(self) -> None:
        dto = FakeLearningPath()
        result = learning_path_from_dto(dto)

        assert isinstance(result, LearningPath)
        assert result.uid == "lp_test_abc"
        assert result.name == "Test Path"
        assert result.goal == "Path desc"
        assert result.total_steps == 0  # lazy-loaded
        assert result.estimated_hours == 5.0

    def test_none_description_becomes_empty(self) -> None:
        dto = FakeLearningPath(description=None)
        result = learning_path_from_dto(dto)
        assert result.goal == ""

    def test_none_estimated_hours_becomes_zero(self) -> None:
        dto = FakeLearningPath(estimated_hours=None)
        result = learning_path_from_dto(dto)
        assert result.estimated_hours == 0.0


# --------------------------------------------------------------------------
# learning_step_from_domain
# --------------------------------------------------------------------------


class TestLearningStepFromDomain:
    def test_basic_conversion(self) -> None:
        step = FakeLearningStep()
        result = learning_step_from_domain(step, step_number=3)

        assert isinstance(result, LearningStep)
        assert result.step_number == 3
        assert result.uid == "ls_test_abc"
        assert result.title == "Test Step"
        assert result.knowledge_uid == "ku_primary"
        assert result.mastery_threshold == 0.8
        assert result.estimated_time == 2.5

    def test_empty_primary_knowledge_uids(self) -> None:
        step = FakeLearningStep(primary_knowledge_uids=())
        result = learning_step_from_domain(step, step_number=1)
        assert result.knowledge_uid == ""

    def test_list_primary_knowledge_uids(self) -> None:
        step = FakeLearningStep(primary_knowledge_uids=["ku_a", "ku_b"])
        result = learning_step_from_domain(step, step_number=1)
        assert result.knowledge_uid == "ku_a"
