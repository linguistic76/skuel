"""Entity text reaches an LLM prompt bounded, field by field.

The domain AI services build a prompt from an entity's stored fields. A field
written through a door with no request model (vault ingestion, a template
spawn) has no length cap, so the bound sits where the text enters the prompt:
``BaseAIService._bounded`` on each field, and a ceiling on the assembled prompt
in ``_generate_insight`` that refuses instead of cutting.

Every prompt-building method of the eight services is exercised here with an
entity whose every text field is far over the bound. The method list is
derived from the service classes, so a new prompt builder is covered on the
day it is written. Runs the real ``LLMService`` over a scripted chat port: the
prompt asserted on is the one the provider would receive.
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date, time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from core.constants import PromptInput
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceUpdateRequest
from core.models.entity import Entity
from core.models.enums import EntityStatus
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest, HabitUpdateRequest
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.principle.principle_request import (
    PrincipleCreateRequest,
    PrincipleUpdateRequest,
)
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.services.base_ai_service import BaseAIService
from core.services.choices.choices_ai_service import ChoicesAIService
from core.services.events.events_ai_service import EventsAIService
from core.services.goals.goals_ai_service import GoalsAIService
from core.services.habits.habits_ai_service import HabitsAIService
from core.services.lp.lp_ai_service import LpAIService
from core.services.principles.principles_ai_service import PrinciplesAIService
from core.services.ps.ps_ai_service import PsAIService
from core.services.tasks.tasks_ai_service import TasksAIService
from core.utils.result_simplified import ErrorCategory, Result
from tests.fixtures.llm_doubles import ScriptedChatCaller, embeddings_double, scripted_llm

if TYPE_CHECKING:
    from pydantic import BaseModel

#: One field's worth of text, far over the bound; words and sentences, so the
#: cut has boundaries to find.
LONG_TEXT = ("A sentence of ordinary words that runs on. " * 1200)[:50_000]

#: Each service, the entity its prompts are built from, and whether its
#: constructor takes the vector-search service.
SERVICES: dict[type[BaseAIService], tuple[Entity, bool]] = {
    TasksAIService: (
        Task(uid="task_1", user_uid="user_1", title="Plan trip", status=EntityStatus.ACTIVE),
        False,
    ),
    GoalsAIService: (Goal(uid="goal_1", user_uid="user_1", title="Run a marathon"), False),
    HabitsAIService: (Habit(uid="habit_1", user_uid="user_1", title="Morning pages"), False),
    EventsAIService: (
        Event(
            uid="event_1",
            user_uid="user_1",
            title="Team retro",
            event_date=date(2026, 10, 5),
            start_time=time(9, 0),
            end_time=time(10, 0),
        ),
        False,
    ),
    ChoicesAIService: (Choice(uid="choice_1", user_uid="user_1", title="Move or stay"), False),
    PrinciplesAIService: (
        Principle(uid="principle_1", user_uid="user_1", title="Tell the truth"),
        False,
    ),
    PsAIService: (PathStep(uid="ps.demo.breath", title="Breath awareness"), True),
    LpAIService: (LearningPath(uid="lp.demo.calm", title="Foundations of calm"), True),
}

_TEXT_FIELD_TYPES = {"<class 'str'>", "str | None"}
_TEXT_TUPLE_TYPE = "tuple[str, ...]"
#: Identity, not prose — and read by nothing a prompt is built from.
_NOT_PROSE = {"uid", "user_uid"}


def _class_name(cls: type) -> str:
    return cls.__name__


def _overlong(entity: Entity) -> Entity:
    """``entity`` with every text field, and every tuple of texts, far over the bound."""
    changes: dict[str, object] = {}
    for field in dataclasses.fields(entity):
        if field.name in _NOT_PROSE:
            continue
        declared = str(field.type)
        if declared in _TEXT_FIELD_TYPES:
            changes[field.name] = LONG_TEXT
        elif declared == _TEXT_TUPLE_TYPE:
            changes[field.name] = (LONG_TEXT, LONG_TEXT, LONG_TEXT)
    if isinstance(entity, Choice):
        changes["options"] = tuple(
            ChoiceOption(uid=f"opt_{n}", title=LONG_TEXT, description=LONG_TEXT) for n in range(3)
        )
    return dataclasses.replace(entity, **changes)


def _prompt_methods(service_class: type[BaseAIService]) -> list[str]:
    """The service's own coroutine methods that hand a prompt to ``_generate_insight``."""
    return [
        name
        for name, member in vars(service_class).items()
        if inspect.iscoroutinefunction(member)
        and not name.startswith("_")
        and "_generate_insight(" in inspect.getsource(member)
    ]


