// SKUEL.app — Mindfulness 101 seed (pure Cypher, idempotent)
// Constraints & Indexes
CREATE CONSTRAINT IF NOT EXISTS FOR (n:Curriculum) REQUIRE n.uid IS UNIQUE;
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
MERGE (ku1:Curriculum {uid:'ku:breath-awareness-basics'})
  ON CREATE SET ku1.title='Breath Awareness — Basics',
                ku1.summary='A light, conversational intro to breath awareness practice.',
                ku1.tags=['breath','meditation','beginner'],
                ku1.kind='article',
                ku1.body_path='content/breath-awareness-basics.md',
                ku1.createdAt=datetime()
  ON MATCH  SET ku1.updatedAt=datetime();

MERGE (ku2:Curriculum {uid:'ku:posture-basics'})
  ON CREATE SET ku2.title='Posture — Basics',
                ku2.summary='Simple posture guidelines that don’t get in the way.',
                ku2.tags=['posture','beginner'],
                ku2.kind='article',
                ku2.createdAt=datetime()
  ON MATCH  SET ku2.updatedAt=datetime();

MERGE (ku3:Curriculum {uid:'ku:mind-wandering-happens'})
  ON CREATE SET ku3.title='Mind Wandering Happens',
                ku3.summary='Wandering is normal; gently label it and return.',
                ku3.tags=['attention','mindfulness'],
                ku3.kind='article',
                ku3.createdAt=datetime()
  ON MATCH  SET ku3.updatedAt=datetime();

// Cluster
MERGE (kc:KnowledgeCluster {uid:'kc:mindfulness-foundations'})
  ON CREATE SET kc.title='Mindfulness Foundations',
                kc.summary='A small set of articles to start mindfulness with levity.',
                kc.tags=['mindfulness','starter'],
                kc.createdAt=datetime()
  ON MATCH  SET kc.updatedAt=datetime();

MERGE (ku1:Curriculum {uid:'ku:breath-awareness-basics'})
MERGE (ku2:Curriculum {uid:'ku:posture-basics'})
MERGE (ku3:Curriculum {uid:'ku:mind-wandering-happens'})

MERGE (ku1)-[:IN_CLUSTER]->(kc)
MERGE (ku2)-[:IN_CLUSTER]->(kc)
MERGE (ku3)-[:IN_CLUSTER]->(kc);

// Principles
MERGE (pr1:Principle {uid:'pr:small-steps'})
  ON CREATE SET pr1.title='Small Steps Beat Big Bursts',
                pr1.summary='Favor consistent tiny actions over heroic sprints.',
                pr1.tags=['discipline','habits'],
                pr1.createdAt=datetime()
  ON MATCH  SET pr1.updatedAt=datetime();

MERGE (pr2:Principle {uid:'pr:attention-over-intensity'})
  ON CREATE SET pr2.title='Attention Over Intensity',
                pr2.summary='Gentle attention matters more than force.',
                pr2.tags=['attention','mindfulness'],
                pr2.createdAt=datetime()
  ON MATCH  SET pr2.updatedAt=datetime();

// Choices
MERGE (ch1:Choice {uid:'ch:2-minutes-right-now'})
  ON CREATE SET ch1.title='Do Two Minutes Right Now',
                ch1.summary='Set a two-minute timer and follow your breath.',
                ch1.tags=['tiny','starter'],
                ch1.createdAt=datetime()
  ON MATCH  SET ch1.updatedAt=datetime();

MERGE (ch2:Choice {uid:'ch:2-minutes-before-bed'})
  ON CREATE SET ch2.title='Two Minutes Before Bed',
                ch2.summary='Close the day with a soft two-minute sit.',
                ch2.tags=['tiny','evening'],
                ch2.createdAt=datetime()
  ON MATCH  SET ch2.updatedAt=datetime();

