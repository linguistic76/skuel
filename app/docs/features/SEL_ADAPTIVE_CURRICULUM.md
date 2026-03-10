---
title: SEL Adaptive Curriculum
updated: 2026-02-03
status: production
category: features
tags: [sel, adaptive-learning, curriculum, personalization, htmx]
related:
  - docs/patterns/UI_COMPONENT_PATTERNS.md
  - docs/architecture/CURRICULUM_GROUPING_PATTERNS.md
  - docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md
---

# SEL Adaptive Curriculum

> **Status:** Production (UX Modernization Complete - 2026-02-03)
> **Routes:** `/sel`, `/sel/{category}`
> **Service:** `AdaptiveSELService`

## Overview

The SEL (Social Emotional Learning) adaptive curriculum delivers personalized knowledge units across 5 core competencies based on user progress, prerequisites, and learning velocity.

**Key Features:**
- Dynamic curriculum personalization via HTMX
- Progress tracking across 5 SEL categories
- Prerequisite-aware recommendations
- Interaction tracking in Neo4j
- Accessible drawer navigation

## Architecture

### The 5 SEL Categories

| Category | Route | Description | SELCategory Enum |
|----------|-------|-------------|------------------|
| **Self Awareness** | `/sel/self-awareness` | Understanding thoughts, emotions, values | `SELF_AWARENESS` |
| **Self Management** | `/sel/self-management` | Managing emotions and achieving goals | `SELF_MANAGEMENT` |
| **Social Awareness** | `/sel/social-awareness` | Understanding others and social contexts | `SOCIAL_AWARENESS` |
| **Relationship Skills** | `/sel/relationship-skills` | Building healthy relationships | `RELATIONSHIP_SKILLS` |
| **Decision Making** | `/sel/decision-making` | Making responsible choices | `DECISION_MAKING` |

### Service Architecture

```python
# Service: AdaptiveSELService (absorbed into KuAdaptiveService — February 2026)
# Location: core/services/ku/ku_adaptive_service.py

class AdaptiveSELService:
    """
    Core service for adaptive SEL curriculum delivery.

    Analyzes user's learning journey and delivers personalized
    Knowledge Units based on readiness, prerequisites, and learning velocity.
    """

    # Curriculum Delivery
    async def get_personalized_curriculum(
        user_uid: str,
        sel_category: SELCategory,
        limit: int = 10
    ) -> Result[list[Ku]]

    async def get_sel_journey(
        user_uid: str
    ) -> Result[SELJourney]

    # Interaction Tracking
    async def track_page_view(
        user_uid: str,
        category: SELCategory | None = None
    ) -> Result[None]

    async def track_curriculum_completion(
        user_uid: str,
        ku_uid: str,
        completion_time_minutes: int = 30
    ) -> Result[None]
```

### Curriculum Personalization Algorithm

```python
# 1. Load user intelligence
user_intel = await self._load_user_intelligence(user_uid)

# 2. Query all KUs in this SEL category
all_kus = await self.ku_backend.find_by(sel_category=category.value)

# 3. Filter by readiness (prerequisites + level)
ready_kus = [ku for ku in all_kus if await self._is_user_ready(user_intel, ku)]

# 4. Rank by learning value
ranked_kus = await self._rank_by_learning_value(user_intel, ready_kus)

# 5. Return top N recommendations
return Result.ok(ranked_kus[:limit])
```

**Readiness Criteria:**
- Not already mastered
- All prerequisites completed
- Learning level appropriate for user

**Ranking Factors:**
- Enables many future KUs (high leverage): +10 × count
- Matches user's preferred difficulty: +20
- Time investment fits availability: +15
- Foundational (no prerequisites): +5
- Quick win (< 15 min): +10

## UI Components

### Route Structure (UX Modernization - 2026-02-03)

All SEL routes follow the modernized pattern:

```python
@rt("/sel/{category}")
async def sel_category(request: Request) -> Any:
    """Category adaptive curriculum page"""
    user_uid = require_authenticated_user(request)

    # Track page view (non-blocking)
    await services.adaptive_sel.track_page_view(user_uid, SELCategory.{CATEGORY})

    # Breadcrumbs
    breadcrumbs = Breadcrumbs(path=[
        {"uid": "sel", "title": "SEL", "url": "/sel"},
        {"uid": "category", "title": "Category Name", "url": None},
    ])

    content = Div(
        breadcrumbs,
        PageHeader("Category Name", subtitle="Description"),
        SectionHeader("About This Competency"),
        P("Description text...", cls="text-base-content/70 mb-6"),

        # HTMX dynamic curriculum loading
        SectionHeader("Your Personalized Curriculum"),
        Div(
            Div(P("Loading...", cls="text-center py-8"), cls="animate-pulse"),
            hx_get=f"/api/sel/curriculum-html/{category}?limit=10",
            hx_trigger="load",
            hx_swap="innerHTML",
            **{"data-announce": "Curriculum loaded"},
            id="curriculum-list",
            cls="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6",
        ),
    )

    # Drawer sidebar layout
    page_layout = create_sel_sidebar_layout(category_slug, content)

    # BasePage wrapper
    return await BasePage(
        page_layout,
        title=f"{category_name} - SEL",
        page_type=PageType.STANDARD,
        request=request,
        active_page="sel",
    )
```

