# LpIntelligenceService - Learning State & Content Intelligence

## Overview

**Architecture:** Extends `BaseAnalyticsService[Any, Lp]` (Facade Pattern)
**Location:** `/core/services/lp_intelligence_service.py`
**Service Name:** `lp.intelligence`
**Lines:** ~1,342 (facade) + ~2,467 (4 sub-services)

---

## Purpose

LpIntelligenceService is a **facade** coordinating four specialized sub-services for comprehensive learning intelligence. It provides learning state analysis, personalized content recommendations, content metadata extraction, and quality assessment through a unified interface. This service maintains backward compatibility while delegating all operations to focused, specialized sub-services.

**Architecture Note:** LpIntelligenceService is **standalone** - it is NOT created by the LpService facade. It must be instantiated independently and injected where needed.

**Sub-Service Architecture:**
```
LpIntelligenceService (Facade - 378 lines)
├── LearningStateAnalyzer (557 lines)
│   └── Learning state assessment, readiness, guidance modes
├── LearningRecommendationEngine (862 lines)
│   └── Content recommendations, path suggestions, interventions
├── ContentAnalyzer (383 lines)
│   └── Content metadata extraction, feature analysis
└── ContentQualityAssessor (442 lines)
    └── Quality scoring, similarity search, feature-based search
```

---

## Core Methods

### Category 1: Learning State Analysis (LearningStateAnalyzer)

#### Method 1: analyze_learning_state()

**Purpose:** Comprehensive analysis of user's current learning state including understanding, engagement, readiness, pedagogical needs, and recommended guidance modes.

**Signature:**
```python
async def analyze_learning_state(
    self,
    user_context: UserContext,
    include_vectors: bool = False
) -> Result[LearningAnalysis]:
```

**Parameters:**
- `user_context` (UserContext) - User's current context with learning history
- `include_vectors` (bool, default=False) - Whether to include vector-based learning style analysis

**Returns:**
```python
LearningAnalysis(
    user_uid="user.mike",
    timestamp=datetime(2026, 1, 8, 10, 0, 0),

    # Current state
    learning_level="intermediate",
    mastery_average=0.65,
    concepts_mastered=23,
    concepts_in_progress=8,
    concepts_needing_review=["ku.python-basics", "ku.fasthtml-intro"],

    # Readiness assessment
    readiness=LearningReadiness.READY_FOR_NEW,
    confidence_score=0.75,

    # Pedagogical analysis
    understanding_level=0.7,
    engagement_level=0.8,
    needs_encouragement=False,
    needs_clarification=False,
    needs_challenge=True,
    needs_break=False,

    # Recommendations
    recommended_guidance=GuidanceMode.CHALLENGE,
    recommended_actions=[
        "Try advanced concepts in Python",
        "Apply knowledge to real projects"
    ],
    focus_areas=["Advanced Python patterns", "FastHTML routing"],

    # Vector analysis (if include_vectors=True)
    learning_style_vector=[0.2, 0.8, ...],  # 384-dim vector
    content_affinity_scores={"code_heavy": 0.85, "theory": 0.45}
)
```

**Example:**
```python
# Basic learning state analysis
result = await lp_intelligence.analyze_learning_state(user_context)

if result.is_ok:
    analysis = result.value
    print(f"Learning level: {analysis.learning_level}")
    print(f"Mastery average: {analysis.mastery_average:.0%}")
    print(f"Readiness: {analysis.readiness.value}")
    print(f"Recommended guidance: {analysis.recommended_guidance.value}")

    if analysis.needs_challenge:
        print("User is ready for more challenging content!")

    print("\nRecommended actions:")
    for action in analysis.recommended_actions:
        print(f"  - {action}")

# With vector analysis (requires embeddings_service)
result = await lp_intelligence.analyze_learning_state(
    user_context,
    include_vectors=True
)

if result.is_ok:
    analysis = result.value
    if analysis.learning_style_vector:
        print(f"Learning style vector: {len(analysis.learning_style_vector)}-dim")
    if analysis.content_affinity_scores:
        print("Content affinities:")
        for content_type, score in analysis.content_affinity_scores.items():
            print(f"  {content_type}: {score:.0%}")
```

