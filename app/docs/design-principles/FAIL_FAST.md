---
title: "Design Principle: Fail Fast"
updated: 2026-03-28
status: current
category: design-principles
tags: [design, principles, error-handling, dependencies]
related: [docs/patterns/ERROR_HANDLING.md, docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md]
---

# Fail Fast

> Dependencies are required. Errors surface immediately with clear reports.

## Statement

All dependencies are REQUIRED at bootstrap — no graceful degradation of core services. When something fails, it fails loudly with a clear error message, not silently with degraded behavior. The only valid `None` cases are true circular dependencies and explicitly-marked unimplemented features.

## Why This Matters

Silent failures compound. A service that silently returns empty results when its dependency is missing can run for weeks before someone notices the data is wrong. A service that crashes at startup with "Neo4j connection refused" is fixed in minutes.

## In Practice

- **Bootstrap validation:** `services_bootstrap/compose.py` verifies all service dependencies at application startup
- **`Result[T]` error handling:** Errors propagate as typed values with category, message, and context — never swallowed
- **`require_found()` pattern:** Fetch + not-found guard in one call; returns 404 immediately rather than passing `None` downstream
- **No fallback Cypher:** `FormSubmissionService` requires `form_template_service` as a dependency. If it's `None`, the app crashes — it doesn't fall back to raw queries
- **Clear error reports:** Six error categories (Validation, NotFound, Database, Integration, Business, System) with structured context

## Enforcement

- **SKUEL017:** No bare `except Exception` — use specific exception types from `core/utils/exception_types.py`
- **SKUEL007:** Use `Errors` factory for consistent error creation
- **SKUEL003:** Use `.is_error` (not `.is_err`) for failure checks
- **MyPy:** `Result[T]` return types force callers to handle the error path

## The Analog-Digital Exception

The one deliberate exception: `INTELLIGENCE_TIER=core` disables AI-dependent features (embeddings, LLM feedback, Askesis). This is not "graceful degradation" — it's a **feature toggle**. The core tier is a complete, tested product. The full tier adds capabilities. Neither degrades silently.

## See Also

- `/docs/patterns/ERROR_HANDLING.md`
- `/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md`
- `CLAUDE.md` § "Fail-Fast Dependency Philosophy"
