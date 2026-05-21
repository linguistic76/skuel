"""Application Orchestrators.

Orchestrators act as facades to serve complex UI views or cross-domain aggregate
business operations, mitigating 'Dependency Gravity' in the routing layer.

Implemented orchestrators:
- ProfileOrchestrator                  — User Profile Hub
- SubmissionsOrchestrator              — Submissions & Workbench Hub (legacy, deleted in commit 5)
- UserEntryOrchestrator                 — UserEntry Hub (ADR-054 successor)
- ExploreOrchestrator                  — Explore / Discovery Hub
- LibraryOrchestrator                  — Library Hub
- TeacherOrchestrator                  — Teaching & Review Hub
- AdminOrchestrator                    — Admin Dashboard Hub
- JournalOrchestrator                  — Journals Hub
- ActivityReviewOrchestrator           — Activity Review Admin Hub
- PathwaysOrchestrator                 — Pathways UI (LpService + UserProgressService)
- LateralRelationshipsOrchestrator     — Lateral Relationships API
- CalendarOptimizationOrchestrator     — Calendar Optimization API
"""