**Dependencies:**
- Progress backend (optional - graceful degradation if not available)
- OpenAIEmbeddingsService (optional - required for vector analysis)

**Readiness States:**
- `REVIEW_NEEDED` - User should review previously learned content
- `READY_FOR_NEW` - Ready to learn new concepts
- `CONSOLIDATE` - Should practice and consolidate current knowledge
- `TAKE_BREAK` - Showing signs of fatigue, needs rest
- `CHALLENGE_READY` - Ready for advanced/challenging content

---

### Category 2: Content Recommendations (LearningRecommendationEngine)

#### Method 2: recommend_content()

**Purpose:** Generate intelligent content recommendations based on user's learning state, mastery level, prerequisites, and learning style.

**Signature:**
```python
async def recommend_content(
    self,
    user_context: UserContext,
    content_pool: list[Any],
    limit: int = 10
) -> Result[list[ContentRecommendation]]:
```

**Parameters:**
- `user_context` (UserContext) - User's current context
- `content_pool` (list[Any]) - Available content to recommend from
- `limit` (int, default=10) - Maximum number of recommendations

**Returns:**
```python
[
    ContentRecommendation(
        content_uid="ku.python-advanced",
        content_type="knowledge_unit",
        title="Advanced Python Patterns",
        relevance_score=0.92,
        difficulty_match=0.85,
        prerequisites_met=True,
        learning_impact="high",
        recommendation_reason="Matches your current skill level and interests",
        confidence_score=0.88
    ),
    ...
]
```

**Example:**
```python
# Get all available KUs from backend
all_kus_result = await ku_service.list()
if all_kus_result.is_error:
    return all_kus_result

# Get recommendations
result = await lp_intelligence.recommend_content(
    user_context=user_context,
    content_pool=all_kus_result.value,
    limit=5
)

if result.is_ok:
    recommendations = result.value
    print(f"Top {len(recommendations)} recommendations:\n")

    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec.title}")
        print(f"   Relevance: {rec.relevance_score:.0%}")
        print(f"   Difficulty match: {rec.difficulty_match:.0%}")
        print(f"   Impact: {rec.learning_impact}")
        print(f"   Reason: {rec.recommendation_reason}")
        print(f"   Prerequisites met: {rec.prerequisites_met}\n")
```

**Dependencies:**
- LearningStateAnalyzer (for learning state assessment)
- Learning backend (optional - for content queries)

**Replaces:** `VectorLearningService.get_personalized_recommendations()`

---

#### Method 3: recommend_learning_paths()

**Purpose:** Recommend complete learning paths based on user's goals and current knowledge level.

**Signature:**
```python
async def recommend_learning_paths(
    self,
    user_context: UserContext,
    goal: str | None = None
) -> Result[list[Any]]:
```

**Parameters:**
- `user_context` (UserContext) - User's current context
- `goal` (str, optional) - Specific learning goal (e.g., "become a full-stack developer")

**Returns:**
```python
[
    {
        "path_uid": "lp.python-to-fullstack",
        "title": "Python to Full-Stack Developer",
        "relevance_score": 0.88,
        "estimated_weeks": 12,
        "prerequisites_met": True,
        "step_count": 24,
        "reason": "Builds on your Python knowledge toward full-stack goal"
    },
    ...
]
```

**Example:**
```python
# General path recommendations
result = await lp_intelligence.recommend_learning_paths(user_context)

if result.is_ok:
    paths = result.value
    for path in paths:
        print(f"{path['title']}")
        print(f"  Relevance: {path['relevance_score']:.0%}")
        print(f"  Duration: {path['estimated_weeks']} weeks")
        print(f"  Steps: {path['step_count']}")

# Goal-specific recommendations
result = await lp_intelligence.recommend_learning_paths(
    user_context,
    goal="Master FastHTML web development"
)

if result.is_ok:
    paths = result.value
    print(f"Recommended paths for goal: {len(paths)}")
```

