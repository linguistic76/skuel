---
title: "ContextRetriever — Four Code-Shaped Findings"
updated: 2026-09-05
status: "set aside"
registered: 2026-09-04
trigger: "Mike schedules the ContextRetriever review"
check: "grep -n \"fail-fast\\|del depth\" core/services/askesis/context_retriever.py"
---

# ContextRetriever — Four Code-Shaped Findings

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Set aside, not ruled.** Surfaced by the signal arc's PR-J (#1253, prose-only) in
`core/services/askesis/context_retriever.py`; Mike (2026-09-04): *"an area that needs
deeper review — set it aside for future consideration."* Registered so the review has a
place to start; none of the four is a decision yet. The section above (three write-only
fields, registered 2026-08-20) is the same file — take the two in one sitting.

1. **`__init__` contradicts itself** (`:175`): the comment says every PS-bundle dependency
   is required and fail-fast, while every parameter defaults to `None` and the helpers
   return `[]` silently when one is missing. Either the constructor refuses (fail-fast, the
   SKUEL rule) or the comment stops claiming it — which side is right is the review's first
   question.
2. **`_user_uid` is live** (`:969`): underscore-prefixed, yet forwarded as the router's
   ADR-085 audience. CLAUDE.md reserves the prefix for placeholders — rename once the review
   confirms the flow.
3. **`get_learning_context(depth)` `del`s its parameter** (`:390`) "for signature
   stability" — three callers (`context_retriever.py:468`, `query_processor.py:523`,
   `askesis_service.py:373`). One Path Forward says delete the parameter and update the
   callers; the review decides whether anything upstream still means to honour a depth.
4. **`LearningContext`** (`core/services/askesis/types.py:374`) is exported from `core/services/askesis/__init__.py`
   with zero constructors — a dead dataclass unless the review finds its consumer. Outside
   `./dev bloat`'s scope (events / methods / templates / embedding maps), so nothing else
   reports it.

**Enable when**: Mike schedules the ContextRetriever review.
