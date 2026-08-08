// Migration: preferred_time becomes the TimeOfDay vocabulary
// Date: 2026-08-03
// Context: habit-rhythm arc S1 (docs/roadmap/done/habit-rhythm-arc.md). `preferred_time`
//          was an untyped string read three incompatible ways — as "HH:MM" clock
//          time, as slot words, and as a day-spine gate that silently dropped
//          anything not matching "HH:MM". It is now `TimeOfDay | None`
//          (core/models/enums/scheduling_enums.py) on BOTH Habit and HabitTemplate.
//
// Audit before fix (live dev graph, 5 Habit nodes, 0 HabitTemplate nodes):
//          "evening"  x1  — already a TimeOfDay value, no rewrite needed
//          "anytime"  x1  — already a TimeOfDay value, no rewrite needed
//          "medium"   x1  — an EnergyLevel word, written by the DSL converter
//                           (core/services/dsl/activity_domain_converters.py),
//                           which now derives the slot from @when()'s hour
//          null       x2  — no declared slot, stays null
//
// Decision: CANONICALISE case first, then DELETE any value that is still not a
//          TimeOfDay member rather than guessing a slot for it. "medium" carries no
//          time information, and absence is the honest representation of "no slot
//          declared". The predicate is membership in the enum, NOT the literal
//          "medium" — pollution the audit did not see must not survive the
//          migration — but a case variant like "EVENING" is a stated preference
//          that the old ingestion path legitimately produced, so it is rewritten
//          rather than destroyed (Codex finding on this PR, code-verified).
//
// Scope:   every node carrying `preferred_time`, NOT just `:Habit`. The field name
//          is registered once, globally, as TimeOfDay (`ENUM_FIELD_TYPES` in
//          core/models/enum_field_registry.py), and `:HabitTemplate` carries the
//          same property through the same retype — a template left holding "09:00"
//          would be unreadable, exactly like a habit. Label-scoping the fix would
//          reintroduce the split vocabulary this arc exists to close.
//
// Why it must run: `parse_enum_field` (core/models/dto_helpers.py) raises on a
//          value outside the enum, so a node carrying one is unreadable until
//          this runs. That is deliberate fail-fast, not a regression.
//
// Run with: cypher-shell -f scripts/migrations/habit_preferred_time_to_slots_2026_08.cypher

// =============================================================================
// Step 1: Audit — every distinct preferred_time value, per label
// =============================================================================
// The two boolean columns separate the classes BEFORE anything is written: a value
// that is only wrong in its casing is rescued by Step 2, one that is wrong outright
// is cleared by Step 3.

MATCH (n)
WHERE n.preferred_time IS NOT NULL
RETURN labels(n) AS labels,
       n.preferred_time AS value,
       n.preferred_time IN
           ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
           AS is_canonical_slot,
       toLower(n.preferred_time) IN
           ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
           AS is_slot_ignoring_case,
       count(*) AS n
ORDER BY n DESC;
// Expected on the dev graph: [Entity,Habit] evening/true/true/1,
//                            [Entity,Habit] anytime/true/true/1,
//                            [Entity,Habit] medium/false/false/1

// =============================================================================
// Step 2: Canonicalise case variants BEFORE anything is deleted
// =============================================================================
// Nodes ingested before this change kept their authored casing — the registry entry
// that lowercases `preferred_time: EVENING` ships in the same PR as this migration,
// and `parse_enum_field` accepted the uppercase form case-insensitively. So
// "EVENING" is a VALID stated preference, not pollution; deleting it on a case
// difference would silently destroy a scheduling choice, and Step 3 is
// unrecoverable — rewrite first, delete second.
//
// Measured 0 such rows on the dev graph (and 0 uppercase values across the vault's
// `preferred_time:` lines) at the time of writing; this step is protective, for
// graphs whose census nobody took.

MATCH (n)
WHERE n.preferred_time IS NOT NULL
  AND NOT n.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
  AND toLower(n.preferred_time) IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
SET n.preferred_time = toLower(n.preferred_time),
    n.updated_at = datetime()
RETURN count(n) AS nodes_case_normalised;
// Expected: 0 on the dev graph — a non-zero count elsewhere is this step earning
// its place, not a problem.

// =============================================================================
// Step 3: Drop every remaining non-slot value (absence = no slot declared)
// =============================================================================

MATCH (n)
WHERE n.preferred_time IS NOT NULL
  AND NOT n.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
REMOVE n.preferred_time
SET n.updated_at = datetime()
RETURN count(n) AS nodes_cleared;
// Expected: 1 (the "medium" habit)

// =============================================================================
// Step 4: Validate — nothing anywhere carries a non-slot preferred_time
// =============================================================================

MATCH (n)
WHERE n.preferred_time IS NOT NULL
  AND NOT n.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
RETURN count(n) AS remaining_non_slot_nodes;
// Expected: 0

// =============================================================================
// Step 5: Positive control — the valid values are still there
// =============================================================================
// A count of 0 here would mean Step 3 over-reached and the "0 remaining" above is
// vacuous.

MATCH (n)
WHERE n.preferred_time IS NOT NULL
RETURN labels(n) AS labels, n.preferred_time AS value, count(*) AS n
ORDER BY value;
// Expected on the dev graph: [Entity,Habit] anytime/1, [Entity,Habit] evening/1