**Dependencies:**
- LearningStateAnalyzer (for state assessment)
- Learning backend (for path queries)

---

#### Method 4: detect_interventions()

**Purpose:** Detect when learning interventions are needed based on user's state and recent activity (e.g., encouragement, clarification, challenge, break).

**Signature:**
```python
async def detect_interventions(
    self,
    user_context: UserContext,
    recent_activity: dict[str, Any] | None = None
) -> Result[list[LearningIntervention]]:
```

**Parameters:**
- `user_context` (UserContext) - User's current context
- `recent_activity` (dict, optional) - Recent learning activity data

**Returns:**
```python
[
    LearningIntervention(
        intervention_type="encouragement",
        priority=0.85,
        message="You're making excellent progress! You've mastered 5 new concepts this week.",
        suggested_action="Keep up the momentum with daily practice",
        estimated_impact="high"
    ),
    LearningIntervention(
        intervention_type="challenge",
        priority=0.7,
        message="You're ready for more advanced content",
        suggested_action="Try the advanced Python patterns module",
        estimated_impact="medium"
    ),
    ...
]
```

**Example:**
```python
result = await lp_intelligence.detect_interventions(user_context)

if result.is_ok:
    interventions = result.value

    # Sort by priority
    interventions.sort(key=lambda x: x.priority, reverse=True)

    print("Learning Interventions (by priority):\n")
    for intervention in interventions:
        print(f"[{intervention.intervention_type.upper()}] Priority: {intervention.priority:.0%}")
        print(f"  Message: {intervention.message}")
        print(f"  Action: {intervention.suggested_action}")
        print(f"  Impact: {intervention.estimated_impact}\n")

# With recent activity context
recent_activity = {
    "sessions_this_week": 3,
    "average_session_minutes": 45,
    "completion_rate": 0.6,
    "struggle_indicators": ["repeated_failures", "long_sessions"]
}

result = await lp_intelligence.detect_interventions(
    user_context,
    recent_activity=recent_activity
)
```

**Dependencies:**
- LearningStateAnalyzer (for state assessment)

**Intervention Types:**
- `encouragement` - Positive reinforcement when doing well
- `clarification` - Offer help when user seems stuck
- `challenge` - Suggest harder content when ready
- `break` - Recommend rest when showing fatigue

**Replaces:** `PedagogicalService.should_intervene()`

---

#### Method 5: optimize_learning_session()

**Purpose:** Optimize a learning session plan based on available time and user's current learning state.

**Signature:**
```python
async def optimize_learning_session(
    self,
    user_context: UserContext,
    available_time_minutes: int
) -> Result[dict[str, Any]]:
```

**Parameters:**
- `user_context` (UserContext) - User's current context
- `available_time_minutes` (int) - Time available for session

**Returns:**
```python
{
    "session_plan": {
        "total_minutes": 60,
        "activities": [
            {
                "type": "review",
                "content_uid": "ku.python-basics",
                "duration_minutes": 15,
                "reason": "Reinforce foundation before new content"
            },
            {
                "type": "new_learning",
                "content_uid": "ku.python-advanced",
                "duration_minutes": 30,
                "reason": "Ready for advanced concepts"
            },
            {
                "type": "practice",
                "content_uid": "task_python_project",
                "duration_minutes": 15,
                "reason": "Apply new knowledge"
            }
        ],
        "expected_outcomes": [
            "Reinforce Python basics",
            "Learn 2-3 advanced patterns",
            "Complete 1 practice project"
        ],
        "difficulty_progression": "gentle_to_challenging",
        "cognitive_load_score": 0.7
    }
}
```

**Example:**
```python
# 30-minute session
result = await lp_intelligence.optimize_learning_session(
    user_context,
    available_time_minutes=30
)

if result.is_ok:
    plan = result.value["session_plan"]
    print(f"Session plan ({plan['total_minutes']} minutes):\n")

    for activity in plan["activities"]:
        print(f"[{activity['duration_minutes']}min] {activity['type']}")
        print(f"  Content: {activity['content_uid']}")
        print(f"  Reason: {activity['reason']}\n")

    print("Expected outcomes:")
    for outcome in plan["expected_outcomes"]:
        print(f"  - {outcome}")

# Extended session (2 hours)
result = await lp_intelligence.optimize_learning_session(
    user_context,
    available_time_minutes=120
)
```

