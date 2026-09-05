---
title: "Per-Node Substance Counters — the Unread Arm"
updated: 2026-09-05
status: "staged (ruled keep staged)"
registered: 2026-08-21
ruled: 2026-08-21
trigger: "a substantiation UI/surface is scheduled (gaps, needs-review, well-practiced badges)"
check: "git grep -n \"get_substantiation_gaps\\|is_well_practiced\" -- ui/ adapters/inbound/ — empty until wired"
---

# Per-Node Substance Counters — the Unread Arm

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**Registered finding, kept staged by Mike's ruling.** The substance-write-grain
census established: the per-node counter arm (`times_*` ×5 + last-date ×5 on
`Curriculum`) has **zero production readers**. All 8 counter-derived model
methods (`substance_score`, `is_theoretical_only`, `is_well_practiced`,
`needs_more_practice`, `get_substantiation_gaps`, `needs_review`,
`days_until_review_needed`, `get_substantiation_summary` —
`core/models/curriculum.py`) have no production caller; no code reads the
counter fields directly. Every live substance read is the OTHER arm — per-user
channel maps (`calculate_user_substance`, `zpd_backend`, analytics — #1033
switched the last reader deliberately: "the corpus-global figure this metric
deliberately no longer reads").

`git log -S` classification: the methods are **never-wired staged vision**
(present since the initial commit; `knowledge_substance_philosophy.md` is the
spec) — with `substance_score` orphaned from its one production caller by
#1033. Per the discriminator (never-wired → ask), Mike ruled **keep staged**:
the writers keep accruing (37 Kus + 10 PathSteps bear reflected counters; 464
total reflection credits vs 28 surviving edges — entries deleted by vault
reconciliation keep their credits) for the day a UI reads them. ⚠️ `./dev
bloat` does NOT cover model methods — this section is the visibility.

**Also parked here, same arm:** retroactive credit. A Ku composed into a
PathStep *after* accruing counters never back-credits the new composer (19
orphaned Kus currently hold counters nothing can read — the `Ku` model drops
the fields). Any future reader of the counter arm must decide whether stranded
orphan-Ku substance back-fills on composition or starts at zero.

| Trigger | Check |
|---------|-------|
| A substantiation UI/surface is scheduled (gaps, needs-review, well-practiced badges) | `git grep -n "get_substantiation_gaps\|is_well_practiced" -- "ui/" "adapters/inbound/"` — empty until wired |
