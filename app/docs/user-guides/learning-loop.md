# The Learning Loop

*Last updated: 2026-03-08*

## Overview

The Learning Loop is the core of SKUEL. Everything in the app — tasks, goals, habits, journals, curriculum — exists to serve one purpose: helping you learn by doing, reflecting on what you did, and doing it better next time.

The loop has five phases:

```
Article → Exercise → Submission → Feedback → Revised Exercise → ...
```

Each phase builds on the last. You never just consume content — you engage with it, get a response, and refine your understanding. The loop repeats until mastery emerges.

---

## The Five Phases

### Phase 1: Article — The Knowledge

Articles are teaching compositions written by teachers. They present ideas, concepts, and narratives that form the foundation of what you'll practice. Each Article composes one or more atomic knowledge units (Kus) into a readable narrative.

You don't need to memorize Articles. You need to *engage* with them — and that engagement happens in the next phase.

**Where to find them:** Browse Articles by category, discover them through Learning Paths, or follow Askesis's recommendations.

### Phase 2: Exercise — The Instructions

An Exercise is what your teacher asks you to do with the knowledge. It contains clear instructions for what to produce — an essay, a voice recording, a reflection, a creative piece.

Exercises come in two forms:

| Type | Created by | Purpose |
|------|-----------|---------|
| **Assigned** | Your teacher | Classroom work with a due date |
| **Personal** | You | Self-directed practice with AI feedback |

Assigned Exercises appear automatically on your assignments page. Personal Exercises let you practice on your own terms and get AI-generated feedback.

**Where to find them:** Your assignments page shows all Exercises assigned to you, with due dates and status.

### Phase 3: Submission — Your Work

This is where you show what you've learned. Upload your work — text, audio, or other files — against an Exercise.

**How it works:**

1. Open the Exercise and click **Submit**
2. Upload your file (audio files are automatically transcribed)
3. Your submission is linked to the Exercise and, for assigned work, automatically shared with your teacher

Your submission's status moves through: **Submitted → Processing → Completed**. Once completed, it's ready for feedback.

**Journals** are a special kind of submission — reflective writing that gets AI-processed automatically. You can submit journals independently of any Exercise.

### Phase 4: Feedback — The Response

After you submit, the system responds. Feedback can come from two sources:

| Source | How it works |
|--------|-------------|
| **Teacher** | Your teacher reads your submission in their review queue and writes personalized feedback |
| **AI** | The Exercise's instructions are used as a prompt to generate automated feedback |

When your teacher reviews your work, they choose one of three outcomes:

- **Feedback** — Written evaluation of your work. You reflect and learn.
- **Revision requested** — Your work needs another pass. You'll get specific guidance on what to improve.
- **Approved** — Your work meets the standard. The loop closes for this Exercise.

**Activity Reports** are a second kind of feedback — not about a single submission, but about your patterns over time. SKUEL looks at everything you've been doing across Tasks, Goals, Habits, Events, Choices, and Principles, then generates a qualitative analysis of your progress. These can be AI-generated on a schedule, requested on-demand, or written by an admin.

You can annotate your Activity Reports with your own reflections, and those annotations feed into the next report — creating a feedback loop about the feedback itself.

### Phase 5: Revised Exercise — The Refinement

If your feedback identifies specific gaps, your teacher can create a Revised Exercise — a new set of instructions that targets exactly what you need to work on.

Revised Exercises:
- Reference the specific feedback they're addressing
- Contain tailored instructions for your next attempt
- Appear in your daily plan and shared inbox
- Link back to the original Exercise, forming a traceable revision chain

You submit against the Revised Exercise just like the original, and the cycle continues: submission → feedback → revision → submission → ... until mastery.

---

## The Two Tracks

The Learning Loop operates on two parallel tracks:

### Curriculum Track (Artifact-Based)

```
Article → Exercise → Submission → Feedback → Revised Exercise → ...
```

This is the explicit learning cycle. You engage with specific curriculum content, produce work, and receive targeted feedback on that work.

### Activity Track (Pattern-Based)

```
Daily activity (Tasks, Goals, Habits, Events, Choices, Principles)
        ↓ over time
   Activity Report
        ↓
   Your annotations + reflection
        ↓
   Next Activity Report (informed by your reflections)
```

This track responds to how you're *living* the knowledge — not just what you submitted, but what you're doing day to day. SKUEL measures knowledge by how it shows up in your habits, choices, tasks, and goals.

Both tracks close the same way: you do something, the system responds, you reflect, and the next iteration is better.

---

## Askesis — Your Learning Companion

Askesis is SKUEL's Socratic companion. It doesn't lecture or deliver content — it asks questions that help you discover your own understanding.

Askesis knows two things deeply:
1. **The curriculum** — what Articles exist, how they connect, what's prerequisite to what
2. **You** — what you've engaged with, where your gaps are, what your journals reveal about your thinking

Based on this, Askesis meets you where you are:

| Your state | Askesis's approach |
|-----------|-------------------|
| Consistent engagement | **Socratic** — asks questions that reveal your thinking |
| Lots of open questions | **Exploratory** — follows your curiosity |
| Low momentum | **Encouraging** — warm and low-pressure |
| First encounter | **Direct** — orients you, then shifts to Socratic |

