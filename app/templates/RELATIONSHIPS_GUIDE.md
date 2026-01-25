# Relationships Guide for SKUEL

## Overview

The Relationships block in YAML frontmatter allows you to create rich connections between entities in the knowledge graph. This guide explains how to use relationships effectively.

## Quick Start

Add a `Relationships:` block to any YAML frontmatter:

```yaml
Relationships:
  Prerequisites: [Basic Math, Logic]
  Enables: Advanced Topics
  RelatedConcepts: Similar Topics
```

## Relationship Types

### Learning Flow

#### Prerequisites
**What must be understood/completed first**
```yaml
Prerequisites:
  - Python Basics
  - Data Types
```
Direction: `(Prerequisite)-[:REQUIRES]->(This)`

#### Enables
**What this unlocks or makes possible**
```yaml
Enables:
  - Advanced Python
  - Web Development
```
Direction: `(This)-[:ENABLES]->(Enabled)`

### Taxonomic Relationships

#### Broader
**Parent or more general concept**
```yaml
Broader: Programming Languages
```
Direction: `(Broader)-[:HAS_NARROWER]->(This)`

#### Narrower
**Child or more specific concepts**
```yaml
Narrower:
  - Python Functions
  - Python Classes
```
Direction: `(This)-[:HAS_NARROWER]->(Narrower)`

### Lateral Connections

#### RelatedConcepts
**Semantically related topics (bidirectional)**
```yaml
RelatedConcepts:
  - JavaScript
  - Ruby
  - Java
```
Direction: `(This)<-[:RELATED_TO]->(Related)`

### Application Context

#### AppliesTo
**Where this knowledge/skill is applicable**
```yaml
AppliesTo:
  - Web Development
  - Data Science
  - Automation
```
Direction: `(This)-[:APPLIES_TO]->(Domain)`

#### UsedBy
**What systems/components use this**
```yaml
UsedBy:
  - Frontend App
  - API Server
  - Database Layer
```
Direction: `(This)-[:USED_BY]->(User)`

## Format Options

### 1. Single Value
```yaml
Broader: Computer Science
```

### 2. List Format
```yaml
Prerequisites:
  - Item 1
  - Item 2
  - Item 3
```

### 3. Inline Array
```yaml
Enables: [Feature A, Feature B, Feature C]
```

### 4. Comma-Separated
```yaml
RelatedConcepts: Java, Python, Ruby, JavaScript
```

## Entity-Specific Examples

### KnowledgeUnit
```yaml
type: KnowledgeUnit
Relationships:
  Prerequisites: [Variables, Functions]
  Enables: [OOP, Functional Programming]
  Broader: Programming Fundamentals
  Narrower: [Methods, Properties, Inheritance]
  RelatedConcepts: [Design Patterns, Best Practices]
```

### Task
```yaml
type: Task
Relationships:
  Prerequisites: Database Setup
  Enables: [API Development, Testing]
  RelatedConcepts: [REST APIs, GraphQL]
  UsedBy: [Frontend, Mobile App]
```

### Habit
```yaml
type: Habit
Relationships:
  Prerequisites: Basic Knowledge
  Enables: Advanced Skills
  Broader: Professional Development
  AppliesTo: [Daily Work, Projects]
```

### Event
```yaml
type: Event
Relationships:
  Prerequisites: [Preparation Complete, Agenda Set]
  Enables: [Decision Making, Next Steps]
  RelatedConcepts: [Project Planning, Risk Assessment]
```

## Best Practices

### 1. Use Meaningful Names
Instead of UIDs, use descriptive titles:
```yaml
# Good
Prerequisites: Introduction to Programming

# Less Clear
Prerequisites: ku.intro_prog
```

### 2. Keep Relationships Focused
Only add relationships that provide value:
```yaml
# Good - Clear learning path
Prerequisites: [Variables, Control Flow]
Enables: Functions

# Too Broad
RelatedConcepts: [Everything in Computer Science]
```

### 3. Maintain Consistency
Use the same names across files:
```yaml
# File A
Enables: Advanced Python

# File B
Prerequisites: Advanced Python  # Same name
```

### 4. Think About Direction
- Prerequisites point TO this entity
- Enables point FROM this entity
- Broader is above, Narrower is below
- Related is bidirectional

### 5. Progressive Enhancement
Start simple, add relationships over time:
```yaml
# Start with essentials
Prerequisites: Python Basics
Enables: Web Development

# Add more detail later
RelatedConcepts: [Flask, Django]
AppliesTo: [REST APIs, Microservices]
```

## Query Examples

### Find Prerequisites
```cypher
MATCH (n {uid: "ku.python_functions"})-[:REQUIRES]->(prereq)
RETURN prereq.title
```

### Find What Something Enables
```cypher
MATCH (n {uid: "task.setup"})-[:ENABLES]->(enabled)
RETURN enabled.title
```

### Find Related Concepts
```cypher
MATCH (n {uid: "ku.recursion"})-[:RELATED_TO]-(related)
RETURN related.title
```

### Find Taxonomy
```cypher
MATCH (n {uid: "ku.python"})-[:HAS_NARROWER]->(child)
RETURN child.title
```

## Troubleshooting

### Relationships Not Appearing
- Check the Relationships block is properly indented
- Ensure relationship names are spelled correctly
- Verify the file has been synced

### Wrong Direction
- Prerequisites point TO the entity (incoming)
- Enables points FROM the entity (outgoing)
- Check the relationship mapping documentation

### Missing Entities
- Referenced entities that don't exist create stubs
- Stubs are replaced when the actual entity is synced
- Check for typos in entity names

## Migration from Old Format

If you have old prerequisite_uids format:
```yaml
# Old
prerequisite_uids:
  - ku.basic_1
  - ku.basic_2

# New (keep old for compatibility, add new for richness)
prerequisite_uids:
  - ku.basic_1
  - ku.basic_2
Relationships:
  Prerequisites: [Basic Concept 1, Basic Concept 2]
  Enables: Advanced Concepts
```

## Summary

The Relationships system transforms isolated content into a rich, interconnected knowledge graph. Use it to:
- Define learning paths
- Track dependencies
- Connect related concepts
- Build taxonomies
- Enable intelligent recommendations

Start simple with Prerequisites and Enables, then expand as needed!