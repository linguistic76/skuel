"""
SKUEL DSL Module
================

Domain-Specific Language for parsing Activity Lines from journal text
with **type-safe EntityType/NonKuDomain contexts**.

This module provides the bridge from freeform journal input to structured
SKUEL entities across all SKUEL domains AND semantic knowledge graph connections.

**Domains:**
- Activity Domains (6): Tasks, Habits, Goals, Events, Principles, Choices
- Curriculum Domains (3): KnowledgeUnit (KU), LearningStep (LS), LearningPath (LP)
- Non-Ku Domains: Finance, Calendar, Learning (modifier)
- Content Processing: Report/Assignment
- The Destination (+1): LifePath

**Type Safety (v0.5.0):**

The @context() tag values are now parsed to `EntityType` or `NonKuDomain` enum values:
- `ParsedActivityLine.contexts` is `list[EntityType | NonKuDomain]` instead of `list[str]`
- Compile-time verification of valid entity types
- IDE autocomplete for EntityType/NonKuDomain values
- Clear error messages for invalid context strings

**Key Components:**

- `EntityType`: Enum defining entity @context() values (from entity_enums)
- `NonKuDomain`: Enum defining non-entity @context() values (from entity_enums)
- `ActivityDSLParser`: Main parser class (parses @context tags to EntityType/NonKuDomain)
- `ParsedActivityLine`: Intermediate representation with type-safe contexts
- `ParsedJournal`: Collection of parsed activities from a document
- `LLMDSLBridgeService`: LLM-powered natural text to DSL converter
- `ActivityExtractorService`: Extracts activities and creates entities
- `ActivityEntityConverter`: Converts parsed activities to create requests
- `DSLKnowledgeConnector`: Plans semantic graph connections from DSL tags
- `DSLConnectionExecutor`: Executes planned connections via relationship services

**Usage:**

```python
# === PHASE 1: LLM Bridge (Natural Text -> DSL) ===
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

# === PHASE 2: DSL Parsing (DSL -> ParsedActivities with EntityType/NonKuDomain) ===
from core.services.dsl import (
    ActivityDSLParser,
    parse_activity_line,
    EntityType,
    NonKuDomain,
)

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

# === PHASE 3: Entity Extraction (ParsedActivities -> SKUEL Entities) ===
from core.services.dsl import ActivityExtractorService

extractor = ActivityExtractorService(
    tasks_service=tasks_service,
    habits_service=habits_service,
    ku_service=ku_service,
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
        |
LLMDSLBridgeService.transform()
        |
Text with @context() tags
        |
ActivityDSLParser.parse_journal()
        |
ParsedJournal with EntityType/NonKuDomain contexts (type-safe!)
        |
ActivityExtractorService.extract_and_create()
        |
SKUEL Entities (Tasks, Habits, Goals, KUs, etc.)
        |
DSLKnowledgeConnector.plan_connections()
        |
Graph Relationships (APPLIES_KNOWLEDGE, FULFILLS_GOAL, etc.)
```
"""

# Re-export EntityType and NonKuDomain for convenient access
from core.models.enums.entity_enums import EntityType, NonKuDomain
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
from core.services.dsl.activity_extractor import (
    ActivityExtractionResult,
    ActivityExtractorService,
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
    "GoalConnection",
    # Type Safety - EntityType/NonKuDomain enums for @context() values
    "EntityType",
    "KnowledgeConnection",
    # LLM DSL Bridge
    "LLMDSLBridgeService",
    # Type Safety - NonKuDomain enum for non-Ku @context() values
    "NonKuDomain",
    "ParsedActivityLine",
    "ParsedJournal",
    "PrincipleConnection",
    # Extractor
    "ActivityExtractorService",
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
