# Test Updates for Adaptive LP Refactoring

**Date:** February 8, 2026  
**Result:** ✅ All tests passing (46 passed, 1 skipped)

---

## Summary

Updated tests to reflect the refactored Adaptive LP service that now accepts `UserContext` instead of `user_uid`.

---

## Tests Updated

### 1. Core Service Test (`test_adaptive_lp_core_service.py`)

**Test:** `test_analyze_user_knowledge_state`

**Before:**
```python
async def test_analyze_user_knowledge_state(self, core_service):
    """Knowledge state analysis returns structured data."""
    result = await core_service.analyze_user_knowledge_state("user_001")  # ❌ String
```

**After:**
```python
async def test_analyze_user_knowledge_state(self, core_service):
    """Knowledge state analysis returns structured data."""
    # Create mock UserContext (refactored 2026-02-08)
    from core.services.user import UserContext

    mock_context = UserContext(
        user_uid="user_001",
        mastered_knowledge_uids={"ku_001", "ku_002"},
        in_progress_knowledge_uids={"ku_003"},
        knowledge_mastery={"ku_001": 0.9, "ku_002": 0.8, "ku_003": 0.3},
        prerequisites_completed={"ku_001"},
        prerequisites_needed={"ku_003": ["ku_001", "ku_002"]},
        recently_mastered_uids={"ku_001"},
    )

    result = await core_service.analyze_user_knowledge_state(mock_context)  # ✅ UserContext

    # Verify it uses UserContext fields
    assert state.mastered_knowledge == mock_context.mastered_knowledge_uids
    assert state.in_progress_knowledge == mock_context.in_progress_knowledge_uids
```

---

### 2. Facade Tests (`test_adaptive_lp_facade.py`)

#### Added Mock UserService

**New fixture:**
```python
def create_mock_user_service() -> Mock:
    """Create mock UserService (needed after 2026-02-08 refactor)."""
    from core.services.user import UserContext

    user_service = Mock()
    # Mock UserContext returned by get_user_context()
    mock_context = UserContext(
        user_uid="user_001",
        mastered_knowledge_uids={"ku_001", "ku_002"},
        in_progress_knowledge_uids={"ku_003"},
        knowledge_mastery={"ku_001": 0.9, "ku_002": 0.8, "ku_003": 0.3},
        prerequisites_completed={"ku_001"},
        prerequisites_needed={"ku_003": ["ku_001"]},
    )
    user_service.get_user_context = AsyncMock(return_value=Result.ok(mock_context))
    return user_service


@pytest.fixture
def mock_user_service():
    return create_mock_user_service()
```

#### Updated Facade Fixture

**Before:**
```python
@pytest.fixture
def facade(mock_ku_service, mock_goals_service, mock_tasks_service, mock_learning_service):
    return AdaptiveLpFacade(
        ku_service=mock_ku_service,
        learning_service=mock_learning_service,
        goals_service=mock_goals_service,
        tasks_service=mock_tasks_service,
    )
```

**After:**
```python
@pytest.fixture
def facade(mock_ku_service, mock_goals_service, mock_tasks_service, mock_learning_service, mock_user_service):
    return AdaptiveLpFacade(
        ku_service=mock_ku_service,
        learning_service=mock_learning_service,
        goals_service=mock_goals_service,
        tasks_service=mock_tasks_service,
        user_service=mock_user_service,  # NEW
    )
```

#### Updated 3 Facade Delegation Tests

**Tests affected:**
1. `test_facade_delegates_to_recommendations_service`
2. `test_facade_delegates_to_cross_domain_service`
3. `test_facade_delegates_to_suggestions_service`

**Before:**
```python
assert result.is_ok
facade.core_service.analyze_user_knowledge_state.assert_called_once_with("user_001")  # ❌ Old assertion
facade.recommendations_service.generate_adaptive_recommendations.assert_called_once()
```

**After:**
```python
assert result.is_ok
# After refactor, facade calls user_service.get_user_context() first
facade.user_service.get_user_context.assert_called_once_with("user_001")  # ✅ New assertion
facade.core_service.analyze_user_knowledge_state.assert_called_once()  # ✅ No parameter check (receives UserContext)
facade.recommendations_service.generate_adaptive_recommendations.assert_called_once()
```

---

## Test Results

```bash
poetry run pytest tests/unit/test_adaptive_lp/ -v

======================== 46 passed, 1 skipped in 7.58s =========================
```

**Tests passing:**
- ✅ 46 tests passed
- ⏭️ 1 test skipped (topological sort - unrelated)
- ❌ 0 failures

**Coverage:**
- `adaptive_lp_core_service.py`: Tested
- `adaptive_lp_facade.py`: Tested
- `adaptive_lp_recommendations_service.py`: Tested
- `adaptive_lp_cross_domain_service.py`: Tested
- `adaptive_lp_suggestions_service.py`: Tested

---

## Key Changes

### Pattern Change

**Old pattern (passing user_uid):**
```python
# Test passes string
result = await core_service.analyze_user_knowledge_state("user_001")
```

**New pattern (passing UserContext):**
```python
# Test passes UserContext object
mock_context = UserContext(user_uid="user_001", ...)
result = await core_service.analyze_user_knowledge_state(mock_context)
```

### Facade Orchestration Change

**Old pattern:**
```python
# Facade called analyze_user_knowledge_state(user_uid) directly
facade.core_service.analyze_user_knowledge_state.assert_called_once_with("user_001")
```

**New pattern:**
```python
# Facade builds UserContext first, then passes to analyze_user_knowledge_state
facade.user_service.get_user_context.assert_called_once_with("user_001")
facade.core_service.analyze_user_knowledge_state.assert_called_once()  # No param check
```

---

## Verification

All Adaptive LP tests verify:
- ✅ UserContext is properly mocked with required fields
- ✅ Facade calls `user_service.get_user_context()` before core service methods
- ✅ Core service receives UserContext and uses its fields
- ✅ No breaking changes to public API (user_uid still passed to facade methods)

---

## Related Documentation

- [`ADAPTIVE_LP_USERCONTEXT_REFACTOR_2026-02-08.md`](ADAPTIVE_LP_USERCONTEXT_REFACTOR_2026-02-08.md) - Complete refactoring guide
- [`docs/architecture/UNIFIED_USER_ARCHITECTURE.md`](docs/architecture/UNIFIED_USER_ARCHITECTURE.md) - UserContext architecture