### Component Stack

**Standard UI Primitives (Migrated 2026-02-03):**
- `EntityCard` - KU display with metadata
- `Badge` - Learning level, prerequisites status
- `ButtonLink` - "Start Learning" actions
- `PageHeader` - Page titles with subtitles
- `SectionHeader` - Section dividers
- `Breadcrumbs` - Navigation trail
- `EmptyState` - No curriculum available

**Legacy Components (Replaced):**
- ~~Custom Badge function~~ → `ui/feedback.py` (StatusBadge, PriorityBadge)
- ~~Manual card layout~~ → `EntityCard` pattern
- ~~Manual navbar creation~~ → `BasePage` wrapper

### SEL Component Examples

#### SELCategoryCard (with EntityCard)

```python
def SELCategoryCard(category: SELCategory, progress: SELCategoryProgress) -> Any:
    """SEL category card showing progress."""
    category_title = f"{get_sel_icon(category.value)} {category.value.replace('_', ' ').title()}"

    card = EntityCard(
        title=category_title,
        description=category.get_description(),
        metadata=[
            f"{progress.articles_mastered} mastered",
            f"{progress.articles_in_progress} in progress",
            f"{progress.articles_available} available",
        ],
        actions=ButtonLink(
            "Continue Learning →",
            href=f"/sel/{category.value.replace('_', '-')}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )

    # Custom progress bar
    progress_section = Div(
        Progress(value=progress.articles_mastered, max=progress.total_articles),
        P(f"{progress.completion_percentage:.0f}% complete"),
    )

    return Div(card, progress_section, cls="mb-4")
```

#### AdaptiveKUCard (with EntityCard)

```python
def AdaptiveKUCard(ku: Ku, prerequisites_met: bool = True) -> Any:
    """Card for one Knowledge Unit in adaptive curriculum."""
    metadata = [
        f"⏱ {ku.estimated_time_minutes} min",
        f"🎯 {ku.difficulty_rating:.1f}/1.0 difficulty",
        Badge(ku.learning_level.value.title(), variant="default"),
        Badge("✓ Prerequisites met" if prerequisites_met else "Prerequisites needed",
              variant="success" if prerequisites_met else "warning"),
    ]

    return EntityCard(
        title=ku.title,
        description=ku.content[:150] + "...",
        metadata=metadata,
        actions=ButtonLink(
            "Start Learning →",
            href=f"/knowledge/{ku.uid}",
            variant="primary",
            full_width=True,
        ),
        config=CardConfig.default(),
    )
```

## HTMX API Endpoints

### Journey Overview

```
GET /api/sel/journey-html
Auth: Required
Returns: HTML fragment (SELJourneyOverview component)

Response:
- Overall completion percentage
- Recommended next category
- All 5 category cards with progress
```

### Category Curriculum

```
GET /api/sel/curriculum-html/{category}?limit=10
Auth: Required
Params:
  - category: self_awareness|self_management|social_awareness|relationship_skills|decision_making
  - limit: Max KUs to return (default: 10)

Returns: HTML fragment (grid of AdaptiveKUCard components)

States:
- Loading: Skeleton/pulse animation
- Success: Grid of KU cards
- Empty: EmptyState component
- Error: Alert message
```

## Interaction Tracking

### Graph Schema

```cypher
// User properties (page views)
(:User {
  uid: "user_mike",
  sel_last_viewed: datetime,
  sel_view_count: 42,
  sel_self_awareness_views: 10,
  sel_self_management_views: 8,
  sel_social_awareness_views: 7,
  sel_relationship_skills_views: 9,
  sel_decision_making_views: 8
})

// Curriculum completions
(:User)-[:MASTERED {
  mastery_level: "proficient",
  source: "sel_curriculum",
  time_to_mastery_hours: 0.5,
  created_at: datetime,
  updated_at: datetime
}]->(:Curriculum)
```

### Tracking Methods

```python
# Track page view (non-blocking)
await services.adaptive_sel.track_page_view(
    user_uid="user_mike",
    category=SELCategory.SELF_AWARENESS  # or None for overview
)

# Track curriculum completion
await services.adaptive_sel.track_curriculum_completion(
    user_uid="user_mike",
    ku_uid="ku_emotional-intelligence_abc123",
    completion_time_minutes=30
)
```

### Analytics Queries

