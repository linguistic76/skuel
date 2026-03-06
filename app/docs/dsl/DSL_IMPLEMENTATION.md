---
title: SKUEL Activity DSL - Implementation Guide
updated: 2025-11-30
status: current
category: dsl
tags: [dsl, implementation, parser, architecture, regex]
related: [DSL_SPECIFICATION.md, DSL_USAGE_GUIDE.md]
---

# SKUEL Activity DSL - Implementation Guide

*Parser architecture and implementation patterns*
*Last Updated: 2025-11-30*

## Overview

This guide covers how to implement a parser for the SKUEL Activity DSL, including regex patterns, data structures, and Neo4j mapping.

**Implementation Location:** `/core/services/dsl/`

**Key Components:**
- `ActivityDSLParser` - Main parser class
- `ParsedActivityLine` - Structured result dataclass
- `EntityType` enum - Type-safe entity classification
- `ActivityEntityConverter` - DSL → Domain entity conversion

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

**Usage:**
```python
def is_activity_line(line: str) -> bool:
    """Check if line contains @context() tag."""
    return '@context(' in line
```

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
from core.models.enums.entity_enums import EntityType

def parse_context(value: str) -> list[EntityType]:
    """Parse @context() into EntityType list."""
    raw_contexts = [c.strip().lower() for c in value.split(',')]

    entity_types = []
    for ctx in raw_contexts:
        entity_type = EntityType.from_string(ctx)
        if entity_type:
            entity_types.append(entity_type)
        else:
            # Log warning: unknown context type
            pass

    return entity_types
```

**Example:**
```python
parse_context("task, learning")
# Result: [EntityType.TASK, EntityType.LEARNING_STEP]
```

---

### `@when()` Parsing

```python
from datetime import datetime

WHEN_PATTERN_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})')
WHEN_PATTERN_RELAXED = re.compile(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})')

def parse_when(value: str) -> datetime | None:
    """Parse @when() timestamp."""
    # Try ISO format first
    match = WHEN_PATTERN_ISO.match(value)
    if not match:
        match = WHEN_PATTERN_RELAXED.match(value)

    if match:
        year, month, day, hour, minute = map(int, match.groups())
        return datetime(year, month, day, hour, minute)

    return None
```

**Example:**
```python
parse_when("2025-11-30T09:30")
# Result: datetime(2025, 11, 30, 9, 30)
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
parse_ku("ku:teens-yoga/focus-lesson")
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

        # Check if line contains @context()
        if '@context(' not in line:
            return None

        # Extract all tags
        tags = {}
        for match in self.tag_pattern.finditer(line):
            tag_name = match.group(1)
            tag_value = match.group(2)
            tags[tag_name] = tag_value

        # Parse required @context()
        if 'context' not in tags:
            return None

        contexts = self.parse_context(tags['context'])
        if not contexts:
            return None

        # Extract description
        description = self.extract_description(line, tags)

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

### ActivityEntityConverter

```python
from core.services.dsl.activity_converter import ActivityEntityConverter
from core.models.enums.entity_enums import EntityType

class ActivityEntityConverter:
    """Converts ParsedActivityLine to domain create requests."""

    def convert(self, activity: ParsedActivityLine) -> ConversionResult:
        """Convert activity to appropriate domain entity."""

        # Get canonical ku type (first context)
        primary_type = activity.contexts[0] if activity.contexts else None

        if not primary_type:
            return Result.fail(Errors.validation("No context type specified", field="contexts"))

        # Dispatch to appropriate converter
        match primary_type:
            case EntityType.TASK:
                return self._convert_to_task(activity)
            case EntityType.HABIT:
                return self._convert_to_habit(activity)
            case EntityType.GOAL:
                return self._convert_to_goal(activity)
            case EntityType.EVENT:
                return self._convert_to_event(activity)
            case _:
                return self._convert_generic(activity)

    def _convert_to_task(self, activity: ParsedActivityLine) -> TaskCreateRequest:
        """Convert to Task entity."""
        return TaskCreateRequest(
            title=activity.description,
            due_date=activity.when.date() if activity.when else None,
            priority=activity.priority or 3,
            estimated_duration_minutes=activity.duration_minutes,
            energy_requirement=activity.energy_states[0] if activity.energy_states else None,
            # ... map other fields
        )
```

---

## Step 8: Neo4j Mapping

### Graph Schema

```cypher
// Activity Line as base node
CREATE (a:ActivityLine {
  uid: "activity:<hash>",
  description: "...",
  contexts: ["task", "learning"],
  when: datetime("2025-11-30T09:00"),
  priority: 1,
  duration_minutes: 90,
  energy_states: ["focus", "creative"],
  source_file: "2025-11-30.md",
  source_line: 42
})

// Convert to domain entity
CREATE (t:Task {
  uid: "task:<generated>",
  title: "...",
  due_date: date("2025-11-30"),
  priority: 1,
  ...
})

// Link activity line to entity
CREATE (a)-[:CONVERTED_TO]->(t)

// Knowledge connection
MATCH (ku:KnowledgeUnit {uid: "ku:teens-yoga/focus-lesson"})
CREATE (t)-[:APPLIES_KNOWLEDGE]->(ku)

// Goal connection
MATCH (g:Goal {uid: "goal:teens-yoga/20-members"})
CREATE (t)-[:FULFILLS_GOAL]->(g)
```

---

## Testing Strategy

### Unit Tests

```python
def test_parse_context():
    assert parse_context("task") == [EntityType.TASK]
    assert parse_context("task, habit") == [EntityType.TASK, EntityType.HABIT]
    assert parse_context("task,learning") == [EntityType.TASK, EntityType.LEARNING_STEP]

def test_parse_when():
    result = parse_when("2025-11-30T09:30")
    assert result == datetime(2025, 11, 30, 9, 30)

    result = parse_when("2025-11-30 09:30")
    assert result == datetime(2025, 11, 30, 9, 30)

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
    line = """- [ ] Draft lesson
              @context(task,learning)
              @when(2025-11-30T09:00)
              @priority(1)
              @duration(90m)
              @energy(focus,creative)"""

    parser = ActivityDSLParser()
    result = parser.parse_line(line)

    assert result is not None
    assert result.description == "Draft lesson"
    assert EntityType.TASK in result.contexts
    assert EntityType.LEARNING_STEP in result.contexts
    assert result.when == datetime(2025, 11, 30, 9, 0)
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
- **Parser Implementation:** `/core/services/dsl/activity_parser.py`
- **Entity Converter:** `/core/services/dsl/activity_converter.py`
- **EntityType Enum:** `/core/models/enums/entity_enums.py`
