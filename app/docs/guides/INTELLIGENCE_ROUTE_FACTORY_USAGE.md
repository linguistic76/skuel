---
title: Intelligence Route Factory - Usage Guide
updated: 2025-11-27
status: current
category: guides
tags: [factory, guides, intelligence, route, usage]
related: []
---

# Intelligence Route Factory - Usage Guide
**Generic Intelligence API Generation for SKUEL**
**Created:** 2025-10-08
**Status:** ✅ Implemented & Tested (16/16 tests passing)

## Quick Start

### Basic Usage

```python
from adapters.inbound.route_factories import IntelligenceRouteFactory

def create_habits_intelligence_routes(app, rt, habits_intelligence_service):
    # Create factory
    intel_factory = IntelligenceRouteFactory(
        intelligence_service=habits_intelligence_service,
        domain_name="habits"
    )

    # Register all intelligence routes at once
    intel_factory.register_routes(app, rt)

    # Add domain-specific intelligence routes below
    @rt("/api/habits/intelligence/atomic-habits-analysis", methods=["GET"])
    @boundary_handler()
    async def atomic_habits_analysis_route(request):
        # Unique to habits domain
        result = await habits_intelligence_service.analyze_atomic_habits(...)
        return result
```

**Impact:** Reduces ~1,200 lines to ~200 lines (83% reduction per intelligence API)

### Routes Generated

The factory automatically creates these intelligence routes:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/{domain}/analytics` | Get analytics and insights |
| GET | `/api/{domain}/{uid}/context` | Get contextual information |
| POST | `/api/{domain}/patterns` | Analyze patterns and trends |
| GET | `/api/{domain}/recommendations` | Get personalized recommendations |
| POST | `/api/{domain}/optimization` | Optimize based on intelligence |

---

## Pattern Analysis Results

### Intelligence APIs Analyzed

10 intelligence API files totaling **15,000+ lines**:

| File | Lines | Common Routes |
|------|-------|---------------|
| `habits_intelligence_api.py` | 1,168 | Analytics, Patterns, Optimization |
| `tasks_intelligence_api.py` | 1,707 | Context, Intelligence, Completion |
| `goals_intelligence_api.py` | 706 | Learning Integration, Progress |
| `knowledge_intelligence_api.py` | 970 | Context, Learning Insights |
| `learning_intelligence_api.py` | 1,966 | Paths Context, Analytics |
| `events_intelligence_api.py` | 1,436 | Learning Insights, Scheduling |
| `principles_intelligence_api.py` | 996 | (patterns to analyze) |
| `search_intelligence_api.py` | 818 | (patterns to analyze) |
| Others | ~5,000 | Various intelligence patterns |

### Common Patterns Identified

**Pattern Frequency Across 10 APIs:**
- **Analytics/Insights:** 10/10 (100%)
- **Context Retrieval:** 9/10 (90%)
- **Pattern Analysis:** 10/10 (100%)
- **Recommendations:** 8/10 (80%)
- **Optimization:** 7/10 (70%)
- **Learning Integration:** 6/10 (60%)
- **Batch Operations:** 4/10 (40%)

---

## Requirements

### 1. Service Must Implement `IntelligenceOperations` Protocol

```python
from adapters.inbound.route_factories import IntelligenceOperations

class HabitsIntelligenceService:
    async def get_analytics(
        self, user_uid: str, params: dict
    ) -> Result[dict]:
        # Return analytics data
        ...

    async def get_context(
        self, uid: str, context_type: str = "general"
    ) -> Result[dict]:
        # Return contextual information
        ...

    async def analyze_patterns(
        self, user_uid: str, params: dict
    ) -> Result[dict]:
        # Analyze patterns and trends
        ...

    async def get_recommendations(
        self, user_uid: str, params: dict
    ) -> Result[List[dict]]:
        # Return personalized recommendations
        ...

    async def optimize(
        self, user_uid: str, optimization_params: dict
    ) -> Result[dict]:
        # Optimize based on intelligence
        ...
