---
title: SKUEL Activity DSL - Usage Guide
updated: 2025-11-30
status: current
category: dsl
tags: [dsl, examples, patterns, guide, usage]
related: [DSL_SPECIFICATION.md, DSL_IMPLEMENTATION.md]
---

# SKUEL Activity DSL - Usage Guide

*Practical examples and patterns for writing SKUEL Activity Lines*
*Last Updated: 2025-11-30*

## Quick Start

### Minimal Activity Line

The simplest valid Activity Line needs only `@context()`:

```markdown
- [ ] Call hosting provider @context(task)
```

This declares "task" as the entity type, making it queryable and processable by SKUEL.

### Adding Time

Add `@when()` for scheduling:

```markdown
- [ ] Morning meditation @context(habit) @when(2025-11-30T07:00)
```

### Common Pattern

Most Activity Lines follow this pattern:

```markdown
- [ ] Description @context(type) @when(time) @priority(N)
```

---

## Entity Types - When to Use What

### `@context(task)` - One-Off Actions

Use for concrete, completable actions:

```markdown
- [ ] Draft Teens.yoga landing page copy @context(task)
- [ ] Call Stripe support about webhook issue @context(task)
- [ ] Research competitive pricing for online courses @context(task)
```

**When to use:** Single-execution actions with clear completion criteria.

---

### `@context(habit)` - Repeated Behaviors

Use for recurring behaviors you want to track:

```markdown
- [ ] Morning meditation 20 minutes @context(habit) @repeat(daily)
- [ ] Strength training @context(habit) @repeat(weekly:Mon,Wed,Fri)
- [ ] Weekly reflection journal @context(habit) @repeat(weekly:Sun)
```

**When to use:** Behaviors you want to repeat and track streaks.

---

### `@context(goal)` - Desired Outcomes

Use for aspirational targets:

```markdown
- [ ] Reach 100 paid Teens.yoga members @context(goal)
- [ ] Complete Python certification @context(goal)
- [ ] Save $10,000 emergency fund @context(goal)
```

**When to use:** Long-term objectives measured by metrics or milestones.

---

### `@context(event)` - Scheduled Occurrences

Use for calendar events and meetings:

```markdown
- [ ] Teens.yoga workshop at local school @context(event) @when(2025-12-15T14:00) @duration(2h)
- [ ] Quarterly planning session @context(event) @when(2025-12-01T09:00) @duration(3h)
```

**When to use:** Time-specific occurrences, often involving other people.

---

### `@context(learning)` - Educational Activities

Use for knowledge acquisition:

```markdown
- [ ] Read Chapter 3: Law of Success @context(learning) @ku(ku:mindset/law-of-success)
- [ ] Watch Python async programming tutorial @context(learning) @duration(45m)
- [ ] Practice yoga asana sequence @context(learning) @duration(1h)
```

**When to use:** Activities focused on building knowledge or skills.

---

### Multiple Contexts

Combine contexts when activities span categories:

```markdown
- [ ] Publish first SEL mini-course @context(task,goal,learning)
- [ ] Daily gratitude journal @context(habit,reflection)
- [ ] Record transcript on secular spirituality for teens @context(task,learning,reflection)
```

**When to use:** Activities that legitimately belong to multiple domains.

---

## Habit Patterns - Repetition Examples

### Daily Habits

```markdown
- [ ] Morning pages writing @context(habit) @repeat(daily) @duration(20m) @energy(creative)
- [ ] Vitamin D supplement @context(habit) @repeat(daily)
- [ ] Evening wind-down routine @context(habit) @repeat(daily) @when(21:00) @duration(30m)
```

### Weekly Patterns

```markdown
- [ ] Strength training @context(habit) @repeat(weekly:Mon,Wed,Fri) @duration(45m) @energy(physical)
- [ ] Meal prep for week @context(habit) @repeat(weekly:Sun) @duration(2h)
- [ ] Review weekly goals @context(habit,reflection) @repeat(weekly:Sun) @duration(30m)
```

### Monthly Patterns

```markdown
- [ ] Review monthly budget @context(habit,metric) @repeat(monthly:1) @duration(1h)
- [ ] Pay rent @context(task,habit) @repeat(monthly:1)
- [ ] Deep clean apartment @context(habit) @repeat(monthly:1,15) @duration(2h)
```

### Interval-Based

```markdown
- [ ] Water houseplants @context(habit) @repeat(every:3d) @duration(15m)
- [ ] Change air filter @context(habit) @repeat(every:30d)
```

---

## Energy States - Scheduling Intelligence

### Focus Work

```markdown
- [ ] Write Askesis architecture documentation @context(task) @energy(focus) @duration(2h)
- [ ] Debug complex Neo4j query issue @context(task) @energy(focus) @duration(90m)
- [ ] Plan Q1 curriculum structure @context(task) @energy(focus,creative) @duration(2h)
```

