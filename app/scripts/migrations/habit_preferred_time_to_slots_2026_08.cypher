// Migration: Habit.preferred_time becomes TimeOfDay vocabulary
// Date: 2026-08-03
// Context: habit-rhythm arc S1 (docs/roadmap/habit-rhythm-arc.md). `preferred_time`
//          was an untyped string read three incompatible ways — as "HH:MM" clock
//          time, as slot words, and as a day-spine gate that silently dropped
//          anything not matching "HH:MM". It is now `TimeOfDay | None`
//          (core/models/enums/scheduling_enums.py).
//
// Audit before fix (live dev graph, 5 Habit nodes, 0 HabitTemplate nodes):
//          "evening"  x1  — already a TimeOfDay value, no rewrite needed
//          "anytime"  x1  — already a TimeOfDay value, no rewrite needed
//          "medium"   x1  — an EnergyLevel word, written by the DSL converter
//                           (core/services/dsl/activity_domain_converters.py),
//                           which now derives the slot from @when()'s hour
//          null       x2  — no declared slot, stays null
//
// Decision: DELETE any value that is not a TimeOfDay member rather than guessing a
//          slot for it. "medium" carries no time information, and absence is the
//          honest representation of "no slot declared". The predicate is
//          membership in the enum, NOT the literal "medium" — pollution the audit
//          did not see must not survive the migration.
//
// Why it must run: `parse_enum_field` (core/models/dto_helpers.py) raises on a
//          value outside the enum, so a habit carrying one is unreadable until
//          this runs. That is deliberate fail-fast, not a regression.
//
// Run with: cypher-shell -f scripts/migrations/habit_preferred_time_to_slots_2026_08.cypher

// =============================================================================
// Step 1: Audit — every distinct preferred_time value and its count
// =============================================================================

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
RETURN h.preferred_time AS value,
       h.preferred_time IN
           ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
           AS is_valid_slot,
       count(*) AS n
ORDER BY n DESC;
// Expected: evening/true/1, anytime/true/1, medium/false/1

// =============================================================================
// Step 2: Drop every non-slot value (absence = no slot declared)
// =============================================================================

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
  AND NOT h.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
REMOVE h.preferred_time
SET h.updated_at = datetime()
RETURN count(h) AS habits_cleared;
// Expected: 1

// =============================================================================
// Step 3: Validate — no Habit carries a non-slot preferred_time
// =============================================================================

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
  AND NOT h.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
RETURN count(h) AS remaining_non_slot_habits;
// Expected: 0

// =============================================================================
// Step 4: Positive control — the surviving slot values are still there
// =============================================================================

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
RETURN h.preferred_time AS value, count(*) AS n
ORDER BY value;
// Expected: anytime/1, evening/1 (a count of 0 here would mean Step 2 over-reached)

// =============================================================================
// Step 5: Sweep — no OTHER node type carries a non-slot preferred_time either
// =============================================================================

MATCH (n)
WHERE n.preferred_time IS NOT NULL
  AND NOT n.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
RETURN labels(n) AS labels, n.preferred_time AS value, count(*) AS n
ORDER BY n DESC;
// Expected: empty result set
