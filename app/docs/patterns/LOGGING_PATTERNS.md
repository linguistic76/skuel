---
title: Logging Patterns
updated: 2026-01-21
category: patterns
related_skills: []
related_docs: []
---

# Logging Patterns

## Core Principle: "Right tool for each context"

SKUEL uses structured logging for production diagnostics while preserving `print()` for appropriate contexts.

| Context | Tool | Why |
|---------|------|-----|
| Production runtime | `logger.*()` | Structured, logged to files, filterable |
| Interactive CLI | `print()` | Direct user communication |
| Docstring examples | `print()` | Pedagogically clear |
| Demo/test blocks | `print()` | Development-only code |

## Logging Infrastructure

**Location:** `core/utils/logging.py`

**Features:**
- Structured logging with `structlog`
- Request correlation context
- Component-specific log levels
- Three log outputs: console, daily rotating file, error-only file

## Usage

### Basic Setup

```python
from core.utils.logging import get_logger

logger = get_logger("skuel.services.tasks")

# Structured logging (preferred)
logger.info("Task created", task_uid=uid, user_uid=user_uid)
logger.error("Task creation failed", error=str(e), task_data=data)
logger.warning("Deprecated method called", method="old_create")
logger.debug("Query executed", query=query, params=params)
```

### Component Logger Names

Use hierarchical names matching the module path:

| Component | Logger Name |
|-----------|-------------|
| Config | `skuel.config` |
| Config validation | `skuel.config.validation` |
| Services | `skuel.services.{domain}` |
| Infrastructure | `skuel.infrastructure.{component}` |
| Adapters | `skuel.adapters.{type}` |
| Routes | `skuel.routes.{domain}` |

### Log Levels

| Level | Use Case |
|-------|----------|
| `DEBUG` | Detailed diagnostic info (queries, internal state) |
| `INFO` | Normal operations (startup, request completion) |
| `WARNING` | Unexpected but handled situations (deprecated usage, retries) |
| `ERROR` | Failures that need attention (validation errors, missing config) |
| `CRITICAL` | System-breaking failures (database unavailable) |

## When to Use Print vs Logger

### Use `logger.*()` for:

```python
# Runtime diagnostics
logger.error("Missing required environment variables", missing=missing)

# Operation results
logger.info("Configuration validation successful")

# Warnings about skipped operations
logger.warning("Constraint already exists", error=str(e))
```

### Keep `print()` for:

```python
# Interactive CLI tools (credential_setup.py)
print("Enter your Neo4j password:")
password = input()

# Docstring examples
"""
Example:
    result = service.get_task("task.123")
    print(result.value.title)  # "My Task"
"""

# Demo blocks (not production code)
if __name__ == "__main__":
    print("Running demo...")
```

## Structured Logging for Exception Blocks

When exception blocks must remain (graceful degradation, internal helpers), use the `extra={}` dict for structured context:

### Standard Pattern

```python
try:
    result = await some_operation()
except Exception as e:
    logger.error(
        "Operation failed - returning default",  # Human-readable message
        extra={
            "user_uid": user_uid,           # Context: who was affected
            "operation": "some_operation",   # Context: what failed
            "error_type": type(e).__name__,  # Standard: exception class
            "error_message": str(e),         # Standard: exception text
        },
    )
    return default_value
```

### Standard Fields

Always include these fields in exception logging:

| Field | Type | Description |
|-------|------|-------------|
| `error_type` | `str` | Exception class name (e.g., `"ValueError"`, `"Neo4jError"`) |
| `error_message` | `str` | String representation of the exception |

Include these context fields when available:

| Field | Type | When to Include |
|-------|------|-----------------|
| `user_uid` | `str` | User-scoped operations |
| `entity_uid` | `str` | Entity-specific operations |
| `operation` | `str` | Named operations |
| `file_path` | `str` | File I/O operations |
| `query` | `str` | Database queries (truncated if long) |

### Examples by Layer

**Service Layer:**
```python
except Exception as e:
    self.logger.error(
        "Failed to calculate alignment - returning 0.0",
        extra={
            "user_uid": user_uid,
            "life_path_uid": life_path_uid,
            "error_type": type(e).__name__,
            "error_message": str(e),
        },
    )
    return 0.0
```

**UI Routes:**
```python
except Exception as e:
    logger.error(
        "Error fetching tasks - returning empty",
        extra={
            "user_uid": user_uid,
            "project": project,
            "status_filter": status_filter,
            "error_type": type(e).__name__,
            "error_message": str(e),
        },
    )
    return []
```

**Ingestion/Batch:**
```python
except Exception as e:
    self.logger.error(
        "Failed to batch update sync metadata",
        extra={
            "batch_size": len(items),
            "error_type": type(e).__name__,
            "error_message": str(e),
        },
    )
    return Result.fail(str(e))
```

### Benefits

1. **Log aggregation**: Filter by `error_type` to find all `ValueError` occurrences
2. **Monitoring**: Create alerts based on specific error types or operations
3. **Debugging**: Full context available without parsing log messages
4. **Consistency**: Standard fields make log analysis predictable

### Anti-Patterns

```python
# ❌ WRONG - String interpolation loses structure
logger.error(f"Failed for user {user_uid}: {e}")

# ❌ WRONG - No context about what failed
logger.error(f"Error: {e}")

# ❌ WRONG - exc_info without structured context
logger.error("Something failed", exc_info=True)

# ✅ CORRECT - Structured with context
logger.error(
    "Failed to process request",
    extra={
        "user_uid": user_uid,
        "error_type": type(e).__name__,
        "error_message": str(e),
    },
    exc_info=True,  # Optional: adds stack trace for debugging
)
```

## Validation Functions Pattern

For validation that may be called from both CLI and production:

```python
from core.utils.logging import get_logger

logger = get_logger("skuel.config.validation")

def log_validation_report(errors: list[str]) -> None:
    """Log validation results (for production use)"""
    if not errors:
        logger.info("Configuration validation successful")
    else:
        logger.error("Configuration validation failed", errors=errors)


def print_validation_report(errors: list[str]) -> None:
    """Print validation results (for CLI/interactive use)"""
    if not errors:
        print("Configuration validation successful")
    else:
        print("Configuration validation failed:")
        for error in errors:
            print(f"  {error}")
```

## Anti-Patterns

### Don't use print for runtime diagnostics

```python
# BAD - bypasses logging infrastructure
def validate_config():
    if missing:
        print(f"Missing: {missing}")  # Lost to stdout
        return False

# GOOD - captured in logs
def validate_config():
    if missing:
        logger.error("Missing config", missing=missing)
        return False
```

### Don't over-log in examples

```python
# BAD - noisy docstrings
"""
Example:
    logger.info("Starting example")
    result = service.get()
    logger.info("Got result", result=result)
"""

# GOOD - clear, simple examples
"""
Example:
    result = service.get()
    print(result.value)  # Shows output clearly
"""
```

## Key Files

| File | Purpose |
|------|---------|
| `core/utils/logging.py` | Logging infrastructure |
| `core/config/validation.py` | Dual validation report pattern |
| `core/config/credential_setup.py` | CLI print usage example |

## Related

- [Error Handling](ERROR_HANDLING.md) - Result[T] pattern and `@safe_event_handler`
- [Error Handling Decorators](error_handling_decorators.md) - `@with_error_handling` and `@safe_event_handler`
- [Linter Rules](linter_rules.md) - SKUEL015 print statement rule