**Use focus energy for:** Deep work, problem-solving, architecture design.

---

### Light Tasks

```markdown
- [ ] Respond to support emails @context(task) @energy(light) @duration(30m)
- [ ] File receipts for tax prep @context(task) @energy(light) @duration(20m)
- [ ] Update social media bio @context(task) @energy(light) @duration(10m)
```

**Use light energy for:** Administrative tasks, easy maintenance, quick wins.

---

### Physical Activities

```markdown
- [ ] Morning run 5K @context(habit) @energy(physical) @repeat(daily) @duration(30m)
- [ ] Yoga practice @context(habit) @energy(physical,spiritual) @repeat(daily) @duration(1h)
- [ ] Walking meeting with collaborator @context(event) @energy(physical,social) @duration(45m)
```

**Use physical energy for:** Movement, exercise, active practices.

---

### Creative Flow

```markdown
- [ ] Brainstorm Teens.yoga course topics @context(task) @energy(creative) @duration(1h)
- [ ] Design new landing page mockup @context(task) @energy(creative,focus) @duration(2h)
- [ ] Free-write morning pages @context(habit) @energy(creative) @repeat(daily) @duration(20m)
```

**Use creative energy for:** Ideation, design, open-ended exploration.

---

### Restorative Activities

```markdown
- [ ] Afternoon nap @context(habit) @energy(rest) @repeat(daily) @when(14:00) @duration(20m)
- [ ] Evening meditation @context(habit) @energy(rest,spiritual) @repeat(daily) @duration(20m)
- [ ] Read fiction before bed @context(habit) @energy(rest) @repeat(daily) @duration(30m)
```

**Use rest energy for:** Recovery, restoration, passive activities.

---

### Mixed Energy States

Combine energy states for complex activities:

```markdown
- [ ] Record podcast on yoga philosophy @context(task) @energy(creative,focus,social) @duration(1h)
- [ ] Walking meditation @context(habit) @energy(physical,spiritual,rest) @duration(30m)
- [ ] Whiteboard session with team @context(event) @energy(social,creative,focus) @duration(2h)
```

---

## Knowledge Integration

### Linking to Knowledge Units

```markdown
- [ ] Practice discernment meditation @context(habit) @ku(ku:sel/thought-not-reality) @repeat(daily)
- [ ] Review Linear Algebra concepts @context(learning) @ku(ku:math/linear-algebra) @duration(1h)
- [ ] Apply Stoic principles to daily stressors @context(reflection) @ku(ku:philosophy/stoicism)
```

**Pattern:** Use `@ku()` to track which knowledge is being applied or learned.

---

### Multiple Knowledge Connections

Use `@link()` for additional KU references:

```markdown
- [ ] Integrate SEL principles into Teens.yoga curriculum
      @context(task,learning)
      @ku(ku:sel/core-principles)
      @link(ku:teens-yoga/curriculum-design, ku:education/pedagogy)
      @duration(3h)
```

---

## Goal Alignment

### Linking Tasks to Goals

```markdown
- [ ] Publish Instagram post about upcoming workshop
      @context(task)
      @link(goal:teens-yoga/100-followers, goal:teens-yoga/workshop-signups)
      @duration(30m)
      @energy(creative,social)
```

### Habits Supporting Goals

```markdown
- [ ] Daily content creation practice
      @context(habit)
      @repeat(daily)
      @link(goal:teens-yoga/consistent-content)
      @duration(45m)
      @energy(creative)
```

---

## Principle Alignment

Connect activities to guiding principles:

```markdown
- [ ] Review business decisions against core values
      @context(reflection,habit)
      @repeat(weekly:Fri)
      @link(principle:discernment-first, principle:awareness-before-action)
      @duration(30m)
      @energy(focus,spiritual)
```

---

## Complete Real-World Examples

### Morning Routine

```markdown
### Morning Routine 2025-11-30

- [ ] Wake up at 6am @context(habit) @repeat(daily) @when(2025-11-30T06:00)
- [ ] Morning meditation 20 minutes @context(habit) @repeat(daily) @when(2025-11-30T06:15) @duration(20m) @energy(spiritual,rest) @ku(ku:yoga/meditation-intro)
- [ ] Morning pages writing @context(habit) @repeat(daily) @when(2025-11-30T06:40) @duration(20m) @energy(creative)
- [ ] Review daily intentions @context(habit,reflection) @repeat(daily) @when(2025-11-30T07:00) @duration(10m) @link(principle:awareness-first)
```

### Work Block

```markdown
### Deep Work - 9am-12pm

- [ ] Draft Teens.yoga lesson on focus
      @context(task,learning)
      @when(2025-11-30T09:00)
      @priority(1)
      @duration(90m)
      @energy(focus,creative)
      @ku(ku:teens-yoga/focus-lesson)
      @link(goal:teens-yoga/20-members)

- [ ] Debug calendar sync issue
      @context(task)
      @when(2025-11-30T10:45)
      @priority(2)
      @duration(45m)
      @energy(focus)

- [ ] Respond to partnership inquiry email
      @context(task)
      @when(2025-11-30T11:30)
      @priority(3)
      @duration(20m)
      @energy(light,social)
```