**Dependencies:**
- LearningStateAnalyzer (for state assessment)

**Session Optimization Factors:**
- Current learning state (tired vs. energized)
- Cognitive load balancing
- Review vs. new content ratio
- Difficulty progression (warm-up → challenge → cool-down)
- Prerequisites and knowledge gaps

---

### Category 3: Content Analysis (ContentAnalyzer)

#### Method 6: extract_content_metadata()

**Purpose:** Extract comprehensive metadata from content including keywords, complexity, reading time, and content features.

**Signature:**
```python
async def extract_content_metadata(
    self,
    content: ContentAdapter
) -> Result[ContentMetadata]:
```

**Parameters:**
- `content` (ContentAdapter) - Content to analyze (protocol-based)

**Returns:**
```python
ContentMetadata(
    content_uid="ku.python-advanced",

    # Text analysis
    keywords=["decorators", "generators", "context managers", "metaclasses"],
    summary="Advanced Python features including decorators, generators...",
    reading_time_minutes=15,
    complexity_score=0.75,  # 0-1 scale

    # Content features
    has_code=True,
    has_images=False,
    has_links=True,
    has_exercises=True,

    # Educational metrics
    concept_density=3.2,  # concepts per 100 words
    example_count=8,
    definition_count=4,

    # Similarity features
    embedding_vector=[0.1, 0.2, ...],  # 384-dim vector
    topic_categories=["programming", "python", "advanced"]
)
```

**Example:**
```python
# Wrap content in ContentAdapter
from core.ports.content_protocols import ContentAdapter

class KuContentAdapter(ContentAdapter):
    def __init__(self, ku):
        self.ku = ku

    @property
    def uid(self) -> str:
        return self.ku.uid

    @property
    def content_text(self) -> str:
        return self.ku.content

ku = await ku_service.get("ku.python-advanced")
adapter = KuContentAdapter(ku.value)

# Extract metadata
result = await lp_intelligence.extract_content_metadata(adapter)

if result.is_ok:
    metadata = result.value
    print(f"Content: {metadata.content_uid}")
    print(f"Reading time: {metadata.reading_time_minutes} minutes")
    print(f"Complexity: {metadata.complexity_score:.0%}")
    print(f"Concept density: {metadata.concept_density:.1f} per 100 words")

    print(f"\nFeatures:")
    print(f"  Code examples: {metadata.has_code}")
    print(f"  Images: {metadata.has_images}")
    print(f"  Exercises: {metadata.has_exercises}")

    print(f"\nKeywords: {', '.join(metadata.keywords[:5])}")
    print(f"Categories: {', '.join(metadata.topic_categories)}")
```

**Dependencies:**
- OpenAIEmbeddingsService (optional - for embedding_vector generation)

**Content Features Detected:**
- Code blocks (```python...```)
- Images (![alt](url))
- External links ([text](http...))
- Exercises/questions (? or "Exercise:" patterns)

---

#### Method 7: analyze_content()

**Purpose:** Perform comprehensive content analysis including quality scoring, completeness assessment, and improvement recommendations.

**Signature:**
```python
async def analyze_content(
    self,
    content: ContentAdapter
) -> Result[ContentAnalysisResult]:
```

**Parameters:**
- `content` (ContentAdapter) - Content to analyze

**Returns:**
```python
ContentAnalysisResult(
    metadata=ContentMetadata(...),  # Full metadata from extract_content_metadata()
    quality_score=0.82,
    completeness_score=0.75,
    educational_value="high",  # "high", "medium", "low"
    recommended_improvements=[
        "Add more code examples",
        "Include exercises for practice",
        "Add visual diagrams for complex concepts"
    ]
)
```