PROMPT_BUILDERS = [
    pytest.param(service_class, method, id=f"{service_class.__name__}.{method}")
    for service_class in SERVICES
    for method in _prompt_methods(service_class)
]


def _service(
    service_class: type[BaseAIService], entity: Entity
) -> tuple[BaseAIService, ScriptedChatCaller]:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(entity))
    llm = scripted_llm("An answer.")
    assert isinstance(llm.caller, ScriptedChatCaller)
    extras = {"vector_search": MagicMock()} if SERVICES[service_class][1] else {}
    service = service_class(
        backend=backend, llm_service=llm, embeddings_service=embeddings_double(), **extras
    )
    return service, llm.caller


async def _prompt_sent(service_class: type[BaseAIService], method: str, entity: Entity) -> str:
    service, caller = _service(service_class, entity)
    await getattr(service, method)(entity.uid)
    assert len(caller.calls) == 1, "the method made no LLM call"
    return str(caller.calls[0][-1]["content"])


@pytest.mark.parametrize("service_class", list(SERVICES), ids=_class_name)
def test_every_service_has_prompt_builders_to_cover(service_class: type[BaseAIService]) -> None:
    """The derived list is the coverage — an empty one would pass every case below."""
    assert _prompt_methods(service_class)


@pytest.mark.parametrize(("service_class", "method"), PROMPT_BUILDERS)
@pytest.mark.asyncio
async def test_overlong_fields_leave_the_prompt_under_the_ceiling_with_its_instructions(
    service_class: type[BaseAIService], method: str
) -> None:
    entity, _ = SERVICES[service_class]
    short_prompt = await _prompt_sent(service_class, method, entity)
    instructions = short_prompt.rsplit("\n\n", 1)[-1]

    long_prompt = await _prompt_sent(service_class, method, _overlong(entity))

    assert len(long_prompt) <= PromptInput.PROMPT_MAX_CHARS
    assert long_prompt.endswith(instructions)
    assert LONG_TEXT not in long_prompt


@pytest.mark.asyncio
async def test_a_short_task_prompt_is_the_fields_as_written() -> None:
    task = Task(
        uid="task_1",
        user_uid="user_1",
        title="Plan trip",
        description="Flights, hotel, and a day in Kyoto.",
        status=EntityStatus.ACTIVE,
    )

    insight = await _prompt_sent(TasksAIService, "generate_task_insight", task)
    breakdown = await _prompt_sent(TasksAIService, "generate_task_breakdown", task)

    assert insight.startswith(
        "Context:\ntitle: Plan trip\ndescription: Flights, hotel, and a day in Kyoto.\n"
    )
    assert breakdown == (
        "Break down this task into 5 or fewer actionable subtasks.\n"
        "\n"
        "Task: Plan trip\n"
        "Description: Flights, hotel, and a day in Kyoto.\n"
        "\n"
        "Return only the subtask titles, one per line. Be specific and actionable."
    )


@pytest.mark.asyncio
async def test_a_description_at_the_field_bound_reaches_the_prompt_whole() -> None:
    description = ("word " * 400)[: PromptInput.FIELD_MAX_CHARS]
    assert len(description) == PromptInput.FIELD_MAX_CHARS
    task = Task(uid="task_1", user_uid="user_1", title="Plan trip", description=description)

    prompt = await _prompt_sent(TasksAIService, "generate_task_breakdown", task)

    assert f"Description: {description}\n" in prompt


