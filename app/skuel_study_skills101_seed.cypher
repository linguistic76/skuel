// SKUEL.app — Study Skills 101 seed (pure Cypher, idempotent)
// Constraints & Indexes
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Ku) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:KnowledgeCluster) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Lp) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:PathStep) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Principle) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Choice) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Habit) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Goal) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Task) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:EventTemplate) REQUIRE n.uid IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Conversation) REQUIRE n.uid IS UNIQUE;

// Knowledge Units (articles)
MERGE (ku1:Ku {uid:'ku:note-taking-basics'})
  ON CREATE SET ku1.title='Note‑Taking Basics',
                ku1.summary='Simple, readable notes: headers, bullets, and keywords.',
                ku1.tags=['study','notes','beginner'],
                ku1.kind='article',
                ku1.body_path='content/study/note-taking-basics.md',
                ku1.createdAt=datetime()
  ON MATCH  SET ku1.updatedAt=datetime();

MERGE (ku2:Ku {uid:'ku:spaced-repetition-basics'})
  ON CREATE SET ku2.title='Spaced Repetition — Basics',
                ku2.summary='Why short reviews beat cramming, and how to start.',
                ku2.tags=['memory','review','beginner'],
                ku2.kind='article',
                ku2.body_path='content/study/spaced-repetition-basics.md',
                ku2.createdAt=datetime()
  ON MATCH  SET ku2.updatedAt=datetime();

MERGE (ku3:Ku {uid:'ku:distraction-handling'})
  ON CREATE SET ku3.title='Handling Distractions',
                ku3.summary='A quick checklist to keep your focus clean.',
                ku3.tags=['focus','environment'],
                ku3.kind='article',
                ku3.body_path='content/study/distraction-handling.md',
                ku3.createdAt=datetime()
  ON MATCH  SET ku3.updatedAt=datetime();

// Cluster
MERGE (kc:KnowledgeCluster {uid:'kc:study-skills-foundations'})
  ON CREATE SET kc.title='Study Skills Foundations',
                kc.summary='A starter bundle: notes, review, and focused blocks.',
                kc.tags=['study','starter'],
                kc.createdAt=datetime()
  ON MATCH  SET kc.updatedAt=datetime();

MERGE (ku1:Ku {uid:'ku:note-taking-basics'})
MERGE (ku2:Ku {uid:'ku:spaced-repetition-basics'})
MERGE (ku3:Ku {uid:'ku:distraction-handling'})

MERGE (ku1)-[:IN_CLUSTER]->(kc)
MERGE (ku2)-[:IN_CLUSTER]->(kc)
MERGE (ku3)-[:IN_CLUSTER]->(kc);

// Principles
MERGE (pr1:Principle {uid:'pr:plan-then-execute'})
  ON CREATE SET pr1.title='Plan, Then Execute',
                pr1.summary='Decide the next block before you start it.',
                pr1.tags=['planning','execution'],
                pr1.createdAt=datetime()
  ON MATCH  SET pr1.updatedAt=datetime();

MERGE (pr2:Principle {uid:'pr:small-wins'})
  ON CREATE SET pr2.title='Small Wins Compound',
                pr2.summary='Short blocks and frequent reviews beat marathons.',
                pr2.tags=['habits','momentum'],
                pr2.createdAt=datetime()
  ON MATCH  SET pr2.updatedAt=datetime();

// Choices
MERGE (ch1:Choice {uid:'ch:start-25min-now'})
  ON CREATE SET ch1.title='Start a 25‑minute block now',
                ch1.summary='Pick one topic, set a timer, go.',
                ch1.tags=['focus','pomodoro'],
                ch1.createdAt=datetime()
  ON MATCH  SET ch1.updatedAt=datetime();

MERGE (ch2:Choice {uid:'ch:plan-two-blocks-tomorrow'})
  ON CREATE SET ch2.title='Plan two blocks for tomorrow',
                ch2.summary='Name topics and times before you sleep.',
                ch2.tags=['planning'],
                ch2.createdAt=datetime()
  ON MATCH  SET ch2.updatedAt=datetime();

MERGE (ch3:Choice {uid:'ch:create-5-flashcards'})
  ON CREATE SET ch3.title='Create 5 flashcards',
                ch3.summary='One concept per card. Keep them short.',
                ch3.tags=['memory','review'],
                ch3.createdAt=datetime()
  ON MATCH  SET ch3.updatedAt=datetime();

