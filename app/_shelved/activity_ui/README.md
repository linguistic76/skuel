# Shelved: Activity Domain CRUD UI

**Date shelved:** 2026-03-28
**Reason:** Transitioning to ingestion-first architecture. Activity data enters via UnifiedIngestionService (mixed markdown + YAML from Obsidian). ActivityReport is the primary UI for viewing activity data.

## What's here

Activity Domain CRUD UI for 6 domains: Tasks, Goals, Habits, Events, Choices, Principles.

### adapters/ (route files)
| File | Original location | Purpose |
|------|-------------------|---------|
| `tasks_ui.py` | `adapters/inbound/tasks_ui.py` | Tasks dashboard, detail, edit routes |
| `tasks_api.py` | `adapters/inbound/tasks_api.py` | Tasks REST API |
| `tasks_routes.py` | `adapters/inbound/tasks_routes.py` | Tasks DomainRouteConfig wiring |
| `goals_ui.py` | `adapters/inbound/goals_ui.py` | Goals dashboard, Gantt, hierarchy |
| `goals_api.py` | `adapters/inbound/goals_api.py` | Goals REST API |
| `goals_routes.py` | `adapters/inbound/goals_routes.py` | Goals wiring |
| `habits_ui.py` | `adapters/inbound/habits_ui.py` | Habits dashboard, wizard, analytics |
| `habits_api.py` | `adapters/inbound/habits_api.py` | Habits REST API |
| `habits_routes.py` | `adapters/inbound/habits_routes.py` | Habits wiring |
| `events_ui.py` | `adapters/inbound/events_ui.py` | Events dashboard, detail, edit |
| `events_api.py` | `adapters/inbound/events_api.py` | Events REST API |
| `events_routes.py` | `adapters/inbound/events_routes.py` | Events wiring |
| `choices_ui.py` | `adapters/inbound/choices_ui.py` | Choices dashboard, decision workflow |
| `choices_api.py` | `adapters/inbound/choices_api.py` | Choices REST API |
| `choices_routes.py` | `adapters/inbound/choices_routes.py` | Choices wiring |
| `principles_ui.py` | `adapters/inbound/principles_ui.py` | Principles dashboard, reflection |
| `principles_api.py` | `adapters/inbound/principles_api.py` | Principles REST API |
| `principles_routes.py` | `adapters/inbound/principles_routes.py` | Principles wiring |
| `activities_ui.py` | `adapters/inbound/activities_ui.py` | Activities landing page |

### ui/ (component directories)
| Directory | Original location | Purpose |
|-----------|-------------------|---------|
| `ui/tasks/` | `ui/tasks/` | Task cards, views, layout |
| `ui/goals/` | `ui/goals/` | Goal cards, Gantt visualization |
| `ui/habits/` | `ui/habits/` | Habit cards, wizard, badges, analytics |
| `ui/events/` | `ui/events/` | Event cards, views |
| `ui/choices/` | `ui/choices/` | Choice cards, decision views |
| `ui/principles/` | `ui/principles/` | Principle cards, reflection views |
| `ui/activities/` | `ui/activities/` | Shared sidebar, landing page |

### tests/ (integration tests)
| File | Original location |
|------|-------------------|
| `test_tasks_api.py` | `tests/integration/routes/test_tasks_api.py` |
| `test_goals_api.py` | `tests/integration/routes/test_goals_api.py` |
| `test_habits_api.py` | `tests/integration/routes/test_habits_api.py` |
| `test_events_api.py` | `tests/integration/routes/test_events_api.py` |

## How to restore

1. Move files back to their original locations (see tables above)
2. Re-add route registrations to `scripts/dev/bootstrap.py`:
   - 6 `create_*_routes` calls in the "Activity" section
   - `setup_activities_routes` call
3. Restore `ACTIVITY_DROPDOWN_ITEMS` in `ui/layouts/nav_config.py`
4. Check that service facades still expose the methods these routes call
5. Run `./dev quality` and `uv run pytest` to verify

### services/ (sub-services only needed by UI)
| File | Original location | Purpose |
|------|-------------------|---------|
| `tasks_ai_service.py` | `core/services/tasks/` | LLM-enriched task descriptions |
| `goals_ai_service.py` | `core/services/goals/` | LLM-enriched goal descriptions |
| `habits_ai_service.py` | `core/services/habits/` | LLM-enriched habit descriptions |
| `events_ai_service.py` | `core/services/events/` | LLM-enriched event descriptions |
| `choices_ai_service.py` | `core/services/choices/` | LLM-enriched choice descriptions |
| `principles_ai_service.py` | `core/services/principles/` | LLM-enriched principle descriptions |
| `tasks_productivity_service.py` | `core/services/tasks/` | Productivity analytics |
| `habits_goal_analytics_service.py` | `core/services/habits/` | Habit-goal cross-analytics |
| `principles_reflection_service.py` | `core/services/principles/` | Reflection system |

### Additional files shelved in cleanup round (2026-03-28)

Orphaned code left behind after the initial shelving — zero active imports.

| File | Original location | Purpose |
|------|-------------------|---------|
| `ui/patterns/activity_views_base.py` | `ui/patterns/activity_views_base.py` | Activity-specific tabs, calendar nav, filters |
| `ui/layouts/activity_layout.py` | `ui/layouts/activity_layout.py` | Activity layout with DOMAIN_CSS mapping |
| `adapters/route_factories/dashboard_ui_factory.py` | `adapters/inbound/route_factories/dashboard_ui_factory.py` | Dashboard UI factory for 6 activity domains |
| `adapters/route_factories/quick_add_factory.py` | `adapters/inbound/route_factories/quick_add_factory.py` | Quick-add form factory for 6 activity domains |
| `static/vendor/frappe-gantt/` | `static/vendor/frappe-gantt/` | Frappe Gantt JS/CSS (only loaded by goals visualization) |

**Also removed from active files (not recoverable from _shelved/, but preserved in git history):**
- 12 dead Alpine.js components from `static/js/skuel.js`: searchSidebar, calendarModal, taskEditModal, timelineViewer, swipeHandler, loadingButton, dropdownNav, ganttVis, choiceOptions, accessibleModal, focusTrapModal, insightSwipeActions
- `Text` class from `ui/tokens.py`
- `DashboardUIFactory`/`QuickAddRouteFactory` exports from `route_factories/__init__.py`

## Dependencies to check on restore

- Service facades: `TasksService`, `GoalsService`, `HabitsService`, `EventsService`, `ChoicesService`, `PrinciplesService`
- Route factories: `DashboardUIFactory`, `QuickAddRouteFactory` (in `adapters/inbound/route_factories/`)
- `create_activity_domain_route_config()` in route wiring files
- `ACTIVITY_SIDEBAR_ITEMS` in `ui/activities/sidebar.py`
- AI services: re-add to `services_bootstrap/_ai_wiring.py` and facade `__init__` methods
- Analytics services: re-add to facade constructors and `services_bootstrap/compose.py`