### Goal Planning

```markdown
### Q1 Goals 2025

- [ ] Launch Teens.yoga with 10 paying members @context(goal) @link(principle:impact-first)
- [ ] Build consistent content habit @context(goal) @link(habit:daily-content-creation)
- [ ] Complete Python certification @context(goal) @ku(ku:programming/python-advanced)
```

---

## Progression: Simple → Complex

### Level 1: Minimal

Start with just context:

```markdown
- [ ] Call doctor @context(task)
- [ ] Exercise @context(habit)
```

### Level 2: Add Time

Add scheduling:

```markdown
- [ ] Call doctor @context(task) @when(2025-11-30T14:00)
- [ ] Exercise @context(habit) @when(2025-11-30T07:00) @repeat(daily)
```

### Level 3: Add Duration & Energy

Make it energy-aware:

```markdown
- [ ] Call doctor @context(task) @when(2025-11-30T14:00) @duration(15m) @energy(light,social)
- [ ] Exercise @context(habit) @when(2025-11-30T07:00) @repeat(daily) @duration(45m) @energy(physical)
```

### Level 4: Full Integration

Connect to knowledge and goals:

```markdown
- [ ] Call doctor about preventive care plan
      @context(task)
      @when(2025-11-30T14:00)
      @duration(15m)
      @energy(light,social)
      @link(goal:health/preventive-care, principle:health-first)

- [ ] Morning strength training routine
      @context(habit)
      @when(2025-11-30T07:00)
      @repeat(weekly:Mon,Wed,Fri)
      @duration(45m)
      @energy(physical)
      @ku(ku:fitness/strength-training-basics)
      @link(goal:health/build-strength)
```

---

## Common Patterns

### Task → Habit Transition

When a one-off task becomes recurring:

```markdown
# Before: One-off task
- [ ] Write blog post @context(task)

# After: Recurring habit
- [ ] Write blog post @context(habit) @repeat(weekly:Mon) @duration(2h) @energy(creative,focus)
```

### Habit → Goal Connection

Link habits to the goals they support:

```markdown
- [ ] Daily meditation practice
      @context(habit)
      @repeat(daily)
      @duration(20m)
      @energy(spiritual,rest)
      @ku(ku:yoga/meditation-intro)
      @link(goal:wellness/consistent-practice, principle:awareness-first)
```

### Multi-Domain Activities

Activities that span multiple domains:

```markdown
- [ ] Record and publish podcast episode on teen mental health
      @context(task,learning,habit)
      @when(2025-11-30T10:00)
      @duration(2h)
      @energy(creative,focus,social)
      @ku(ku:teens-yoga/mental-health)
      @link(goal:teens-yoga/thought-leadership, habit:weekly-content-creation)
      @priority(1)
```

---

## Tips for Effective Usage

### 1. Start Simple

Begin with `@context()` and `@when()`. Add complexity as needed:

```markdown
# Week 1: Basics
- [ ] Task description @context(task) @when(2025-11-30T09:00)

# Week 2: Add energy
- [ ] Task description @context(task) @when(2025-11-30T09:00) @energy(focus)

# Week 3: Connect to goals
- [ ] Task description @context(task) @when(2025-11-30T09:00) @energy(focus) @link(goal:project/milestone)
```

### 2. Consistent Ordering

Pick a tag order and stick to it for readability:

```markdown
@context(...) @when(...) @priority(...) @duration(...) @energy(...) @ku(...) @link(...)
```

### 3. Energy-Based Scheduling

Group activities by energy state for better flow:

```markdown
### Morning (High Focus)
- [ ] Architecture work @context(task) @energy(focus) @duration(2h)
- [ ] Code review @context(task) @energy(focus) @duration(1h)

### Afternoon (Light Tasks)
- [ ] Email responses @context(task) @energy(light) @duration(30m)
- [ ] Calendar scheduling @context(task) @energy(light) @duration(15m)
```

### 4. Use Habits for Patterns

Convert recurring tasks to habits with `@repeat()`:

```markdown
# ❌ Manual daily tasks
- [ ] Exercise @context(task) @when(2025-11-30T07:00)
- [ ] Exercise @context(task) @when(2025-12-01T07:00)

# ✅ Single habit definition
- [ ] Exercise @context(habit) @when(07:00) @repeat(daily) @duration(45m)
```

---

## See Also

- **Formal Grammar:** `DSL_SPECIFICATION.md`
- **Implementation Guide:** `DSL_IMPLEMENTATION.md`
- **Activity DSL Parser:** `/core/services/dsl/`
