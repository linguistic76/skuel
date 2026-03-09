---
title: RevisedExercise — AI + Student Collaboration (Future)
created: 2026-03-07
status: deferred
priority: post-mvp
related:
- FOUR_PHASED_LEARNING_LOOP.md
- REPORT_ARCHITECTURE.md
---

# RevisedExercise: AI + Student Collaboration Mode

> Deferred idea from the Five-Phase Learning Loop design session (2026-03-07).
> MVP uses teacher-created RevisedExercise only. This doc captures the richer
> collaboration model for future implementation.

## Context

The Five-Phase Learning Loop adds `REVISED_EXERCISE` as a teacher-created entity
between SubmissionReport and the next Submission. In the MVP, only the teacher
creates RevisedExercises manually.

This document captures the **combination approach** — where AI, student, and
teacher collaborate to produce the RevisedExercise.

## The Three-Role Collaboration

```
SubmissionReport arrives
        |
        v
   ┌─────────────────────────────────────────────┐
   │  AI generates suggested RevisedExercise      │
   │  (from original Exercise + Feedback gaps)     │
   │                                               │
   │  Student reviews AI suggestion, modifies it:  │
   │  - Adds their own reflection                  │
   │  - Adjusts scope / focus areas                │
   │  - Demonstrates understanding of gaps         │
   │                                               │
   │  Teacher approves / refines final version      │
   └─────────────────────────────────────────────┘
        |
        v
   RevisedExercise v2 (approved) → Student submits against it
```

## Why This Is Pedagogically Powerful

1. **AI contribution**: Scalable — generates targeted instructions from feedback
   without requiring teacher time for every student. Identifies specific gaps
   from the SubmissionReport and maps them to new exercise instructions.

2. **Student contribution**: Metacognitive — the student must engage with the
   feedback to modify the exercise. "I understand what I need to practice" is
   a higher-order skill than "I'll try again." The student's modifications
   reveal whether they actually understood the feedback.

3. **Teacher contribution**: Quality control — teacher has final approval.
   Can catch AI hallucinations or student misunderstandings. Can add nuance
   that neither AI nor student would generate alone.

## Implementation Notes (When Ready)

- `ProcessorType.HYBRID` already exists — fits this three-role model
- AI generation could use the same LLM infrastructure as SubmissionReport
  (Exercise instructions as prompt, Feedback as context)
- Student draft could use annotation fields similar to ActivityReport
  (`user_revision`, `annotation_mode`)
- Teacher approval could reuse the review queue pattern from ADR-040
- Status flow: `AI_DRAFTED → STUDENT_MODIFIED → TEACHER_APPROVED → ACTIVE`

## Relationship to MVP

The MVP (teacher-created only) establishes:
- The `REVISED_EXERCISE` EntityType and its position in the loop
- The graph relationships (backward to feedback, forward to submission)
- The version numbering system
- The sharing infrastructure

The collaboration mode layers on top without changing the entity structure —
it only changes WHO creates the content and adds an approval workflow.
