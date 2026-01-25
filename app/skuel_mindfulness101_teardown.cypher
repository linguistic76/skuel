// SKUEL.app — Mindfulness 101 teardown (remove only this slice)
WITH [
  'ku:breath-awareness-basics','ku:posture-basics','ku:mind-wandering-happens',
  'kc:mindfulness-foundations',
  'pr:small-steps','pr:attention-over-intensity',
  'ch:2-minutes-right-now','ch:2-minutes-before-bed','ch:label-one-wander',
  'hb:daily-2min-breath','hb:label-wander-daily',
  'gl:mindfulness-beginner',
  'tk:log-first-5-sessions','tk:reflect-on-first-week',
  'ev:practice-block-2min',
  'lp:mindfulness-101','ps:lp:mindfulness-101:step-1','ps:lp:mindfulness-101:step-2',
  'cv:2025-10-04:breath-starter'
] AS uids
MATCH (n) WHERE n.uid IN uids
DETACH DELETE n;