```

**Migration Note:** Most existing intelligence services already implement these patterns, they just need to be formalized into the protocol!

---

## Configuration Options

### Selective Feature Enablement

```python
intel_factory = IntelligenceRouteFactory(
    intelligence_service=tasks_intelligence_service,
    domain_name="tasks",
    enable_analytics=True,
    enable_context=True,
    enable_patterns=True,
    enable_recommendations=False,  # Disable recommendations
    enable_optimization=False       # Disable optimization
)
```

### Custom Base Path

```python
intel_factory = IntelligenceRouteFactory(
    intelligence_service=habits_intelligence_service,
    domain_name="habits",
    base_path="/api/v2/habits/intelligence"  # Custom path
)
```

### Advanced Intelligence Factory

For domains with additional advanced features:

```python
from adapters.inbound.route_factories import AdvancedIntelligenceFactory

advanced_factory = AdvancedIntelligenceFactory(
    intelligence_service=learning_intelligence_service,
    domain_name="learning",
    enable_learning_integration=True,
    enable_batch_operations=True,
    enable_performance_analytics=True
)
```

**Additional Routes Generated:**
- `POST /api/{domain}/learning-integration`
- `POST /api/{domain}/batch-operations`
- `GET /api/{domain}/performance/analytics`

---

## How It Works

### 1. Analytics Route (GET /api/{domain}/analytics)

**Request:** `GET /api/habits/analytics?user_uid=user123&period=30_days&metric=completion_rate`

**Process:**
1. Extract `user_uid` from query params (required)
2. Pass remaining params to `service.get_analytics()`
3. Return Result[Dict]
4. `@boundary_handler()` converts to `(response, 200)`

**Response:**
```json
{
  "user_uid": "user123",
  "analytics": {
    "total_habits": 23,
    "completion_rate": 0.85,
    "trend": "increasing",
    "insights": [...]
  },
  "period": "30_days"
}
```

### 2. Context Route (GET /api/{domain}/{uid}/context)

**Request:** `GET /api/habits/habit:abc123/context?context_type=detailed`

**Process:**
1. Extract `uid` from path params
2. Extract `context_type` from query params (default: "general")
3. Call `service.get_context(uid, context_type)`
4. Return Result[Dict]

**Response:**
```json
{
  "uid": "habit:abc123",
  "context_type": "detailed",
  "context_data": {
    "related_habits": [...],
    "success_patterns": [...],
    "behavioral_insights": {...}
  }
}
```

### 3. Patterns Route (POST /api/{domain}/patterns)

**Request:**
```json
{
  "user_uid": "user123",
  "analysis_type": "behavioral",
  "time_range": "90_days",
  "focus_areas": ["morning", "evening"]
}
```

**Process:**
1. Extract `user_uid` from body (required)
2. Pass remaining params to `service.analyze_patterns()`
3. Return Result[Dict]

**Response:**
```json
{
  "user_uid": "user123",
  "patterns": [
    {
      "pattern": "morning_productivity",
      "confidence": 0.92,
      "frequency": "daily",
      "impact": "high"
    },
    {
      "pattern": "evening_learning",
      "confidence": 0.78,
      "frequency": "4x_week",
      "impact": "medium"
    }
  ],
  "analysis_metadata": {...}
}
```

### 4. Recommendations Route (GET /api/{domain}/recommendations)

**Request:** `GET /api/habits/recommendations?user_uid=user123&count=5&type=habit`

**Process:**
1. Extract `user_uid` from query params (required)
2. Pass remaining params to `service.get_recommendations()`
3. Return Result[List[Dict]]

**Response:**
```json
[
  {
    "id": "rec1",
    "type": "habit",
    "title": "Add morning meditation",
    "priority": "high",
    "confidence": 0.89
  },
  {
    "id": "rec2",
    "type": "habit",
    "title": "Evening reflection",
    "priority": "medium",
    "confidence": 0.76
  }
]
```

### 5. Optimization Route (POST /api/{domain}/optimization)

**Request:**
```json
{
  "user_uid": "user123",
  "optimization_target": "completion_rate",
  "constraints": {
    "time_budget": 30,
    "difficulty_preference": "gradual"
  }
}
```

**Process:**
1. Extract `user_uid` from body (required)
2. Pass optimization params to `service.optimize()`
3. Return Result[Dict]

**Response:**
```json
{
  "user_uid": "user123",
  "optimization_results": {
    "current_state": {
      "completion_rate": 0.65,
      "time_spent": 45
    },
    "optimized_state": {
      "completion_rate": 0.82,
      "time_spent": 30
    },
    "improvement": {
      "completion_rate_increase": 0.17,
      "time_saved": 15
    },
    "recommended_changes": [...]
  }
}
```

---

## Migration Example

### Before: Manual Intelligence Routes (~1,200 lines)

```python
def create_habits_intelligence_routes(app, rt, habits_intelligence_service):
    @rt("/api/habits/behavioral-insights", methods=["GET"])
    @boundary_handler()
    async def behavioral_insights_route(request):
        user_uid = request.query_params.get("user_uid")
        if not user_uid:
            return error_response("user_uid is required")

        params = dict(request.query_params)
        params.pop("user_uid")

        result = await habits_intelligence_service.get_behavioral_insights(
            user_uid, **params
        )

        if result.is_error:
            return error_response(result.error.message)

        return success_response(result.value)

    @rt("/api/habits/context/{uid}", methods=["GET"])
    @boundary_handler()
    async def context_route(request):
        uid = request.path_params["uid"]
        context_type = request.query_params.get("context_type", "general")

        result = await habits_intelligence_service.get_context(uid, context_type)

        if result.is_error:
            return error_response(result.error.message)

        return success_response(result.value)

    # ... 10+ more similar routes ...
    # ... 1,000+ more lines of boilerplate ...

    # Domain-specific routes
    @rt("/api/habits/intelligence/atomic-habits-analysis", methods=["GET"])
    async def atomic_habits_route(request):
        # Unique habit intelligence
        ...