You can talk with Askesis from any Article page, any Learning Path, or from the Askesis home page for open-ended dialogue.

---

## A Typical Learning Cycle

Here's what the loop looks like in practice:

1. **Discover** — You browse Articles or follow a Learning Path. Askesis might suggest what to explore next based on your recent journals and activity.

2. **Receive instructions** — Your teacher assigns an Exercise, or you create a Personal Exercise for self-directed practice.

3. **Do the work** — You produce something: write an essay, record a voice reflection, complete a creative piece. Upload it as a Submission.

4. **Get feedback** — Your teacher writes feedback, or the AI evaluates your work against the Exercise instructions. You read the feedback and reflect.

5. **Refine** — If revision is needed, your teacher creates a Revised Exercise targeting your specific gaps. You submit again with focused improvements.

6. **Repeat** — The cycle continues. Each iteration builds on the last. Meanwhile, your daily activity across all domains feeds into periodic Activity Reports that show your broader growth patterns.

---

## The Learning Dashboard

The Pathways Dashboard at `/pathways` is your home base for tracking progress through the loop. Everything you see here is live data — your actual Learning Paths, your real mastery progress, your knowledge profile.

### What you see

- **Learning Overview** — Total hours across your enrolled paths, concepts mastered, active path count, and completion rate. These numbers come from your real engagement history, not projections.
- **Active Learning Paths** — Each path shows your current progress percentage, which step you're on, and difficulty level. Click "Continue Learning" to jump to where you left off.
- **Analytics** (at `/pathways/analytics`) — A deeper view: concepts mastered vs. in-progress, average retention score, concepts needing review, and concepts you're struggling with.

### Learning Paths and Steps

A Learning Path is a structured sequence of Learning Steps. Each step references specific curriculum (Articles, Kus) and tracks your mastery independently.

| Concept | What it is |
|---------|-----------|
| **Learning Path** | An ordered sequence of steps toward a learning goal. Has outcomes, estimated hours, and a difficulty level. |
| **Learning Step** | One unit of work within a path. Has its own mastery threshold, difficulty, estimated hours, and links to knowledge units. |
| **Mastery** | Each step tracks mastery 0.0-1.0. A step is "mastered" when your score crosses its threshold (default 0.7). |

**How paths connect to the loop:** Steps within a path point to Articles and Exercises. When you complete an Exercise's submission-feedback cycle, your mastery on the related step increases. The path's progress is the ratio of mastered steps to total steps.

### Browsing and enrolling

Visit `/pathways/browse` to see all available Learning Paths. Each card shows the path's difficulty, estimated hours, and tags. Click "View Details" to see the full step list, learning outcomes, and your enrollment status. Enroll to add a path to your dashboard.

### For teachers creating paths

Learning Paths are curriculum — created by teachers or admins, shared with all users. When you create a path:

1. Define the path's title, description, outcomes, and estimated hours
2. Create Learning Steps in sequence, each referencing the Articles and Kus students should engage with
3. Set mastery thresholds per step (higher for critical concepts, lower for introductory ones)
4. Students enroll and progress through steps by completing the associated Exercises

The path structure gives students a clear road through your curriculum while the loop (Exercise -> Submission -> Feedback -> Revision) ensures they actually engage with each step's content.

---

## For Teachers

Teachers drive the loop from the other side:

1. **Create curriculum** — Write Articles that present knowledge. Create Exercises that operationalize that knowledge into concrete assignments.

2. **Assign work** — Set an Exercise's scope to Assigned, choose a due date, and target a Group (classroom). Students see it automatically.

3. **Review submissions** — Your review queue shows pending student work. For each submission, you can:
   - Write feedback (creates a SubmissionReport record)
   - Request revision (student resubmits)
   - Approve (loop closes)

4. **Create revisions** — When feedback reveals specific gaps, create a Revised Exercise with targeted instructions. It's automatically shared with the student.

5. **Track progress** — Monitor submission rates, revision chains, and mastery progression across your class.

---

## Key Concepts

| Concept | What it means |
|---------|--------------|
| **Mastery** | Not "I read it" but "I live it." Measured through habits, choices, journals, tasks — not just submissions. |
| **Substance** | Knowledge has weight when it changes behavior. Habits contribute more to substance than passive reading. |
| **Revision chain** | The sequence Exercise → Submission → Feedback → Revised Exercise → Submission v2 → ... Each link is a traceable entity. |
| **Activity Report** | A periodic synthesis of everything you've been doing, with AI-generated insights about your patterns. |
| **Annotation** | Your voice alongside the system's analysis. Add your own reflections to Activity Reports — they inform the next one. |
| **ZPD** | Zone of Proximal Development. Askesis reads the curriculum graph to know what you're ready to learn next — not too easy, not too hard. See the [standalone ZPD guide](zpd.md). |

---

## Reference Documentation

- `/docs/architecture/FOUR_PHASED_LEARNING_LOOP.md` — Architecture overview
- `/docs/architecture/REPORT_ARCHITECTURE.md` — Report system design
- `/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — Askesis vision and pedagogy
- `/docs/decisions/ADR-038-content-sharing-model.md` — Content sharing model
- `/docs/decisions/ADR-040-teacher-assignment-workflow.md` — Teacher assignment workflow
