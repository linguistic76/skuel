# Result Pattern Migration Guide

## Overview

We're migrating from a complex 891-line Result implementation with 37 error categories to a streamlined 300-line version with 6 focused categories. This guide helps you update existing code.

## Key Changes

### 1. Error Categories (37 → 6)

**Old Categories** → **New Category**
```python
# Validation/Input errors
VALIDATION, USER_INPUT, PROCESSING → ErrorCategory.VALIDATION

# Database errors
DATABASE, GRAPH_TRAVERSAL → ErrorCategory.DATABASE

# External services
EXTERNAL_SERVICE, EXTERNAL_API, LLM_PROVIDER,
NETWORK, TIMEOUT, VECTOR_SEARCH → ErrorCategory.INTEGRATION

# Not found
NOT_FOUND → ErrorCategory.NOT_FOUND

# Business logic
BUSINESS_LOGIC, CONFLICT, DOCUMENT_PROCESSING → ErrorCategory.BUSINESS

# System/Infrastructure
INFRASTRUCTURE, CONFIGURATION, DEPENDENCY,
SERVICE_UNAVAILABLE, INTERNAL,
AUTHENTICATION, AUTHORIZATION, RATE_LIMITING → ErrorCategory.SYSTEM
```

### 2. Error Classes (9 classes → 1 ErrorContext)

**Before:**
```python
# Many specific error classes
DatabaseError("Connection failed", query=cypher, host=uri)
ValidationError("Invalid email", field="email")
ServiceError.not_found("User", "user-123")
LlmProviderError("Rate limited", provider="openai")
```

**After:**
```python
# Single ErrorContext with factory methods
Errors.database("connection", "Connection failed", query=cypher, host=uri)
Errors.validation("Invalid email", field="email")
Errors.not_found("User", "user-123")
Errors.integration("openai", "Rate limited", status_code=429)
```

## Migration Patterns

### Pattern 1: Database Errors

**Old:**
```python
from core.utils.result import Result, DatabaseError

result = Result.fail(DatabaseError(
    "Failed to connect to Neo4j",
    query="MATCH (n) RETURN n",
    host="bolt://localhost:7687"
))
```

**New:**
```python
from core.utils.result_simplified import Result, Errors

result = Result.fail(Errors.database(
    operation="connection",
    message="Failed to connect to Neo4j",
    query="MATCH (n) RETURN n",
    host="bolt://localhost:7687"
))
```

### Pattern 2: Validation Errors

**Old:**
```python
from core.utils.result import Result, ValidationError

if not email.contains("@"):
    return Result.fail(ValidationError(
        "Invalid email format",
        field="email",
        value=email
    ))
```

**New:**
```python
from core.utils.result_simplified import Result, Errors

if not email.contains("@"):
    return Result.fail(Errors.validation(
        "Invalid email format",
        field="email",
        value=email,
        user_message="Please enter a valid email address"
    ))
```

### Pattern 3: Not Found Errors

**Old:**
```python
from core.utils.result import Result, ServiceError

result = await repo.get_by_id(uid)
if not result.value:
    return Result.fail(ServiceError.not_found("User", uid))
```

**New:**
```python
from core.utils.result_simplified import Result, Errors

result = await repo.get_by_id(uid)
if not result.value:
    return Result.fail(Errors.not_found("User", uid))
```

### Pattern 4: External Service Errors

**Old:**
```python
from core.utils.result import Result, LlmProviderError, NetworkError

# LLM errors
if response.status == 429:
    return Result.fail(LlmProviderError(
        "Rate limited",
        provider="openai",
        status_code=429
    ))

# Network errors
if timeout:
    return Result.fail(NetworkError("Request timeout", url=api_url))
```

**New:**
```python
from core.utils.result_simplified import Result, Errors

# LLM errors
if response.status == 429:
    return Result.fail(Errors.integration(
        service="openai",
        message="Rate limited",
        status_code=429
    ))

# Network errors
if timeout:
    return Result.fail(Errors.integration(
        service="api",
        message="Request timeout",
        url=api_url
    ))
```

### Pattern 5: Quick Failures

**Old:**
```python
return Result.fail(SkuelError("Something went wrong"))
```

**New:**
```python
# Quick string failures automatically become SYSTEM errors
return Result.fail("Something went wrong")

# Or be more specific
return Result.fail(Errors.system("Something went wrong"))
```

### Pattern 6: Error Handling by Category

**Old:**
```python
if result.is_err:
    error = result.error
    if isinstance(error, ValidationError):
        return Response(400, error.message)
    elif isinstance(error, ServiceError) and error.code == "NOT_FOUND":
        return Response(404, error.message)
    elif isinstance(error, DatabaseError):
        return Response(503, "Service unavailable")
    else:
        return Response(500, "Internal error")
```