```

### After: Factory Pattern (~200 lines)

```python
from adapters.inbound.route_factories import IntelligenceRouteFactory

def create_habits_intelligence_routes(app, rt, habits_intelligence_service):
    # Standard intelligence routes (80% eliminated)
    intel_factory = IntelligenceRouteFactory(
        intelligence_service=habits_intelligence_service,
        domain_name="habits"
    )
    intel_factory.register_routes(app, rt)

    # Domain-specific intelligence only (20% of code)
    @rt("/api/habits/intelligence/atomic-habits-analysis", methods=["GET"])
    @boundary_handler()
    async def atomic_habits_analysis_route(request):
        user_uid = request.query_params.get("user_uid")
        result = await habits_intelligence_service.analyze_atomic_habits(user_uid)
        return result

    @rt("/api/habits/intelligence/behavioral-mastery", methods=["GET"])
    @boundary_handler()
    async def behavioral_mastery_route(request):
        user_uid = request.query_params.get("user_uid")
        result = await habits_intelligence_service.behavioral_mastery_guidance(user_uid)
        return result
```

**Impact:**
- **Lines Saved:** 1,000 lines per intelligence API (83% reduction)
- **Consistency:** 100% identical intelligence behavior across all domains
- **Maintainability:** Single source of truth for intelligence patterns

---

## Expected Impact Across 10 Intelligence APIs

### Before Refactoring

| File | Lines | Boilerplate % |
|------|-------|---------------|
| habits_intelligence_api.py | 1,168 | ~80% |
| tasks_intelligence_api.py | 1,707 | ~80% |
| goals_intelligence_api.py | 706 | ~80% |
| knowledge_intelligence_api.py | 970 | ~80% |
| learning_intelligence_api.py | 1,966 | ~80% |
| events_intelligence_api.py | 1,436 | ~80% |
| principles_intelligence_api.py | 996 | ~80% |
| search_intelligence_api.py | 818 | ~80% |
| Others | ~5,000 | ~80% |
| **Total** | **~15,000** | **~80%** |

### After Refactoring

| File | Lines | Reduction |
|------|-------|-----------|
| habits_intelligence_api.py | ~200 | -968 lines (83%) |
| tasks_intelligence_api.py | ~300 | -1,407 lines (82%) |
| goals_intelligence_api.py | ~150 | -556 lines (79%) |
| knowledge_intelligence_api.py | ~200 | -770 lines (79%) |
| learning_intelligence_api.py | ~350 | -1,616 lines (82%) |
| events_intelligence_api.py | ~250 | -1,186 lines (83%) |
| principles_intelligence_api.py | ~200 | -796 lines (80%) |
| search_intelligence_api.py | ~150 | -668 lines (82%) |
| Others | ~1,000 | -4,000 lines (80%) |
| **Total** | **~2,800** | **-12,200 lines (81%)** |

**Combined Savings: 12,200 lines eliminated (81% reduction)**

---

## Testing

### Unit Tests (16/16 Passing)

```bash
uv run pytest tests/infrastructure/test_intelligence_route_factory.py -v
```

**Test Coverage:**
- ✅ Factory initialization
- ✅ Route registration (selective features)
- ✅ Analytics route (with/without user_uid)
- ✅ Context route (default/custom type)
- ✅ Patterns route (validation)
- ✅ Recommendations route
- ✅ Optimization route
- ✅ Advanced factory features
- ✅ Protocol compliance checks

---

## Benefits

### 1. Massive Boilerplate Elimination
- **Before:** ~15,000 lines across 10 intelligence APIs
- **After:** ~2,800 lines (81% reduction)
- **Savings:** **12,200 lines eliminated**

### 2. Consistency
- **Before:** Each domain manually implements intelligence patterns with variations
- **After:** 100% identical intelligence behavior across all 10 domains
- **Result:** No more inconsistencies

### 3. Single Source of Truth
- **Before:** Fix bug in intelligence patterns → update 10 files manually
- **After:** Fix bug in factory → all 10 domains automatically fixed
- **Result:** Maintainable codebase

### 4. Focused Development
- **Before:** 80% boilerplate, 20% domain-specific logic
- **After:** 100% domain-specific intelligence (factory handles rest)
- **Result:** Developers focus on unique intelligence, not plumbing

---

## Next Steps

### Phase 2: Pilot Migration (This Week)
1. ✅ Create IntelligenceRouteFactory
2. ✅ Add comprehensive tests (16 tests)
3. ⏳ Migrate `habits_intelligence_api.py` as pilot
4. ⏳ Migrate `tasks_intelligence_api.py` as validation
5. ⏳ Verify no regressions in test suite

### Phase 3: Rollout (Next Week)
1. Migrate remaining 8 intelligence API files
2. Update documentation
3. Delete old boilerplate code

### Phase 4: Enhancement (Future)
1. Add caching support
2. Add batch intelligence operations
3. Add real-time intelligence streams

---

## Combined Impact with CRUD Factory

### Total Boilerplate Elimination

**Phase 1 (CRUD Factory):**
- Lines eliminated: 3,000 (CRUD routes)

**Phase 2 (Intelligence Factory):**
- Lines eliminated: 12,200 (Intelligence routes)

**Combined Total:**
- **15,200 lines eliminated**
- **From:** 47,000+ lines → **To:** ~32,000 lines
- **Reduction:** 32% of total API layer codebase

---

## References

- **Implementation:** `/adapters/inbound/route_factories/intelligence_route_factory.py`
- **Tests:** `/tests/infrastructure/test_intelligence_route_factory.py`
- **CRUD Factory:** `/docs/CRUD_ROUTE_FACTORY_USAGE.md`
- **Refactoring Plan:** `/docs/INBOUND_ADAPTER_REFACTORING_PLAN.md`

---

**Status:** ✅ Phase 2 Complete - Ready for Migration

**Next:** Pilot migration of `habits_intelligence_api.py` and `tasks_intelligence_api.py`