**Example:**
```python
result = await lp_intelligence.analyze_content(content_adapter)

if result.is_ok:
    analysis = result.value

    print(f"Quality Analysis:")
    print(f"  Overall quality: {analysis.quality_score:.0%}")
    print(f"  Completeness: {analysis.completeness_score:.0%}")
    print(f"  Educational value: {analysis.educational_value}")

    print(f"\nContent Statistics:")
    meta = analysis.metadata
    print(f"  Reading time: {meta.reading_time_minutes} min")
    print(f"  Complexity: {meta.complexity_score:.0%}")
    print(f"  Examples: {meta.example_count}")
    print(f"  Definitions: {meta.definition_count}")

    if analysis.recommended_improvements:
        print(f"\nRecommended Improvements:")
        for improvement in analysis.recommended_improvements:
            print(f"  - {improvement}")
```

**Dependencies:**
- ContentAnalyzer (for metadata extraction)

**Quality Scoring Factors:**
- Content completeness (has intro, body, conclusion)
- Example-to-concept ratio
- Clarity (reading level analysis)
- Structure (headings, formatting)
- Educational components (exercises, summaries)

**Replaces:** `ContentAnalysisService.analyze_content()`

---

### Category 4: Content Discovery (ContentQualityAssessor)

#### Method 8: find_similar_content()

**Purpose:** Find similar content based on text similarity, topic overlap, and structural features.

**Signature:**
```python
async def find_similar_content(
    self,
    content: ContentAdapter,
    content_pool: list[ContentAdapter],
    limit: int = 5
) -> Result[list[tuple[ContentAdapter, float]]]:
```

**Parameters:**
- `content` (ContentAdapter) - Reference content
- `content_pool` (list[ContentAdapter]) - Pool of content to search
- `limit` (int, default=5) - Maximum results

**Returns:**
```python
[
    (ContentAdapter("ku.python-decorators"), 0.92),  # (content, similarity_score)
    (ContentAdapter("ku.python-generators"), 0.85),
    (ContentAdapter("ku.python-context-managers"), 0.78),
    ...
]
```

**Example:**
```python
# Find content similar to specific KU
reference_ku = await ku_service.get("ku.python-advanced")
reference_adapter = KuContentAdapter(reference_ku.value)

# Get all available content
all_kus = await ku_service.list()
content_pool = [KuContentAdapter(ku) for ku in all_kus.value]

# Find similar content
result = await lp_intelligence.find_similar_content(
    content=reference_adapter,
    content_pool=content_pool,
    limit=5
)

if result.is_ok:
    similar_content = result.value
    print(f"Content similar to '{reference_ku.value.title}':\n")

    for i, (content, similarity) in enumerate(similar_content, 1):
        print(f"{i}. {content.uid} (similarity: {similarity:.0%})")
```

**Dependencies:**
- ContentAnalyzer (for metadata extraction)

**Similarity Metrics:**
- Keyword overlap
- Topic category matching
- Structural similarity (code/images/exercises)
- Complexity match
- Embedding vector cosine similarity (if available)

---

#### Method 9: search_by_content_features()

**Purpose:** Search content by specific features like code presence, reading time, images, exercises, and keywords.

**Signature:**
```python
async def search_by_content_features(
    self,
    has_code: bool | None = None,
    has_images: bool | None = None,
    has_links: bool | None = None,
    has_exercises: bool | None = None,
    min_reading_time: int | None = None,
    max_reading_time: int | None = None,
    keywords: list[str] | None = None,
    content_pool: list[ContentAdapter] | None = None
) -> Result[list[ContentAdapter]]:
```

**Parameters:**
- `has_code` (bool, optional) - Filter by code presence
- `has_images` (bool, optional) - Filter by image presence
- `has_links` (bool, optional) - Filter by link presence
- `has_exercises` (bool, optional) - Filter by exercise presence
- `min_reading_time` (int, optional) - Minimum reading time in minutes
- `max_reading_time` (int, optional) - Maximum reading time in minutes
- `keywords` (list[str], optional) - Required keywords
- `content_pool` (list[ContentAdapter], optional) - Pool to search in

**Returns:**
```python
[
    ContentAdapter("ku.python-decorators"),
    ContentAdapter("ku.python-generators"),
    ...
]
```

