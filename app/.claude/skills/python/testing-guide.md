# Python Testing Guide

> **Moved:** This guide has been superseded by the dedicated pytest skill.

## See: `/.claude/skills/pytest/`

The pytest skill provides comprehensive SKUEL testing documentation:

| File | Content |
|------|---------|
| [SKILL.md](../pytest/SKILL.md) | Quick reference, Result[T] patterns, CLI commands |
| [fixtures-reference.md](../pytest/fixtures-reference.md) | SKUEL fixture ecosystem, TestContainers |
| [async-testing.md](../pytest/async-testing.md) | pytest-asyncio patterns, event loops |
| [mocking-patterns.md](../pytest/mocking-patterns.md) | Service factory pattern, mock backends |

## Quick Start

```bash
# Run all tests
uv run pytest

# Unit tests only (fast)
uv run pytest tests/unit/

# Integration tests (requires Docker)
uv run pytest tests/integration/
```

## Key Pattern: Result[T] Testing

```python
@pytest.mark.asyncio
async def test_service_method(service):
    result = await service.get(uid)

    assert result.is_ok  # Check success
    task = result.value  # Access value
    assert task.uid == uid
```

For detailed patterns, fixtures, and mocking - see the pytest skill.