MERGE (ch3:Choice {uid:'ch:label-one-wander'})
  ON CREATE SET ch3.title='Label One Wander',
                ch3.summary='When you notice drifting, softly say “wandering” once.',
                ch3.tags=['attention'],
                ch3.createdAt=datetime()
  ON MATCH  SET ch3.updatedAt=datetime();

// Habits
MERGE (hb1:Habit {uid:'hb:daily-2min-breath'})
  ON CREATE SET hb1.title='Daily Two-Minute Breath',
                hb1.summary='One tiny session per day. That’s it.',
                hb1.tags=['habit','mindfulness'],
                hb1.schedule_hint='daily',
                hb1.metrics = {unit:'sessions', target_per_week:5},
                hb1.createdAt=datetime()
  ON MATCH  SET hb1.updatedAt=datetime();

MERGE (hb2:Habit {uid:'hb:label-wander-daily'})
  ON CREATE SET hb2.title='Label a Wander Daily',
                hb2.summary='Name one mind-wander each day without judgment.',
                hb2.tags=['attention','mindfulness'],
                hb2.schedule_hint='daily',
                hb2.metrics = {unit:'labels', target_per_week:5},
                hb2.createdAt=datetime()
  ON MATCH  SET hb2.updatedAt=datetime();

// Goal
MERGE (gl:Goal {uid:'gl:mindfulness-beginner'})
  ON CREATE SET gl.title='Build a gentle daily starter practice',
                gl.summary='Five short sessions per week for four weeks.',
                gl.tags=['mindfulness','starter'],
                gl.createdAt=datetime()
  ON MATCH  SET gl.updatedAt=datetime();

// Tasks
MERGE (tk1:Task {uid:'tk:log-first-5-sessions'})
  ON CREATE SET tk1.title='Log your first five sessions',
                tk1.summary='Record date, duration, and one sentence about how it felt.',
                tk1.tags=['logging','beginner'],
                tk1.estimated_minutes=3,
                tk1.priority='normal',
                tk1.createdAt=datetime()
  ON MATCH  SET tk1.updatedAt=datetime();

MERGE (tk2:Task {uid:'tk:reflect-on-first-week'})
  ON CREATE SET tk2.title='Reflect on your first week',
                tk2.summary='Write 3–5 sentences about what you noticed.',
                tk2.tags=['reflection'],
                tk2.estimated_minutes=5,
                tk2.priority='normal',
                tk2.createdAt=datetime()
  ON MATCH  SET tk2.updatedAt=datetime();

// Event Template
MERGE (ev:EventTemplate {uid:'ev:practice-block-2min'})
  ON CREATE SET ev.title='Breath Practice — 2 min',
                ev.summary='Calendar projection of a tiny practice block.',
                ev.duration_minutes=2,
                ev.render = {color_hint:'teal', icon_hint:'timer'},
                ev.createdAt=datetime()
  ON MATCH  SET ev.updatedAt=datetime();

// Learning Path & Steps
MERGE (lp:Lp {uid:'lp:mindfulness-101'})
  ON CREATE SET lp.title='Mindfulness 101 — Light & Conversational',
                lp.summary='Choose-your-own-adventure starter path with tiny practices.',
                lp.tags=['mindfulness','beginner','conversational'],
                lp.audience='teen-general',
                lp.progress_model = {kind:'simple-checkpoints', completion_rule:'any-4-days-in-7'},
                lp.createdAt=datetime()
  ON MATCH  SET lp.updatedAt=datetime();

MERGE (ps1:PathStep {uid:'ps:lp:mindfulness-101:step-1'})
  ON CREATE SET ps1.title='Two Minutes Today',
                ps1.intent='Try one two-minute breath session, note what you notice.',
                ps1.createdAt=datetime()
  ON MATCH  SET ps1.updatedAt=datetime();

MERGE (ps2:PathStep {uid:'ps:lp:mindfulness-101:step-2'})
  ON CREATE SET ps2.title='Name The Wanders',
                ps2.intent='Label mind-wanders without judgment once per session.',
                ps2.createdAt=datetime()
  ON MATCH  SET ps2.updatedAt=datetime();