**Example:**
```python
# Find short content with code examples
result = await lp_intelligence.search_by_content_features(
    has_code=True,
    has_exercises=True,
    min_reading_time=5,
    max_reading_time=15,
    content_pool=all_content
)

if result.is_ok:
    matches = result.value
    print(f"Found {len(matches)} content items with code and exercises (5-15 min)")
    for content in matches:
        print(f"  - {content.uid}")

# Find content by keywords
result = await lp_intelligence.search_by_content_features(
    keywords=["async", "await", "concurrency"],
    has_code=True,
    content_pool=all_content
)

if result.is_ok:
    matches = result.value
    print(f"Found {len(matches)} content items about async/await")

# Find visual learning content
result = await lp_intelligence.search_by_content_features(
    has_images=True,
    has_code=False,
    max_reading_time=10,
    content_pool=all_content
)
```

**Dependencies:**
- ContentAnalyzer (for metadata extraction)

**Use Cases:**
- "Find quick code examples" → `has_code=True, max_reading_time=10`
- "Find visual explanations" → `has_images=True`
- "Find practice content" → `has_exercises=True`
- "Find beginner content" → `complexity_score < 0.3` (via metadata filtering)

---

## BaseAnalyticsService Features

### Inherited Infrastructure

**Fail-Fast Validation:**
- `_require_graph_intelligence()` - Ensures graph_intel available (not currently used by LP)
- `_require_relationship_service()` - Ensures relationships available (not currently used by LP)

**Standard Attributes:**
- `self.backend` - Primary backend (optional - backward compatibility)
- `self.graph_intel` - GraphIntelligenceService (optional)
- `self.relationships` - UnifiedRelationshipService (optional)
- `self.embeddings` - OpenAIEmbeddingsService (optional)
- `self.llm` - LLMService (optional)
- `self.event_bus` - EventBus (optional)

**LP-Specific Attributes:**
- `self.progress_backend` - Progress backend for user mastery data
- `self.learning_backend` - Learning backend for LP/LS queries
- `self.vectors` - Vector storage backend
- `self.ku_service` - KuService for semantic queries
- `self.user_service` - UserService for UserContext access

**Sub-Service Attributes:**
- `self.state_analyzer` - LearningStateAnalyzer instance
- `self.recommendation_engine` - LearningRecommendationEngine instance
- `self.content_analyzer` - ContentAnalyzer instance
- `self.quality_assessor` - ContentQualityAssessor instance

**Logging:**
```python
self.logger.info("Message")  # Logs to: skuel.intelligence.lp.intelligence
```

---

## Integration

### Standalone Service (NOT in LpService Facade)

**IMPORTANT:** Unlike TasksIntelligenceService or GoalsIntelligenceService, LpIntelligenceService is **standalone** and must be created independently:

```python
# services_bootstrap.py
from core.services.lp_intelligence_service import create_lp_intelligence_service

# Create standalone (NOT via LpService)
lp_intelligence = create_lp_intelligence_service(
    progress_backend=progress_backend,
    learning_backend=lp_backend,
    embeddings_service=embeddings_service,
    vectors_backend=vectors_backend,
    graph_intelligence_service=graph_intelligence,
    ku_service=ku_service,
)

# Add to Services dataclass
services = Services(
    lp=lp_service,
    lp_intelligence=lp_intelligence,  # Separate field
    ...
)
```

### Usage in Application

```python
# Access via services composition root
from core.utils.services_bootstrap import get_services

services = await get_services()
lp_intelligence = services.lp_intelligence  # NOT services.lp.intelligence

# Analyze learning state
result = await lp_intelligence.analyze_learning_state(user_context)

# Get content recommendations
result = await lp_intelligence.recommend_content(
    user_context,
    content_pool=available_content,
    limit=10
)

# Analyze content quality
result = await lp_intelligence.analyze_content(content_adapter)
```

---

## Domain-Specific Features

### Facade Pattern (Zero Business Logic)

