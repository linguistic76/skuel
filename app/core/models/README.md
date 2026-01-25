# Core Models Directory Structure

## 🏗️ Organization Overview

The models directory is organized into clean, logical groups following the three-tier architecture pattern where appropriate.

## 📁 Directory Structure

### Root Level Files
These files contain shared definitions used across the entire application:

- **`shared_enums.py`** - All shared enumerations (Priority, Status, Domain, etc.)
- **`base_models_consolidated.py`** - Base classes and shared model patterns
- **`type_hints.py`** - Type definitions and hints used throughout the codebase

### 🎯 Three-Tier Domain Models
Each domain follows the three-tier pattern: Request (Pydantic) → DTO (Mutable) → Domain (Immutable)

#### `/task/` - Task Management ✅
- `task.py` - Immutable domain model with business logic
- `task_dto.py` - Data transfer object for database operations
- `task_request.py` - Pydantic models for API validation
- **Enhanced with**: Learning integration, goal tracking, knowledge prerequisites

#### `/event/` - Calendar Events ✅
- `event.py` - Immutable domain model with business logic
- `event_dto.py` - Data transfer object for database operations
- `event_request.py` - Pydantic models for API validation
- **Enhanced with**: Habit reinforcement, knowledge practice, milestone celebration

#### `/goal/` - Goal Management ✅
- `goal.py` - Immutable domain model with business logic
- `goal_dto.py` - Data transfer object for database operations
- `goal_request.py` - Pydantic models for API validation
- **Features**: Milestone tracking, knowledge requirements, habit support

#### `/habit/` - Habit Tracking ✅
- `habit.py` - Immutable domain model with business logic
- `habit_dto.py` - Data transfer object for database operations
- `habit_request.py` - Pydantic models for API validation
- **Features**: Streak tracking, knowledge reinforcement, goal alignment

#### `/principle/` - Core Principles ✅
- `principle.py` - Immutable domain model with business logic
- `principle_dto.py` - Data transfer object for database operations
- `principle_request.py` - Pydantic models for API validation
- **Features**: Alignment tracking, behavioral expressions, goal guidance

#### `/knowledge/` - Knowledge Management ✅
- `knowledge.py` - Immutable domain model with business logic
- `knowledge_dto.py` - Data transfer object for database operations
- `knowledge_request.py` - Pydantic models for API validation
- **Features**: Prerequisites, mastery levels, learning paths

#### `/progress/` - Progress Tracking ✅
- `progress.py` - Immutable domain model with business logic
- `progress_dto.py` - Data transfer object for database operations
- `progress_request.py` - Pydantic models for API validation
- **Features**: Multi-domain tracking, weighted metrics, trend analysis

### 🔧 Utility Directories

#### `/utils/` - Utility Functions
- `uid_utils.py` - UID generation and validation
- `time_utils.py` - Time and date utilities
- `validation_utils.py` - Common validation functions
- `model_utils_refactored.py` - Model helper functions
- `encoder_functions.py` - JSON encoding helpers
- `factory_functions.py` - Factory pattern utilities

#### `/protocols/` - Protocol Definitions
- `graph_protocol.py` - Graph database protocols
- `calendar_protocol.py` - Calendar operation protocols

#### `/relationships/` - Relationship Management
- `relationships.py` - Basic relationship definitions
- `relationship_base.py` - Base relationship classes
- `relationship_graph_native.py` - Neo4j native relationships
- `relationship_validation.py` - Relationship validation logic
- `semantic_relationships.py` - Semantic relationship handling
- `unified_relationships.py` - Unified relationship system

#### `/database/` - Database & Schema
- `schema.py` - Database schema definitions
- `schema_change.py` - Schema migration utilities
- `graph_yaml_models.py` - YAML to graph model conversion
- `ontology_generator.py` - Ontology generation utilities

#### `/query/` - Query Models
- `query_models.py` - Query model definitions
- `query_analysis.py` - Query analysis utilities
- `cypher_template.py` - Cypher query templates

#### `/search/` - Search Models
- `search.py` - Search model definitions

#### `/user/` - User Management
- `user.py` - User domain model
- `user_dto.py` - User data transfer object

#### `/specialized/` - Specialized Models
- `askesis.py` - AI assistant models
- `conversation.py` - Conversation tracking
- `calendar_models.py` - Calendar-specific models
- `learning_unified.py` - Unified learning models

### 📦 Legacy & Backups

#### `/schemas_legacy/` - Legacy Schema Files
Contains old schema files for domains not yet migrated to three-tier:
- Finance models
- Journal models
- Audio transcription models
- Legacy learning schemas

#### `/backups/` - Backup Files
Contains previous versions of models that have been replaced with three-tier architecture.

## 🎨 Architecture Patterns

### Three-Tier Pattern (Current Standard)
```python
# Tier 1: Request (Pydantic) - External validation
class TaskCreateRequest(BaseModel):
    title: str
    due_date: Optional[date]

# Tier 2: DTO (Mutable) - Data transfer
@dataclass
class TaskDTO:
    uid: str
    title: str
    due_date: Optional[date]

# Tier 3: Domain (Immutable) - Business logic
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    due_date: Optional[date]

    def is_overdue(self) -> bool:
        # Business logic here
        return self.due_date < date.today()
```

### Unified Learning Integration
All major domains (Task, Event, Goal, Habit, Principle, Knowledge) are now interconnected:
- Tasks fulfill Goals and apply Knowledge
- Events reinforce Habits and practice Knowledge
- Goals require Knowledge and supporting Habits
- Habits support Goals and reinforce Knowledge
- Principles guide Goals and prioritize Tasks

## 🚀 Migration Status

### ✅ Completed Migrations
- Task → Three-tier with learning integration
- Event → Three-tier with habit integration
- Goal → Three-tier with milestone support
- Habit → Three-tier with streak tracking
- Principle → Three-tier with alignment tracking
- Knowledge → Three-tier with prerequisites
- Progress → Three-tier with multi-domain tracking

### 🔄 Pending Migrations
- Finance → Needs three-tier migration
- Journal → Needs three-tier migration
- Audio Transcription → Needs three-tier migration

## 📝 Usage Guidelines

1. **Always use the three-tier models** for new development
2. **Import from specific subfolders** (e.g., `from core.models.task.task import Task`)
3. **Use shared_enums.py** for all enumeration values
4. **Follow the immutable domain model pattern** for business logic
5. **Keep DTOs mutable** for database operations
6. **Use Request models** for API validation only

## 🔗 Related Documentation

- `/UNIFIED_DOMAIN_ARCHITECTURE.md` - Complete architecture vision
- `/UNIFIED_DOMAIN_IMPLEMENTATION.md` - Implementation details
- `/INTEGRATED_LEARNING_SYSTEM.md` - Learning system integration