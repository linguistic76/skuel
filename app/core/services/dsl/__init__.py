"""
SKUEL DSL Module
================

Domain-Specific Language for parsing Activity Lines from journal text
with **type-safe EntityType contexts**.

This module provides the bridge from freeform journal input to structured
SKUEL entities across ALL 15 SKUEL domains + 1 destination AND semantic
knowledge graph connections.

**The 15 Domains + 1 Destination:**
- Activity Domains (7): Tasks, Habits, Goals, Events, Principles, Choices, Finance
- Curriculum Domains (3): KnowledgeUnit (KU), LearningStep (LS), LearningPath (LP)
- Meta Domains (3): Assignments, Reports, Calendar
- The Destination (+1): LifePath

**Type Safety (v0.4.0):**

The @context() tag values are now parsed to `EntityType` enum values:
- `ParsedActivityLine.contexts` is `list[EntityType]` instead of `list[str]`
- Compile-time verification of valid entity types
- IDE autocomplete for EntityType values
- Clear error messages for invalid context strings

**Key Components:**

- `EntityType`: Enum defining all valid @context() values (re-exported from shared_enums)
- `ActivityDSLParser`: Main parser class (parses @context tags to EntityType)
- `ParsedActivityLine`: Intermediate representation with type-safe contexts
- `ParsedJournal`: Collection of parsed activities from a document
- `LLMDSLBridgeService`: LLM-powered natural text to DSL converter
- `ReportActivityExtractorService`: Extracts activities and creates entities
- `ActivityEntityConverter`: Converts parsed activities to create requests
- `DSLKnowledgeConnector`: Plans semantic graph connections from DSL tags
- `DSLConnectionExecutor`: Executes planned connections via relationship services

**Usage:**

```python
# === PHASE 1: LLM Bridge (Natural Text → DSL) ===
from core.services.dsl import LLMDSLBridgeService, create_llm_dsl_bridge

bridge = create_llm_dsl_bridge()  # Uses OPENAI_API_KEY from env

# Transform natural text to DSL format
result = await bridge.transform(
    text="I need to finish the report by Friday and start exercising daily.",
    user_uid="user:mike",
)
if result.is_ok:
    dsl_text = result.value.transformed_text
    # - @context(task) Finish the report @when(Friday) @priority(high)
    # - @context(habit) Exercise @repeat(daily)

# === PHASE 2: DSL Parsing (DSL → ParsedActivities with EntityType) ===
from core.services.dsl import ActivityDSLParser, parse_activity_line, EntityType

# Parse single line
result = parse_activity_line("- @context(task) Call mom @priority(high)")
if result.is_ok:
    activity = result.value
    print(activity.description)  # "Call mom"
    print(activity.contexts)  # [EntityType.TASK] - type-safe!

    # Type-safe context checking
    if EntityType.TASK in activity.contexts:
        print("This is a task!")

# Parse full journal
parser = ActivityDSLParser()
result = parser.parse_journal(journal_text)
if result.is_ok:
    for task in result.value.get_tasks():
        print(f"Task: {task.description}")

# === PHASE 3: Entity Extraction (ParsedActivities → SKUEL Entities) ===
from core.services.dsl import ReportActivityExtractorService

extractor = ReportActivityExtractorService(
    tasks_service=tasks_service,
    habits_service=habits_service,
    ku_service=ku_service,  # All 15 domains supported
)
result = await extractor.extract_and_create(assignment, user_uid)

# === PHASE 4: Knowledge Graph Connections ===
from core.services.dsl import DSLKnowledgeConnector, plan_activity_connections

connector = DSLKnowledgeConnector()
plan = connector.plan_connections(activity)
print(f"Will create {plan.total_connections} graph edges")
```

**Complete Pipeline:**

```
Natural Journal Text
        ↓
LLMDSLBridgeService.transform()
        ↓
Text with @context() tags
        ↓
ActivityDSLParser.parse_journal()
        ↓
ParsedJournal with EntityType contexts (type-safe!)
        ↓
ReportActivityExtractorService.extract_and_create()
        ↓
SKUEL Entities (Tasks, Habits, Goals, KUs, etc.)
        ↓
DSLKnowledgeConnector.plan_connections()
        ↓
Graph Relationships (APPLIES_KNOWLEDGE, FULFILLS_GOAL, etc.)
```

Version: 0.4.0 (Type-safe EntityType contexts)
"""

# Re-export EntityType for convenient access
from core.models.enums import EntityType
from core.services.dsl.activity_dsl_parser import (
    ActivityDSLParser,
    ParsedActivityLine,
    ParsedJournal,
    is_activity_line,
    parse_activity_line,
    parse_journal_text,
)
from core.services.dsl.activity_entity_converter import (
    ActivityEntityConverter,
    ConversionResult,
    CreateRequestProtocol,
    TypedConversionResult,
    activity_to_event_dict,
    activity_to_goal_dict,
    activity_to_habit_dict,
    activity_to_task_request,
)
from core.services.dsl.dsl_knowledge_connector import (
    DSLConnectionExecutor,
    DSLConnectionPlan,
    DSLKnowledgeConnector,
    GoalConnection,
    KnowledgeConnection,
    PrincipleConnection,
    plan_activity_connections,
    plan_journal_connections,
)
from core.services.dsl.llm_dsl_bridge import (
    DOMAIN_RECOGNITION_PROMPT,
    DSLTransformResult,
    LLMDSLBridgeService,
    create_llm_dsl_bridge,
)
from core.services.dsl.report_activity_extractor import (
    ActivityExtractionResult,
    ReportActivityExtractorService,
)

__all__ = [
    "DOMAIN_RECOGNITION_PROMPT",
    # Parser
    "ActivityDSLParser",
    # Converter - Protocol-verified conversion
    "ActivityEntityConverter",
    "ActivityExtractionResult",
    "ConversionResult",
    "CreateRequestProtocol",
    "DSLConnectionExecutor",
    "DSLConnectionPlan",
    # Knowledge Graph Connector
    "DSLKnowledgeConnector",
    "DSLTransformResult",
    # Type Safety - EntityType enum for @context() values
    "EntityType",
    "GoalConnection",
    # Extractor
    "ReportActivityExtractorService",
    "KnowledgeConnection",
    # LLM DSL Bridge
    "LLMDSLBridgeService",
    "ParsedActivityLine",
    "ParsedJournal",
    "PrincipleConnection",
    "TypedConversionResult",
    "activity_to_event_dict",
    "activity_to_goal_dict",
    "activity_to_habit_dict",
    "activity_to_task_request",
    "create_llm_dsl_bridge",
    "is_activity_line",
    "parse_activity_line",
    "parse_journal_text",
    "plan_activity_connections",
    "plan_journal_connections",
]
