---
title: SKUEL Activity DSL - Implementation Guide
updated: 2026-07-10
status: current
category: dsl
tags: [dsl, implementation, parser, architecture, regex]
related: [DSL_SPECIFICATION.md, DSL_USAGE_GUIDE.md]
---

# SKUEL Activity DSL - Implementation Guide

*Parser architecture and implementation patterns*
*Last Updated: 2026-07-10*

## Overview

This guide covers how to implement a parser for the SKUEL Activity DSL, including regex patterns, data structures, and Neo4j mapping.

**Implementation Location:** `/core/services/dsl/`

**Key Components:**
- `ActivityDSLParser` - Main parser class
- `ParsedActivityLine` - Structured result dataclass
- `EntityType` enum - Type-safe entity classification
- `activity_to_*` converter functions - DSL → Domain entity conversion

---

## Parsing Strategy

### High-Level Flow

```
1. Detect Activity Lines (contains @context()
2. Extract all tags via regex
3. Validate tag values
4. Build structured ParsedActivityLine object
5. Convert to domain entities (Task, Habit, Goal, etc.)
6. Persist to Neo4j graph
```

---

## Step 1: Activity Line Detection

### Regex Pattern

```python
ACTIVITY_LINE_PATTERN = r'@context\('
```

**Usage** (the live shape — `core/services/dsl/activity_dsl_parser.py`):
```python
def is_activity_line(line: str) -> bool:
    """A real @context() marker — one OUTSIDE Markdown inline code."""
    return has_context_marker(line)          # "@context(" in mask_inline_code(line)
```