**New:**
```python
if result.is_error:
    match result.error.category:
        case ErrorCategory.VALIDATION:
            return Response(400, result.error.user_message)
        case ErrorCategory.NOT_FOUND:
            return Response(404, result.error.user_message)
        case ErrorCategory.DATABASE:
            return Response(503, "Service temporarily unavailable")
        case _:
            return Response(500, "Internal server error")
```

## Automated Migration Script

```python
#!/usr/bin/env python3
"""
Script to help migrate from old Result to new Result pattern.
Run: python migrate_result.py <file_or_directory>
"""

import re
import sys
from pathlib import Path

def migrate_file(filepath: Path):
    """Migrate a single Python file."""
    content = filepath.read_text()
    original = content

    # Update imports
    content = re.sub(
        r'from core\.utils\.result import (.+)',
        lambda m: migrate_imports(m.group(1)),
        content
    )

    # Replace error class instantiations
    patterns = [
        # DatabaseError
        (r'DatabaseError\(([^)]+)\)', r'Errors.database(operation="query", message=\1)'),

        # ValidationError
        (r'ValidationError\(([^)]+)\)', r'Errors.validation(\1)'),

        # ServiceError.not_found
        (r'ServiceError\.not_found\(([^)]+)\)', r'Errors.not_found(\1)'),

        # LlmProviderError
        (r'LlmProviderError\(([^)]+)\)', r'Errors.integration(service="llm", message=\1)'),

        # NetworkError
        (r'NetworkError\(([^)]+)\)', r'Errors.integration(service="network", message=\1)'),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    # Write back if changed
    if content != original:
        filepath.write_text(content)
        print(f"✅ Migrated: {filepath}")
        return True
    return False

def migrate_imports(import_list: str) -> str:
    """Migrate import statements."""
    imports = [i.strip() for i in import_list.split(',')]
    new_imports = []

    for imp in imports:
        if imp == 'Result':
            new_imports.append('Result')
        elif imp in ['DatabaseError', 'ValidationError', 'ServiceError',
                    'LlmProviderError', 'NetworkError']:
            if 'Errors' not in new_imports:
                new_imports.append('Errors')
        elif imp == 'ErrorCategory':
            new_imports.append('ErrorCategory')
        # Skip other error classes

    return f"from core.utils.result_simplified import {', '.join(new_imports)}"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_result.py <file_or_directory>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if path.is_file():
        migrate_file(path)
    elif path.is_dir():
        for py_file in path.rglob("*.py"):
            migrate_file(py_file)
```

## Benefits of Migration

1. **Simpler Codebase**: 891 lines → 300 lines (~66% reduction)
2. **Better Debugging**:
   - Searchable error codes (`DB_CONNECTION`, `VALIDATION_EMAIL`)
   - Automatic source location capture
   - Structured details dict for any context
3. **Clearer Error Handling**: 6 categories map directly to HTTP status codes
4. **User-Friendly**: Separate `message` (for devs) and `user_message` (for UI)
5. **Consistent Patterns**: Single `ErrorContext` class with factory methods

## Testing the Migration

After migrating, test that:

1. **Error Creation Works**:
```python
# Should all create proper ErrorContext
result1 = Result.fail(Errors.validation("Bad input", field="test"))
result2 = Result.fail(Errors.database("connection", "Timeout"))
result3 = Result.fail("Quick failure")  # String shorthand

assert result1.is_error
assert result1.error.category == ErrorCategory.VALIDATION
assert result1.error.code == "VALIDATION_FIELD_TEST"
```

2. **Logging Works**:
```python
result = Result.fail(Errors.database("query", "Failed"))
result.log_if_error("Database operation failed")  # Should log with context
```

3. **Error Handling Works**:
```python
if result.is_error:
    # Should handle all 6 categories appropriately
    match result.error.category:
        case ErrorCategory.VALIDATION: ...
        case ErrorCategory.DATABASE: ...
        # etc
```

## Gradual Migration

You don't need to migrate everything at once:

1. Start by adding `result_simplified.py` alongside existing `result.py`
2. Migrate new code to use simplified version
3. Gradually update existing code as you touch it
4. Once fully migrated, remove old `result.py` and rename simplified version

## Questions?

The new Result pattern is designed to be simpler and more powerful. Key principles:
- **Explicit over implicit**: 6 clear categories
- **Rich context over inheritance**: One ErrorContext with details
- **Debugging over brevity**: Include source location and stack traces
- **User experience**: Separate developer and user messages