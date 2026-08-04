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
// Decision: CANONICALISE case first, then DELETE any value that is still not a
//          TimeOfDay member rather than guessing a slot for it. "medium" carries no
//          time information, and absence is the honest representation of "no slot
//          declared". The predicate is membership in the enum, NOT the literal
//          "medium" — pollution the audit did not see must not survive the
//          migration — but a case variant like "EVENING" is a stated preference
//          that the old ingestion path legitimately produced, so it is rewritten
//          rather than destroyed (Codex finding on this PR, code-verified).
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
           AS is_canonical_slot,
       toLower(h.preferred_time) IN
           ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
           AS is_slot_ignoring_case,
       count(*) AS n
ORDER BY n DESC;
// Expected: evening/true/true/1, anytime/true/true/1, medium/false/false/1

// =============================================================================
// Step 2: Canonicalise case variants BEFORE anything is deleted
// =============================================================================
// Habits ingested before this change kept their authored casing — the registry
// entry that lowercases `preferred_time: EVENING` ships in the same PR as this
// migration, and `parse_enum_field` accepted the uppercase form case-insensitively,
// so `"EVENING"` is a VALID stated preference, not pollution. Deleting it on a
// case difference would silently destroy a scheduling choice, and Step 3 is
// unrecoverable — so rewrite first, delete second.
//
// Measured 0 such rows on the dev graph (and 0 uppercase values in the vault) at
// the time of writing; this step is protective, for graphs whose census nobody took.

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
  AND NOT h.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
  AND toLower(h.preferred_time) IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
SET h.preferred_time = toLower(h.preferred_time),
    h.updated_at = datetime()
RETURN count(h) AS habits_case_normalised;
// Expected: 0 on the dev graph — a non-zero count elsewhere is this step earning
// its place, not a problem.

// =============================================================================
// Step 3: Drop every remaining non-slot value (absence = no slot declared)
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
// Step 4: Validate — no Habit carries a non-slot preferred_time
// =============================================================================

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
  AND NOT h.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
RETURN count(h) AS remaining_non_slot_habits;
// Expected: 0

// =============================================================================
// Step 5: Positive control — the surviving slot values are still there
// =============================================================================

MATCH (h:Habit)
WHERE h.preferred_time IS NOT NULL
RETURN h.preferred_time AS value, count(*) AS n
ORDER BY value;
// Expected: anytime/1, evening/1 (a count of 0 here would mean Step 3 over-reached)

// =============================================================================
// Step 6: Sweep — no OTHER node type carries a non-slot preferred_time either
// =============================================================================

MATCH (n)
WHERE n.preferred_time IS NOT NULL
  AND NOT n.preferred_time IN
      ['early_morning', 'morning', 'afternoon', 'evening', 'night', 'late_night', 'anytime']
RETURN labels(n) AS labels, n.preferred_time AS value, count(*) AS n
ORDER BY n DESC;
// Expected: empty result set