`mask_inline_code()` replaces every code span (`` `…` ``, or a run of N backticks
closed by exactly N) with same-length whitespace before the check, so a legend
line such as ``> Events: `- [ ] Description @context(event) …` `` is documentation,
not an Activity Line (DSL_SPECIFICATION § `@context()`, "Literal text is not a
marker" — ruled 2026-08-27 after such a line minted a junk Event). The same mask
feeds tag extraction and description extraction, so a tag-shaped token inside
code is neither a tag nor cut from the description. A span may straddle lines:
`parse_journal` masks the whole document first (`mask_code_spans_in_lines`) and hands
each line's mask to `parse_line`, so a line lying inside such a span is literal for
both doors; `parse_line` on its own masks a line for its own spans only.

**Alternative (stricter):**
```python
import re

ACTIVITY_LINE_PATTERN = re.compile(r'^\s*[-*]\s*\[[ x]\]\s+.*@context\(')

def is_activity_line_strict(line: str) -> bool:
    """Require checkbox syntax."""
    return bool(ACTIVITY_LINE_PATTERN.match(line))
```

---

## Step 2: Tag Extraction

### Generic Tag Regex

```python
TAG_PATTERN = re.compile(r'@([a-zA-Z0-9_]+)\(([^)]*)\)')
```

**Captures:**
- Group 1: Tag identifier (e.g., "context", "when", "priority")
- Group 2: Tag value (everything inside parentheses)

**Usage:**
```python
def extract_tags(line: str) -> dict[str, str]:
    """Extract all tags from activity line."""
    tags = {}
    for match in TAG_PATTERN.finditer(line):
        tag_name = match.group(1)
        tag_value = match.group(2)
        tags[tag_name] = tag_value
    return tags
```

**Example:**
```python
line = "- [ ] Task @context(task) @when(2025-11-30T09:00) @priority(1)"
tags = extract_tags(line)
# Result: {
#   'context': 'task',
#   'when': '2025-11-30T09:00',
#   'priority': '1'
# }
```

---

## Step 3: Tag-Specific Parsing

### `@context()` Parsing

```python
from core.models.enums.entity_enums import EntityType, NonKuDomain

def parse_context(value: str) -> Result[list[EntityType | NonKuDomain]]:
    """Parse @context() against the closed DSL vocabulary (v0.6)."""
    contexts, invalid = [], []
    for ctx in (c.strip().lower() for c in value.split(',')):
        # Resolve: DSL aliases, then EntityType.from_string, then NonKuDomain.
        resolved = resolve(ctx)
        # Strict, closed vocabulary: a typo AND a system-side enum member
        # (e.g. "interaction") both count as invalid — any invalid value
        # fails the WHOLE line with an error listing the 13 valid types.
        if resolved is None or resolved not in _DSL_CONTEXT_VOCABULARY:
            invalid.append(ctx)
        else:
            contexts.append(resolved)
    if invalid:
        return Result.fail(...)  # lists the sanctioned vocabulary
    # `learning` is a modifier — alone it creates nothing, so it also fails.
    if all(c is NonKuDomain.LEARNING for c in contexts):
        return Result.fail(...)
    return Result.ok(contexts)
```

**Example:**
```python
parse_context("task, learning")
# Result.ok([EntityType.TASK, NonKuDomain.LEARNING])

parse_context("task, interaction")
# Result.fail — "interaction" is outside _DSL_CONTEXT_VOCABULARY; whole line fails

parse_context("learning")
# Result.fail — modifier with no base type
```

---

### `@when()` Parsing

```python
from datetime import datetime

WHEN_PATTERN_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})')
WHEN_PATTERN_RELAXED = re.compile(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})')
WHEN_PATTERN_DATE_ONLY = re.compile(r'(\d{4})-(\d{2})-(\d{2})\s*$')

def parse_when(value: str) -> datetime | None:
    """Parse @when() timestamp (impossible dates degrade to None, never raise)."""
    try:
        match = WHEN_PATTERN_ISO.match(value) or WHEN_PATTERN_RELAXED.match(value)
        if match:
            year, month, day, hour, minute = map(int, match.groups())
            return datetime(year, month, day, hour, minute)

        match = WHEN_PATTERN_DATE_ONLY.match(value)
        if match:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day)  # midnight
    except ValueError:
        return None  # impossible calendar date (e.g. 2026-02-31) — drop schedule, keep line

    return None
```

**Example:**
```python
parse_when("2025-11-30T09:30")
# Result: datetime(2025, 11, 30, 9, 30)

parse_when("2025-11-30")
# Result: datetime(2025, 11, 30) — date only (v0.5+)
```

---

### `@priority()` Parsing

```python
def parse_priority(value: str) -> int | None:
    """Parse @priority() value (1-5)."""
    try:
        priority = int(value.strip())
        if 1 <= priority <= 5:
            return priority
    except ValueError:
        pass
    return None
```

---

### `@duration()` Parsing

```python
DURATION_PATTERN = re.compile(r'(?:(\d+)h)?(?:(\d+)m)?')

def parse_duration(value: str) -> int | None:
    """Parse @duration() to minutes."""
    match = DURATION_PATTERN.fullmatch(value)
    if not match:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)

    return hours * 60 + minutes
```

**Examples:**
```python
parse_duration("1h30m")  # → 90
parse_duration("45m")    # → 45
parse_duration("2h")     # → 120
```

---

### `@repeat()` Parsing

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class RepeatPattern:
    type: Literal["daily", "weekly", "monthly", "interval", "custom"]
    days: list[str] | None = None       # For weekly: ["Mon", "Wed"]
    day_numbers: list[int] | None = None  # For monthly: [1, 15]
    interval: int | None = None          # For interval: 3 (days)

REPEAT_DAILY = re.compile(r'^daily$')
REPEAT_WEEKLY = re.compile(r'^weekly:((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:,(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))*)$')
REPEAT_MONTHLY = re.compile(r'^monthly:(\d+(?:,\d+)*)$')
REPEAT_INTERVAL = re.compile(r'^every:(\d+)d$')

def parse_repeat(value: str) -> RepeatPattern | None:
    """Parse @repeat() pattern."""
    value = value.strip()

    if REPEAT_DAILY.match(value):
        return RepeatPattern(type="daily")

    if match := REPEAT_WEEKLY.match(value):
        days = match.group(1).split(',')
        return RepeatPattern(type="weekly", days=days)

    if match := REPEAT_MONTHLY.match(value):
        day_numbers = [int(d) for d in match.group(1).split(',')]
        return RepeatPattern(type="monthly", day_numbers=day_numbers)

    if match := REPEAT_INTERVAL.match(value):
        interval = int(match.group(1))
        return RepeatPattern(type="interval", interval=interval)

    if value == "custom":
        return RepeatPattern(type="custom")

    return None
```

---

### `@energy()` Parsing

```python
def parse_energy(value: str) -> list[str]:
    """Parse @energy() states."""
    return [e.strip().lower() for e in value.split(',') if e.strip()]
```

**Example:**
```python
parse_energy("focus, creative")
# Result: ["focus", "creative"]
```

---

### `@ku()` Parsing

```python
KU_PATTERN = re.compile(r'^ku:([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)$')

def parse_ku(value: str) -> tuple[str, str] | None:
    """Parse @ku() identifier into (namespace, slug)."""
    match = KU_PATTERN.match(value.strip())
    if match:
        namespace = match.group(1)
        slug = match.group(2)
        return (namespace, slug)
    return None
```

**Example:**
```python
parse_ku("ku.teens-yoga/focus-lesson")
# Result: ("teens-yoga", "focus-lesson")
```

---

### `@link()` Parsing

```python
@dataclass
class LinkRef:
    type: str
    id: str

LINK_PATTERN = re.compile(r'([a-zA-Z0-9_-]+):([a-zA-Z0-9_/-]+)')

def parse_link(value: str) -> list[LinkRef]:
    """Parse @link() into list of LinkRef."""
    links = []
    for match in LINK_PATTERN.finditer(value):
        link_type = match.group(1)
        link_id = match.group(2)
        links.append(LinkRef(type=link_type, id=link_id))
    return links
```

**Example:**
```python
parse_link("goal:teens-yoga/10-members, principle:discernment-first")
# Result: [
#   LinkRef(type="goal", id="teens-yoga/10-members"),
#   LinkRef(type="principle", id="discernment-first")
# ]
```

---

## Step 4: Description Extraction

```python
def extract_description(line: str, tags: dict[str, str]) -> str:
    """Extract human-readable description by removing tags."""
    # Remove leading checkbox syntax
    line = re.sub(r'^\s*[-*]\s*\[[ x]\]\s*', '', line)

    # Remove all tags
    for tag_name, tag_value in tags.items():
        tag_pattern = f'@{tag_name}\\({re.escape(tag_value)}\\)'
        line = re.sub(tag_pattern, '', line)

    # Clean up whitespace
    return line.strip()
```

**Example:**
```python
line = "- [ ] Draft lesson @context(task) @when(2025-11-30T09:00)"
tags = extract_tags(line)
desc = extract_description(line, tags)
# Result: "Draft lesson"
```

---

## Step 5: Structured Data Model

### ParsedActivityLine Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime
from core.models.enums.entity_enums import EntityType

@dataclass
class ParsedActivityLine:
    """Structured representation of parsed Activity Line."""

    # Required
    description: str
    contexts: list[EntityType]

    # Optional temporal
    when: datetime | None = None
    duration_minutes: int | None = None
    repeat: RepeatPattern | None = None

    # Optional classification
    priority: int | None = None
    energy_states: list[str] = field(default_factory=list)

    # Optional graph connections
    primary_ku: tuple[str, str] | None = None  # (namespace, slug)
    links: list[LinkRef] = field(default_factory=list)

    # Metadata
    source_file: str | None = None
    source_line: int | None = None

    # Dropped-tag-value reports (@when(Friday), @priority(99), ...): value
    # dropped, line kept; extraction surfaces these via the sync warnings.
    tag_warnings: list[str] = field(default_factory=list)

    @property
    def context_values(self) -> list[str]:
        """Get string values of contexts for serialization."""
        return [ctx.value for ctx in self.contexts]
```

---

## Step 6: Complete Parser Implementation

```python
class ActivityDSLParser:
    """Parser for SKUEL Activity DSL."""

    def __init__(self):
        self.tag_pattern = re.compile(r'@([a-zA-Z0-9_]+)\(([^)]*)\)')

    def parse_line(self, line: str, source_file: str | None = None,
                   line_number: int | None = None) -> ParsedActivityLine | None:
        """Parse a single activity line."""

        # Inline code is literal text: blank every code span (same length, so
        # offsets still address the original) and read markers/tags off the mask.
        masked = mask_inline_code(line)          # or the document-level mask
        if '@context(' not in masked:
            return None

        # Extract all tags — from the MASK, so a tag-shaped token inside code is not a tag
        tags = {}
        for match in self.tag_pattern.finditer(masked):
            tag_name = match.group(1)
            tag_value = match.group(2)
            tags[tag_name] = tag_value

        # Parse required @context()
        if 'context' not in tags:
            return None

        contexts = self.parse_context(tags['context'])
        if not contexts:
            return None

        # Extract description — cut out only the tag spans found on the mask, by
        # position, so literal code text stays in the description verbatim
        description = self.extract_description(line, masked)

        # Parse optional tags
        when = self.parse_when(tags.get('when')) if 'when' in tags else None
        priority = self.parse_priority(tags.get('priority')) if 'priority' in tags else None
        duration = self.parse_duration(tags.get('duration')) if 'duration' in tags else None
        repeat = self.parse_repeat(tags.get('repeat')) if 'repeat' in tags else None
        energy_states = self.parse_energy(tags.get('energy')) if 'energy' in tags else []
        primary_ku = self.parse_ku(tags.get('ku')) if 'ku' in tags else None
        links = self.parse_link(tags.get('link')) if 'link' in tags else []

        return ParsedActivityLine(
            description=description,
            contexts=contexts,
            when=when,
            duration_minutes=duration,
            repeat=repeat,
            priority=priority,
            energy_states=energy_states,
            primary_ku=primary_ku,
            links=links,
            source_file=source_file,
            source_line=line_number
        )

    # Individual parsing methods (parse_context, parse_when, etc.) as shown above
```

---

## Step 7: Domain Entity Conversion

### Converter functions

Conversion is per-domain standalone functions, not a dispatch class. Each
`activity_to_*` function guards on its `is_<domain>()` predicate and returns a
`Result[ConversionResult]` (`TaskCreateRequest | dict`):

- `activity_domain_converters.py` — Task, Habit, Goal, Event, Principle, Choice
- `specialized_domain_converters.py` — Finance, KU, PS, LP, Report, Calendar, LifePath

Graph connections ride the create request: link UIDs from `@ku()` / `@link()`
are emitted as request fields (`applies_knowledge_uids`, `fulfills_goal_uid`,
`linked_*_uids`) that the graph-aware create paths persist as edges.

```python
from core.services.dsl.activity_domain_converters import activity_to_task_request

@with_error_handling(error_type="system", operation="activity_to_task_request")
def activity_to_task_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """Convert ParsedActivityLine to TaskCreateRequest (excerpt)."""
    if not activity.is_task():
        return Result.fail(Errors.validation(...))

    # model_validate + INGESTED_NOTE_CONTEXT: past due dates are admissible on
    # this path — historical vault notes must still create their tasks (Arc E,
    # G10). Interactive creation constructs requests without the context and
    # keeps the future-date guard.
    request = TaskCreateRequest.model_validate(
        {
            "title": activity.description,
            "due_date": activity.when.date() if activity.when else None,
            "duration_minutes": activity.duration_minutes or 30,
            "priority": map_dsl_priority_to_enum(activity.priority),
            "status": EntityStatus.DRAFT if not activity.is_checked else EntityStatus.COMPLETED,
            "recurrence_pattern": map_repeat_to_recurrence(activity.repeat_pattern),
            # Knowledge connections
            "applies_knowledge_uids": activity.get_linked_knowledge(),
            # Goal connections
            "fulfills_goal_uid": (
                activity.get_linked_goals()[0] if activity.get_linked_goals() else None
            ),
            "tags": activity.energy_states if activity.energy_states else [],
        },
        context=INGESTED_NOTE_CONTEXT,
    )
    return Result.ok(request)
```

---

## Step 8: Neo4j Mapping

### Graph Schema

There is **no ActivityLine node** — a parsed line is an in-memory intermediate
(`ParsedActivityLine`), never persisted. The extractor creates the domain
entity through its facade (so it gets the full multi-label `:Entity` + domain
treatment), then writes one provenance edge back to the source UserEntry
(ADR-069):

```cypher
// Domain entity created via the facade (TasksService etc.)
(t:Entity:Task {uid: "task_<generated>", title: "...", due_date: date("2025-11-30"), priority: "high", ...})

// Provenance: what line of which entry produced this entity.
// source_line_hash is the SHA-256 of the normalized source line — the
// idempotency key that lets edited notes re-sync without duplicating.
(t)-[:EXTRACTED_FROM {source_line_hash: "...", extracted_at: datetime()}]->(entry:Entity:UserEntry)

// @ku() / @link() ride the create request as fields
// (applies_knowledge_uids, fulfills_goal_uid, ...) and the graph-aware
// create paths persist them as edges:
(t)-[:APPLIES_KNOWLEDGE]->(ku:Entity:Ku)
(t)-[:FULFILLS_GOAL]->(g:Entity:Goal)
```

---

## Testing Strategy

### Unit Tests

```python
def test_parse_context():
    assert parse_context("task") == [EntityType.TASK]
    assert parse_context("task, habit") == [EntityType.TASK, EntityType.HABIT]
    assert parse_context("task,learning") == [EntityType.TASK, NonKuDomain.LEARNING]

def test_parse_when():
    result = parse_when("2025-11-30T09:30")
    assert result == datetime(2025, 11, 30, 9, 30)

    result = parse_when("2025-11-30 09:30")
    assert result == datetime(2025, 11, 30, 9, 30)

    result = parse_when("2025-11-30")  # date only (v0.5+) — midnight
    assert result == datetime(2025, 11, 30)

def test_parse_duration():
    assert parse_duration("1h30m") == 90
    assert parse_duration("45m") == 45
    assert parse_duration("2h") == 120
    assert parse_duration("90m") == 90

def test_parse_repeat():
    result = parse_repeat("daily")
    assert result.type == "daily"

    result = parse_repeat("weekly:Mon,Wed,Fri")
    assert result.type == "weekly"
    assert result.days == ["Mon", "Wed", "Fri"]
```

### Integration Tests

```python
def test_full_activity_line_parsing():
    # An Activity Line is ONE physical line — parse_journal handles each
    # line independently, so tags must live on the same line as the description.
    line = (
        "- [ ] Draft lesson @context(task,learning) @when(2025-11-30T09:00) "
        "@priority(1) @duration(90m) @energy(focus,creative)"
    )

    parser = ActivityDSLParser()
    result = parser.parse_line(line)

    assert result.is_ok
    activity = result.value
    assert activity.description == "Draft lesson"
    assert EntityType.TASK in activity.contexts
    assert NonKuDomain.LEARNING in activity.contexts
    assert activity.when == datetime(2025, 11, 30, 9, 0)
    assert result.priority == 1
    assert result.duration_minutes == 90
    assert "focus" in result.energy_states
    assert "creative" in result.energy_states
```

---

## Performance Considerations

### Optimization Strategies

1. **Compile regex patterns once:**
```python
class ActivityDSLParser:
    TAG_PATTERN = re.compile(r'@([a-zA-Z0-9_]+)\(([^)]*)\)')  # Class-level
```

2. **Batch processing:**
```python
def parse_file(self, file_path: str) -> list[ParsedActivityLine]:
    """Parse all activity lines in a file."""
    activities = []
    with open(file_path) as f:
        for line_num, line in enumerate(f, 1):
            if activity := self.parse_line(line, file_path, line_num):
                activities.append(activity)
    return activities
```

3. **Caching parsed results:**
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def parse_line_cached(self, line: str) -> ParsedActivityLine | None:
    return self.parse_line(line)
```

---

## Error Handling

### Validation Strategies

```python
from core.result import Result, Errors

def parse_line_with_validation(self, line: str) -> Result[ParsedActivityLine]:
    """Parse with Result[T] error handling."""

    if '@context(' not in line:
        return Errors.validation("Line missing required @context() tag")

    tags = self.extract_tags(line)

    if 'context' not in tags:
        return Errors.validation("@context() tag not found")

    contexts = self.parse_context(tags['context'])
    if not contexts:
        return Errors.validation(f"Invalid context values: {tags['context']}")

    # ... continue parsing

    activity = ParsedActivityLine(...)
    return Result.ok(activity)
```

---

## See Also

- **Formal Grammar:** `DSL_SPECIFICATION.md`
- **Usage Examples:** `DSL_USAGE_GUIDE.md`
- **Parser Implementation:** `/core/services/dsl/activity_dsl_parser.py`
- **Entity Converters:** `/core/services/dsl/activity_domain_converters.py` (activity domains), `/core/services/dsl/specialized_domain_converters.py` (curriculum/meta/finance/lifepath), `/core/services/dsl/dsl_mappings.py` (shared mappings)
- **EntityType Enum:** `/core/models/enums/entity_enums.py`
