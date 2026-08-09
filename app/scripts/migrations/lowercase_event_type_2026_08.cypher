// Migration: Lowercase persisted Event.event_type values (2026-08)
// =====================================================================
// Problem: event_type was written in one vocabulary and read in three.
//   Every writer used the UPPERCASE constants of the old
//   `class EventType(str)` bag (core/models/event/event_request.py, deleted
//   in this migration's PR), while the search facet, the palette colour map
//   and the search-ranking learning-type set all compared lowercase — so the
//   readers could never match a persisted row.
//
// Fix (same PR as this file): EventType became a lowercase StrEnum in
//   core/models/enums/event_enums.py, registered in ENUM_FIELD_TYPES so
//   ingestion canonicalizes authored casing, and every write path now emits
//   lowercase members. This migration converges the already-persisted rows.
//
// Idempotent: toLower() on an already-lowercase value is a no-op.
// Scope: :Event nodes only. AuthEvent.event_type (a different, already-
//   lowercase vocabulary) and the event-bus BaseEvent.event_type discriminator
//   ("task.completed") are NOT persisted node properties of :Event and are
//   untouched.
//
// Verify (before/after):
//   MATCH (e:Event) WHERE e.event_type IS NOT NULL
//   RETURN e.event_type AS value, count(*) AS n ORDER BY value
//   -- After: every `value` must be a lowercase EventType member; decide
//   -- explicitly on any non-member survivor (do not silently rewrite).
//   -- Audit of 2026-08-09 (local dev graph): PERSONAL x5, RECURRING x1.

// Statement 1: the known category-error rows. "RECURRING" was stamped by
// EventsSchedulingService.create_recurring_events (fixed in this PR to write
// EventType.PERSONAL); recurrence stays modeled by recurrence_pattern on the
// same rows. Translate to the member the fixed writer now emits — lowercasing
// alone would strand a non-member "recurring".
MATCH (e:Event)
WHERE e.event_type = 'RECURRING'
SET e.event_type = 'personal';

// Statement 2: pure casing convergence for every remaining row.
MATCH (e:Event)
WHERE e.event_type IS NOT NULL AND e.event_type <> toLower(e.event_type)
SET e.event_type = toLower(e.event_type);