MERGE (lp)-[:HAS_STEP {order:1}]->(ps1)
MERGE (lp)-[:HAS_STEP {order:2}]->(ps2);

// Step 1 links
MERGE (ps1)-[:PRIMARY_KNOWLEDGE]->(:Curriculum {uid:'ku:breath-awareness-basics'})
MERGE (ps1)-[:SUPPORTING_KNOWLEDGE]->(:Curriculum {uid:'ku:posture-basics'})
MERGE (ps1)-[:HAS_PRINCIPLE]->(:Principle {uid:'pr:small-steps'})
MERGE (ps1)-[:OFFERS_CHOICE]->(:Choice {uid:'ch:2-minutes-right-now'})
MERGE (ps1)-[:OFFERS_CHOICE]->(:Choice {uid:'ch:2-minutes-before-bed'})
MERGE (ps1)-[:SUGGESTS_HABIT]->(:Habit {uid:'hb:daily-2min-breath'})
MERGE (ps1)-[:ASSIGNS_TASK]->(:Task {uid:'tk:log-first-5-sessions'})
MERGE (ps1)-[:APPEARS_AS {frequency_hint:'daily'}]->(:EventTemplate {uid:'ev:practice-block-2min'})

// Step 2 links
MERGE (ps2)-[:PRIMARY_KNOWLEDGE]->(:Curriculum {uid:'ku:mind-wandering-happens'})
MERGE (ps2)-[:HAS_PRINCIPLE]->(:Principle {uid:'pr:attention-over-intensity'})
MERGE (ps2)-[:OFFERS_CHOICE]->(:Choice {uid:'ch:label-one-wander'})
MERGE (ps2)-[:SUGGESTS_HABIT]->(:Habit {uid:'hb:label-wander-daily'})
MERGE (ps2)-[:ASSIGNS_TASK]->(:Task {uid:'tk:reflect-on-first-week'})

// Cross-links
MERGE (hb1:Habit {uid:'hb:daily-2min-breath'})
MERGE (ku1:Curriculum {uid:'ku:breath-awareness-basics'})
MERGE (hb1)-[:REINFORCES]->(ku1)
MERGE (hb1)-[:APPEARS_IN_PATH]->(:Lp {uid:'lp:mindfulness-101'})

MERGE (tk1:Task {uid:'tk:log-first-5-sessions'})
MERGE (gl:Goal {uid:'gl:mindfulness-beginner'})
MERGE (tk1)-[:SUPPORTS_GOAL]->(gl)
MERGE (tk1)-[:ABOUT]->(ku1)

MERGE (ch1:Choice {uid:'ch:2-minutes-right-now'})
MERGE (ch1)-[:CREATES_TASK]->(tk1)
MERGE (ch1)-[:NUDGES_HABIT]->(hb1)

MERGE (tk1)-[:PROJECTS_AS]->(:EventTemplate {uid:'ev:practice-block-2min'})

// Conversation
MERGE (cv:Conversation {uid:'cv:2025-10-04:breath-starter'})
  ON CREATE SET cv.title='Two minutes is enough to begin',
                cv.summary='A light, conversational nudge introducing the step.',
                cv.tags=['conversation','onboarding','mindfulness'],
                cv.createdAt=datetime()
  ON MATCH  SET cv.updatedAt=datetime();

MERGE (cv)-[:REFERENCES]->(:Curriculum {uid:'ku:breath-awareness-basics'})
MERGE (cv)-[:INVITES]->(:Choice {uid:'ch:2-minutes-right-now'})
MERGE (cv)-[:INVITES]->(:Choice {uid:'ch:2-minutes-before-bed'})
MERGE (cv)-[:ANCHORS]->(:PathStep {uid:'ps:lp:mindfulness-101:step-1'});
