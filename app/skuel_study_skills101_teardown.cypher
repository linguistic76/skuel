// SKUEL.app — Study Skills 101 teardown (remove only this slice)
WITH [
  'ku:note-taking-basics','ku:spaced-repetition-basics','ku:distraction-handling',
  'kc:study-skills-foundations',
  'pr:plan-then-execute','pr:small-wins',
  'ch:start-25min-now','ch:plan-two-blocks-tomorrow','ch:create-5-flashcards',
  'hb:daily-25min-focus','hb:weekly-review-30min',
  'gl:study-sprint-beginner',
  'tk:log-first-3-blocks','tk:make-5-cards','tk:weekly-review',
  'ev:study-block-25min',
  'lp:study-skills-101','ps:lp:study-skills-101:step-1','ps:lp:study-skills-101:step-2',
  'cv:2025-10-04:study-starter'
] AS uids
MATCH (n) WHERE n.uid IN uids
DETACH DELETE n;
