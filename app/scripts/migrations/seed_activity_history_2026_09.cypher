// Migration: seed progress / alignment history from the latest-only stamps (2026-09)
// ==================================================================================
// The activity report's goals_progressed and principles_reviewed counters read
// persisted history — Goal.progress_history entries and Principle.alignment_history
// entries dated in the period — never last_progress_update / last_review_date, which
// every later write overwrites. A node that carries a stamp but no history was
// progressed or reviewed at the stamped time and would count nowhere; this file
// gives each such node one history entry dated at its stamp, so the counters see
// what the stamps saw. Run it BEFORE the code that reads history is deployed —
// ordering is what makes the switch invisible.
//
// Shapes (the mapper's): a non-empty history is ONE JSON string of records; an
// empty one is a native empty list. Only a node with no history at all (null,
// '', '[]', []) is touched — a node that already holds entries is left alone,
// so the file is idempotent.
//
//   Goal entry:      {"date": <stamp as stored>, "progress_percentage": <figure or null>}
//   Principle entry: {"assessed_date": <stamp's day>, "alignment_level": <current level,
//                     'unknown' when unset>, "evidence": <this file's marker>,
//                     "reflection": null, "kind": "seeded"}
//
// The principle entry's kind is "seeded": the stamp records THAT a review happened
// on that day, not which door recorded it (assessment or reflection), and the
// level is the principle's current one — a reading at seed time, which the marker
// evidence says. alignment_level must be an AlignmentLevel value (the model
// reads it back as one); current_alignment already is.
//
// Verify (before/after):
//   MATCH (g:Entity:Goal) WHERE g.last_progress_update IS NOT NULL
//   RETURN g.uid, g.progress_history
//   MATCH (p:Entity:Principle) WHERE p.last_review_date IS NOT NULL
//   RETURN p.uid, p.alignment_history
//   -- After: no row above has a null / empty history.

// Statement 1: goals.
MATCH (g:Entity:Goal)
WHERE g.last_progress_update IS NOT NULL
  AND (g.progress_history IS NULL OR g.progress_history IN ['', '[]'] OR g.progress_history = [])
SET g.progress_history =
  '[{"date": "' + toString(g.last_progress_update) + '", "progress_percentage": '
  + coalesce(toString(toFloat(g.progress_percentage)), 'null') + '}]';

// Statement 2: principles.
MATCH (p:Entity:Principle)
WHERE p.last_review_date IS NOT NULL
  AND (p.alignment_history IS NULL OR p.alignment_history IN ['', '[]'] OR p.alignment_history = [])
SET p.alignment_history =
  '[{"assessed_date": "' + left(toString(p.last_review_date), 10)
  + '", "alignment_level": "' + coalesce(p.current_alignment, 'unknown')
  + '", "evidence": "Seeded from last_review_date (scripts/migrations/seed_activity_history_2026_09.cypher)"'
  + ', "reflection": null, "kind": "seeded"}]';