// Habits
MERGE (hb1:Habit {uid:'hb:daily-25min-focus'})
  ON CREATE SET hb1.title='Daily 25‑Minute Focus Block',
                hb1.summary='One focused study block per day.',
                hb1.tags=['focus','study','habit'],
                hb1.schedule_hint='daily',
                hb1.metrics = {unit:'blocks', target_per_week:5},
                hb1.createdAt=datetime()
  ON MATCH  SET hb1.updatedAt=datetime();

MERGE (hb2:Habit {uid:'hb:weekly-review-30min'})
  ON CREATE SET hb2.title='Weekly 30‑Minute Review',
                hb2.summary='Sweep your notes; refresh key ideas.',
                hb2.tags=['review','habit'],
                hb2.schedule_hint='weekly',
                hb2.metrics = {unit:'minutes', target_per_week:30},
                hb2.createdAt=datetime()
  ON MATCH  SET hb2.updatedAt=datetime();

// Goal
MERGE (gl:Goal {uid:'gl:study-sprint-beginner'})
  ON CREATE SET gl.title='Finish a beginner study sprint',
                gl.summary='5 focused blocks and 1 weekly review in the first week.',
                gl.tags=['study','starter'],
                gl.createdAt=datetime()
  ON MATCH  SET gl.updatedAt=datetime();

// Tasks
MERGE (tk1:Task {uid:'tk:log-first-3-blocks'})
  ON CREATE SET tk1.title='Log your first three blocks',
                tk1.summary='Record topic, start time, and one sentence of result.',
                tk1.tags=['logging','beginner'],
                tk1.estimated_minutes=3,
                tk1.priority='normal',
                tk1.createdAt=datetime()
  ON MATCH  SET tk1.updatedAt=datetime();

MERGE (tk2:Task {uid:'tk:make-5-cards'})
  ON CREATE SET tk2.title='Make five flashcards',
                tk2.summary='Create 5 Q→A cards from today’s notes.',
                tk2.tags=['memory','cards'],
                tk2.estimated_minutes=10,
                tk2.priority='normal',
                tk2.createdAt=datetime()
  ON MATCH  SET tk2.updatedAt=datetime();

MERGE (tk3:Task {uid:'tk:weekly-review'})
  ON CREATE SET tk3.title='Do a 30‑minute weekly review',
                tk3.summary='Scan notes, tidy headings, mark confusing parts.',
                tk3.tags=['review'],
                tk3.estimated_minutes=30,
                tk3.priority='normal',
                tk3.createdAt=datetime()
  ON MATCH  SET tk3.updatedAt=datetime();

// Event Template
MERGE (ev:EventTemplate {uid:'ev:study-block-25min'})
  ON CREATE SET ev.title='Study Block — 25 min',
                ev.summary='Calendar projection of a focused work block.',
                ev.duration_minutes=25,
                ev.render = {color_hint:'indigo', icon_hint:'book'},
                ev.createdAt=datetime()
  ON MATCH  SET ev.updatedAt=datetime();

// Learning Path & Steps
MERGE (lp:Lp {uid:'lp:study-skills-101'})
  ON CREATE SET lp.title='Study Skills 101 — Simple & Steady',
                lp.summary='Start with one focused block and a tiny review habit.',
                lp.tags=['study','beginner','conversational'],
                lp.audience='teen-general',
                lp.progress_model = {kind:'simple-checkpoints', completion_rule:'any-4-days-in-7'},
                lp.createdAt=datetime()
  ON MATCH  SET lp.updatedAt=datetime();

MERGE (ps1:PathStep {uid:'ps:lp:study-skills-101:step-1'})
  ON CREATE SET ps1.title='One 25‑Minute Block Today',
                ps1.intent='Pick one topic, run a single 25‑minute block, and log it.',
                ps1.createdAt=datetime()
  ON MATCH  SET ps1.updatedAt=datetime();

MERGE (ps2:PathStep {uid:'ps:lp:study-skills-101:step-2'})
  ON CREATE SET ps2.title='Make Five Cards + Quick Review',
                ps2.intent='Turn today’s concepts into 5 cards and sweep your notes.',
                ps2.createdAt=datetime()
  ON MATCH  SET ps2.updatedAt=datetime();

MERGE (lp)-[:HAS_STEP {order:1}]->(ps1)
MERGE (lp)-[:HAS_STEP {order:2}]->(ps2);