```cypher
// Most viewed categories
MATCH (u:User {uid: $user_uid})
RETURN {
  self_awareness: u.sel_self_awareness_views,
  self_management: u.sel_self_management_views,
  social_awareness: u.sel_social_awareness_views,
  relationship_skills: u.sel_relationship_skills_views,
  decision_making: u.sel_decision_making_views
} as views

// Curriculum completions by category
MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(k:Curriculum)
WHERE m.source = 'sel_curriculum'
AND k.sel_category = $category
RETURN count(m) as completions,
       avg(m.time_to_mastery_hours) as avg_time_hours

// Completion rate over time
MATCH (u:User {uid: $user_uid})-[m:MASTERED]->(k:Curriculum)
WHERE m.source = 'sel_curriculum'
WITH date(m.created_at) as completion_date, count(m) as completions
RETURN completion_date, completions
ORDER BY completion_date DESC
LIMIT 30
```

## Accessibility

### ARIA Announcements

```python
# HTMX attributes for screen readers (raw data attributes, read by skuel.js)
**{"data-announce": "Curriculum loaded",
   "data-announce-loading": "Loading personalized curriculum"}
```

**Screen reader flow:**
1. User navigates to category page
2. Screen reader announces: "Loading personalized curriculum"
3. Content loads via HTMX
4. Screen reader announces: "Curriculum loaded"

### Keyboard Navigation

- **Drawer menu:** Tab/Arrow keys navigate categories
- **Breadcrumbs:** Tab to breadcrumb links, Enter to activate
- **KU cards:** Tab through "Start Learning" buttons
- **Skip links:** BasePage provides skip-to-content

### Drawer Sidebar

```python
# Preserved drawer navigation (DaisyUI checkbox-based)
create_sel_sidebar_layout(
    active_page="self-awareness",
    content=main_content
)
```

**Features:**
- CSS-only toggle (no JavaScript)
- Keyboard accessible (Tab, Space, Enter)
- Mobile responsive (hamburger menu)
- ARIA labels for screen readers

## Testing

### Unit Tests

```bash
# SEL adaptive logic now tested via ku_adaptive_service tests
poetry run pytest tests/test_ku_search_service.py -v
```

### Manual Testing Checklist

- [ ] Navigate to `/sel` - journey loads via HTMX
- [ ] Click category - curriculum loads dynamically
- [ ] Drawer navigation works (all 5 categories)
- [ ] Breadcrumbs show correct path
- [ ] Loading states display
- [ ] Error states display (simulate API failure)
- [ ] Empty state when no curriculum
- [ ] Screen reader announces HTMX updates
- [ ] Keyboard navigation functional
- [ ] Mobile drawer menu works

## Performance

**HTMX Benefits:**
- Partial page updates (no full reload)
- Reduced bandwidth (HTML fragments only)
- Faster perceived performance (skeleton states)
- Progressive enhancement (works without JS)

**Optimization:**
- Non-blocking tracking calls
- Curriculum query limit (default: 10)
- Neo4j query optimization (indexed properties)
- Caching opportunities (future enhancement)

## Migration History

**2026-02-03: UX Modernization Complete**
- ✅ Component migration to EntityCard pattern
- ✅ BasePage integration with breadcrumbs
- ✅ HTMX dynamic loading
- ✅ Interaction tracking in Neo4j
- ✅ Accessibility improvements (ARIA, keyboard nav)

**Key Changes:**
- ~520 lines modified across 4 files
- Zero breaking changes
- All 14 tests passing
- Drawer sidebar preserved

See: `/docs/migrations/SEL_UX_MODERNIZATION_2026-02-03.md`

## Future Enhancements

### Phase 2: Advanced Tracking
- [ ] Track time spent on each KU
- [ ] Measure completion rates by difficulty
- [ ] A/B test curriculum ordering
- [ ] Spaced repetition reminders

### Phase 3: Social Features
- [ ] Share progress with mentors
- [ ] Peer learning groups
- [ ] Discussion forums per category
- [ ] Collaborative learning paths

### Phase 4: AI Recommendations
- [ ] ChatGPT-powered curriculum explanations
- [ ] Personalized study plans
- [ ] Learning style adaptation
- [ ] Automated prerequisite detection

## Related Documentation

**Patterns:**
- [UI Component Patterns](../patterns/UI_COMPONENT_PATTERNS.md) - EntityCard, BasePage
- [HTMX Accessibility Patterns](../patterns/HTMX_ACCESSIBILITY_PATTERNS.md) - ARIA announcements
- [Curriculum Grouping](../architecture/CURRICULUM_GROUPING_PATTERNS.md) - KU/LS/LP

**Architecture:**
- [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) - BaseService patterns
- [Service Architecture: File Organization & Topology](../architecture/SERVICE_TOPOLOGY.md) - Service structure

**ADRs:**
- [ADR-023: Curriculum BaseService Migration](../decisions/ADR-023-curriculum-baseservice-migration.md)
- [ADR-005: Ready to Learn Knowledge Query](../decisions/ADR-005-ready-to-learn-knowledge-query.md)

## Contact & Support

**Service Location:** `core/services/ku/ku_adaptive_service.py` (absorbed from AdaptiveSELService February 2026 — SEL is a navigation lens over KUs)
**Routes:** SEL routes removed February 2026 — curriculum access via `/ku` hub

**Key Contributors:** Claude Sonnet 4.5 (UX Modernization - 2026-02-03)
