---
title: "KnowledgePracticed Subscriber"
updated: 2026-09-05
status: "ruled earns a subscriber"
registered: 2026-08-21
ruled: 2026-08-21
trigger: "a review-scheduling / spaced-repetition surface is scheduled"
check: "git grep -l \"subscribe(KnowledgePracticed\" — empty until wired"
---

# KnowledgePracticed Subscriber

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Trigger-gated deferral, Mike's ruling.** Offered delete-vs-keep on the
zero-subscriber `KnowledgePracticed` event (published at
`ps_practice_service.py`, path 1), Mike ruled a third way: **it should earn a
subscriber**. Per that ruling this section names the consumer; nothing is
built now.

**The named consumer: review scheduling (spaced repetition).** The staged
`Curriculum` model methods (`needs_review`, `days_until_review_needed` — see
the next section) are the repo's only designed consumer of practice recency,
and the event carries exactly what a scheduler needs (`knowledge_uid`,
`user_uid`, `times_practiced`, `occurred_at`, `practice_context`). When a
review-scheduling surface is built, `KnowledgePracticed` is its live signal —
subscribe there, then delete this section.

**Named cost of deferral:** until then the event is published to nobody — and
today not even published, since path 1 (`CalendarEventCompleted` →
`APPLIES_KNOWLEDGE` edges) has zero live traffic. Zero runtime cost, nonzero
map cost: `./dev bloat` will keep reporting it at the informational tier, and
this section is the recorded judgment call it asks for. ⚠️ `PLANNED_EVENTS` is
NOT the vehicle — it flags *published* classes as `planned-marking-stale`.

| Trigger | Check |
|---------|-------|
| A review-scheduling / spaced-repetition surface is scheduled | `git grep -l "subscribe(KnowledgePracticed"` — empty until wired |