def test_bounded_cuts_an_overlong_field_and_marks_the_cut() -> None:
    bounded = BaseAIService._bounded(LONG_TEXT)

    assert len(bounded) <= PromptInput.FIELD_MAX_CHARS
    assert bounded.endswith("...")
    assert LONG_TEXT.startswith(bounded.removesuffix("..."))


def test_bounded_renders_a_value_that_is_not_text() -> None:
    assert BaseAIService._bounded(7) == "7"
    assert BaseAIService._bounded(0.5) == "0.5"
    assert BaseAIService._bounded(EntityStatus.ACTIVE) == f"{EntityStatus.ACTIVE}"


@pytest.mark.asyncio
async def test_context_values_are_bounded_one_by_one() -> None:
    service, caller = _service(TasksAIService, SERVICES[TasksAIService][0])

    result = await service._generate_insight(
        "Say something useful.", context={"notes": LONG_TEXT, "streak": 7}
    )

    assert result.is_ok
    prompt = str(caller.calls[0][-1]["content"])
    notes_line, streak_line = prompt.split("\n")[1:3]
    assert notes_line.startswith("notes: A sentence of ordinary words")
    assert len(notes_line) <= len("notes: ") + PromptInput.FIELD_MAX_CHARS
    assert streak_line == "streak: 7"
    assert prompt.endswith("\n\nSay something useful.")


@pytest.mark.asyncio
async def test_a_prompt_over_the_ceiling_is_refused_and_never_sent() -> None:
    service, caller = _service(TasksAIService, SERVICES[TasksAIService][0])

    result = await service._generate_insight("x" * (PromptInput.PROMPT_MAX_CHARS + 1))

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.SYSTEM
    assert error.details["prompt_chars"] == PromptInput.PROMPT_MAX_CHARS + 1
    assert caller.calls == []


@pytest.mark.asyncio
async def test_a_prompt_at_the_ceiling_is_sent() -> None:
    service, caller = _service(TasksAIService, SERVICES[TasksAIService][0])

    result = await service._generate_insight("x" * PromptInput.PROMPT_MAX_CHARS)

    assert result.is_ok
    assert len(caller.calls) == 1


ACTIVITY_REQUEST_MODELS: list[type[BaseModel]] = [
    TaskCreateRequest,
    TaskUpdateRequest,
    GoalCreateRequest,
    GoalUpdateRequest,
    HabitCreateRequest,
    HabitUpdateRequest,
    EventCreateRequest,
    EventUpdateRequest,
    ChoiceCreateRequest,
    ChoiceUpdateRequest,
    PrincipleCreateRequest,
    PrincipleUpdateRequest,
]


def _max_length(model: type[BaseModel], field_name: str) -> int | None:
    for constraint in model.model_fields[field_name].metadata:
        limit = getattr(constraint, "max_length", None)
        if limit is not None:
            return int(limit)
    return None


@pytest.mark.parametrize("model", ACTIVITY_REQUEST_MODELS, ids=_class_name)
def test_request_models_cap_description(model: type[BaseModel]) -> None:
    assert _max_length(model, "description") is not None


@pytest.mark.parametrize("model", ACTIVITY_REQUEST_MODELS, ids=_class_name)
def test_no_request_model_caps_a_text_field_above_the_prompt_field_bound(
    model: type[BaseModel],
) -> None:
    """A field that passed its request model's cap is one a prompt carries whole."""
    text_caps = {
        name: _max_length(model, name)
        for name, field in model.model_fields.items()
        if str(field.annotation) in {"<class 'str'>", "str | None"}
    }
    over = {
        name: cap for name, cap in text_caps.items() if cap and cap > PromptInput.FIELD_MAX_CHARS
    }

    assert over == {}