LpIntelligenceService is **pure delegation** - it contains zero business logic:
- All learning state analysis delegated to `LearningStateAnalyzer`
- All recommendations delegated to `LearningRecommendationEngine`
- All content metadata delegated to `ContentAnalyzer`
- All quality assessment delegated to `ContentQualityAssessor`

**Why Facade?**
- **Single entry point** - Consumers use one service, not four
- **Backward compatibility** - Maintains original LpIntelligenceService API
- **Focused sub-services** - Each sub-service has clear responsibility
- **Easier testing** - Test sub-services independently
- **BaseAnalyticsService compliance** - Extends base while maintaining architecture

### Learning State Analysis

LearningStateAnalyzer provides pedagogical intelligence:
- **Understanding assessment** - Analyze concept mastery depth
- **Engagement tracking** - Monitor learning motivation and focus
- **Readiness determination** - Decide when to review, learn new, consolidate, or rest
- **Guidance mode recommendations** - Suggest appropriate teaching approach
- **Vector-based learning styles** - Identify content preferences (if embeddings available)

### Content Intelligence

ContentAnalyzer and ContentQualityAssessor provide content operations:
- **Metadata extraction** - Extract all content features automatically
- **Quality scoring** - Multi-factor quality assessment
- **Similarity search** - Find related content across multiple metrics
- **Feature-based filtering** - Search by specific content characteristics
- **Educational value assessment** - Determine pedagogical effectiveness

### Personalized Recommendations

LearningRecommendationEngine provides intelligent guidance:
- **Content recommendations** - Rank content by relevance, difficulty match, prerequisites
- **Path recommendations** - Suggest complete learning sequences
- **Intervention detection** - Identify when user needs help, encouragement, or challenge
- **Session optimization** - Plan optimal learning sessions based on time and state

### ContentAdapter Protocol

All content analysis methods use `ContentAdapter` protocol for flexibility:
```python
from core.ports.content_protocols import ContentAdapter

class MyContentAdapter(ContentAdapter):
    @property
    def uid(self) -> str:
        return self._content.id

    @property
    def content_text(self) -> str:
        return self._content.text

    # Optional properties
    @property
    def title(self) -> str:
        return self._content.title
```

This allows any content type (KU, LS, LP, MOC, even external content) to be analyzed.

---

## Testing

### Unit Tests
```bash
# Test facade
uv run python -m pytest tests/unit/services/test_lp_intelligence_service.py -v

# Test sub-services
uv run python -m pytest tests/unit/services/lp_intelligence/ -v
```

### Integration Tests
```bash
# Test with real backends
uv run python -m pytest tests/integration/intelligence/test_lp_intelligence.py -v

# Test specific method
uv run python -m pytest tests/integration/intelligence/ -k "test_analyze_learning_state" -v
```

### Example Test
```python
from unittest.mock import Mock
from core.services.lp_intelligence_service import LpIntelligenceService

# Create mock dependencies
progress_backend = Mock()
learning_backend = Mock()
embeddings_service = Mock()

# Instantiate service
service = LpIntelligenceService(
    progress_backend=progress_backend,
    learning_backend=learning_backend,
    embeddings_service=embeddings_service
)

# Verify initialization
assert service._service_name == "lp.intelligence"
assert service.progress_backend == progress_backend
assert service.learning_backend == learning_backend

# Verify sub-services created
assert service.state_analyzer is not None
assert service.recommendation_engine is not None
assert service.content_analyzer is not None
assert service.quality_assessor is not None

# Test delegation
result = await service.analyze_learning_state(mock_user_context)
# Should delegate to state_analyzer.analyze_learning_state()
```

---

## See Also

- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` - Master index
- `/docs/decisions/ADR-024-base-intelligence-service-migration.md` - BaseAnalyticsService pattern
- `/core/services/base_intelligence_service.py` - Base implementation
- `/core/services/lp/lp_service.py` - LpService facade
- `/core/services/lp_intelligence/` - Sub-service implementations
- `/core/ports/content_protocols.py` - ContentAdapter protocol
- `/core/services/lp_intelligence/types.py` - Shared types and dataclasses