// Step 1 links
MERGE (ps1)-[:PRIMARY_KNOWLEDGE]->(:Ku {uid:'ku:note-taking-basics'})
MERGE (ps1)-[:SUPPORTING_KNOWLEDGE]->(:Ku {uid:'ku:distraction-handling'})
MERGE (ps1)-[:HAS_PRINCIPLE]->(:Principle {uid:'pr:plan-then-execute'})
MERGE (ps1)-[:HAS_PRINCIPLE]->(:Principle {uid:'pr:small-wins'})
MERGE (ps1)-[:OFFERS_CHOICE]->(:Choice {uid:'ch:start-25min-now'})
MERGE (ps1)-[:OFFERS_CHOICE]->(:Choice {uid:'ch:plan-two-blocks-tomorrow'})
MERGE (ps1)-[:SUGGESTS_HABIT]->(:Habit {uid:'hb:daily-25min-focus'})
MERGE (ps1)-[:ASSIGNS_TASK]->(:Task {uid:'tk:log-first-3-blocks'})
MERGE (ps1)-[:APPEARS_AS {frequency_hint:'daily'}]->(:EventTemplate {uid:'ev:study-block-25min'})

// Step 2 links
MERGE (ps2)-[:PRIMARY_KNOWLEDGE]->(:Ku {uid:'ku:spaced-repetition-basics'})
MERGE (ps2)-[:HAS_PRINCIPLE]->(:Principle {uid:'pr:small-wins'})
MERGE (ps2)-[:OFFERS_CHOICE]->(:Choice {uid:'ch:create-5-flashcards'})
MERGE (ps2)-[:SUGGESTS_HABIT]->(:Habit {uid:'hb:weekly-review-30min'})
MERGE (ps2)-[:ASSIGNS_TASK]->(:Task {uid:'tk:make-5-cards'})
MERGE (ps2)-[:ASSIGNS_TASK]->(:Task {uid:'tk:weekly-review'})

// Cross-links
MERGE (hb1:Habit {uid:'hb:daily-25min-focus'})
MERGE (ku3:Ku {uid:'ku:distraction-handling'})
MERGE (hb1)-[:REINFORCES]->(ku3)
MERGE (hb1)-[:APPEARS_IN_PATH]->(:Lp {uid:'lp:study-skills-101'})

MERGE (hb2:Habit {uid:'hb:weekly-review-30min'})
MERGE (ku2:Ku {uid:'ku:spaced-repetition-basics'})
MERGE (hb2)-[:REINFORCES]->(ku2)
MERGE (hb2)-[:APPEARS_IN_PATH]->(:Lp {uid:'lp:study-skills-101'})

MERGE (tk1:Task {uid:'tk:log-first-3-blocks'})
MERGE (gl:Goal {uid:'gl:study-sprint-beginner'})
MERGE (ku1:Ku {uid:'ku:note-taking-basics'})
MERGE (tk1)-[:SUPPORTS_GOAL]->(gl)
MERGE (tk1)-[:ABOUT]->(ku1)

MERGE (tk2:Task {uid:'tk:make-5-cards'})
MERGE (tk2)-[:ABOUT]->(ku2)

MERGE (ch1:Choice {uid:'ch:start-25min-now'})
MERGE (ch1)-[:CREATES_TASK]->(tk1)
MERGE (ch1)-[:NUDGES_HABIT]->(hb1)

MERGE (ch3:Choice {uid:'ch:create-5-flashcards'})
MERGE (ch3)-[:CREATES_TASK]->(tk2)
MERGE (ch3)-[:NUDGES_HABIT]->(hb2)

MERGE (tk1)-[:PROJECTS_AS]->(:EventTemplate {uid:'ev:study-block-25min'})

// Conversation
MERGE (cv:Conversation {uid:'cv:2025-10-04:study-starter'})
  ON CREATE SET cv.title='Start with one clean block',
                cv.summary='Pick a topic, set 25 minutes, and log one sentence.',
                cv.tags=['conversation','onboarding','study'],
                cv.createdAt=datetime()
  ON MATCH  SET cv.updatedAt=datetime();

MERGE (cv)-[:REFERENCES]->(:Ku {uid:'ku:note-taking-basics'})
MERGE (cv)-[:INVITES]->(:Choice {uid:'ch:start-25min-now'})
MERGE (cv)-[:INVITES]->(:Choice {uid:'ch:create-5-flashcards'})
MERGE (cv)-[:ANCHORS]->(:PathStep {uid:'ps:lp:study-skills-101:step-1'});
