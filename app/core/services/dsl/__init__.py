"""
SKUEL DSL Module
================

Domain-Specific Language for parsing Activity Lines from freeform text
with **type-safe EntityType/NonKuDomain contexts**.

This module provides the bridge from freeform user input to structured
SKUEL entities across all SKUEL domains.

**Domains:**
- Activity Domains (6): Tasks, Habits, Goals, Events, Principles, Choices
- Curriculum Domains (3): KnowledgeUnit (KU), PathStep (PS), LearningPath (LP)
- Non-Ku Domains: Finance, Calendar, Learning (modifier)
- Content Processing: Report
- The Destination (+1): LifePath

**Type Safety (v0.5.0):**

The @context() tag values are parsed to `EntityType` or `NonKuDomain` enum values:
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
- `activity_to_*` converter functions: ParsedActivityLine → create requests
  (in `activity_domain_converters` / `specialized_domain_converters`)

Graph connections ride the create requests themselves: converters emit link
UIDs (`applies_knowledge_uids`, `fulfills_goal_uid`, `linked_*_uids`) that the
graph-aware create paths persist as edges. There is no separate post-create
connection step.

**Wiring status:** wired (ADR-069). Extraction runs as the
`Pipeline.EXTRACT_ACTIVITIES` branch of `UserEntryProcessingService.process()`
on the unified ingestion path — the original submission-metadata wiring
(retired in ADR-054 Commit 6a) was not resurrected.

**Usage:**

```python
# === PHASE 1: LLM Bridge (Natural Text -> DSL) ===
# The bridge depends only on a ChatCompletionPort; the factory that builds the
# OpenAI chat adapter lives below the boundary (W1 / SKUEL022).
from adapters.external.llm import create_llm_dsl_bridge

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
result = await extractor.extract_and_create(entry, user_uid)
```

**Complete Pipeline:**

```
Natural Text
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
   with graph edges from link UIDs on the create requests
```
"""

# Re-export EntityType and NonKuDomain for convenient access
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.services.dsl.activity_domain_converters import (
    activity_to_choice_request,
    activity_to_event_request,
    activity_to_goal_request,
    activity_to_habit_request,
    activity_to_principle_request,
    activity_to_task_request,
)
from core.services.dsl.activity_dsl_parser import (
    ActivityDSLParser,
    ParsedActivityLine,
    ParsedJournal,
    is_activity_line,
    parse_activity_line,
    parse_journal_text,
)
from core.services.dsl.activity_extractor import (
    ActivityExtractionResult,
    ActivityExtractorService,
)
from core.services.dsl.dsl_mappings import ConversionResult
from core.services.dsl.llm_dsl_bridge import (
    DSLTransformResult,
    LLMDSLBridgeService,
)

__all__ = [
    # Parser
    "ActivityDSLParser",
    "ActivityExtractionResult",
    # Converters - ParsedActivityLine → create requests
    "ConversionResult",
    "DSLTransformResult",
    # Type Safety - EntityType/NonKuDomain enums for @context() values
    "EntityType",
    # LLM DSL Bridge
    "LLMDSLBridgeService",
    # Type Safety - NonKuDomain enum for non-Ku @context() values
    "NonKuDomain",
    "ParsedActivityLine",
    "ParsedJournal",
    # Extractor
    "ActivityExtractorService",
    "activity_to_choice_request",
    "activity_to_event_request",
    "activity_to_goal_request",
    "activity_to_habit_request",
    "activity_to_principle_request",
    "activity_to_task_request",
    "is_activity_line",
    "parse_activity_line",
    "parse_journal_text",
]
