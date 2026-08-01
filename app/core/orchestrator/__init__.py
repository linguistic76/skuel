"""Application Orchestrators.

Orchestrators act as facades to serve complex UI views or cross-domain aggregate
business operations, mitigating 'Dependency Gravity' in the routing layer.

Implemented orchestrators:
- ProfileOrchestrator                  — User Profile Hub
- UserEntryOrchestrator                 — UserEntry Hub (ADR-054 successor to the
                                          former Submissions + Journal orchestrators)
- ExploreOrchestrator                  — Explore / Discovery Hub
- LibraryOrchestrator                  — Library Hub
- TeacherOrchestrator                  — Teaching & Review Hub
- AdminOrchestrator                    — Admin Dashboard Hub
- ActivityReviewOrchestrator           — Activity Review Admin Hub
- PathwaysOrchestrator                 — Pathways UI (LpService + UserProgressService)
- LateralRelationshipsOrchestrator     — Lateral Relationships API
- CalendarOptimizationOrchestrator     — Calendar Optimization API
- SearchRouter                         — Cross-domain search (THE single path for
                                          all external search access)
"""
