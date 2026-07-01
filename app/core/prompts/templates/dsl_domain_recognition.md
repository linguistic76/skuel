You are analyzing journal text to identify activities that map to SKUEL's entity types.

## ENTITY TYPES

### Activity Domains (6) - What I DO:
- @context(task) - One-time actions with deadlines
- @context(habit) - Recurring behaviors to build
- @context(goal) - Outcomes to achieve
- @context(event) - Scheduled appointments/meetings
- @context(principle) - Values/beliefs to embody
- @context(choice) - Decisions to make

### Curriculum Domains (3) - What I LEARN:
- @context(ku) - Knowledge to acquire (concepts, facts, skills)
- @context(ps) - Path steps (curriculum content that composes Kus)
- @context(lp) - Learning paths (ordered sequences of path steps)

### Other Domains - How I ORGANIZE:
- @context(finance) - Money matters (expenses/income/budget)
- @context(report) - Content to process (files, voice memos)
- @context(calendar) - Time blocks to schedule

### The Destination - Where I'm GOING:
- @context(lifepath) - Life vision alignment, ultimate goals

## DSL SYNTAX

Each activity line should include:
- @context(type) - REQUIRED: The domain type
- @priority(low|medium|high|critical) - Optional: Importance level
- @when(date/time) - Optional: Due date, deadline, or scheduled time
- @repeat(daily|weekly|monthly|yearly) - Optional: For habits
- @duration(minutes) - Optional: Time estimate
- @energy(low|medium|high) - Optional: Energy state requirements
- @amount(number) - Optional: For finance items
- @goal(goal_description) - Optional: Link to a goal
- @principle(principle_name) - Optional: Link to a principle
- @ku(knowledge_unit) - Optional: Link to knowledge

## EXAMPLES

Input: "I need to finish the quarterly report by Friday. Also want to start meditating daily - 10 minutes each morning."

Output:
- @context(task) Finish the quarterly report @when(Friday) @priority(high)
- @context(habit) Meditate @repeat(daily) @duration(10) @energy(low)

Input: "Thinking about whether to take that new job offer. Spent $150 on groceries today."

Output:
- @context(choice) Decide on job offer @priority(high)
- @context(finance) Groceries @amount(150) @when(today)

Input: "I want to learn Python for data science. Need to master pandas first."

Output:
- @context(lp) Python for data science @priority(high)
- @context(ku) Pandas library fundamentals @goal(Python for data science)

Input: "Meeting with Sarah at 3pm tomorrow. Life goal: become a respected teacher who inspires others."

Output:
- @context(event) Meeting with Sarah @when(tomorrow 3pm)
- @context(lifepath) Become a respected teacher who inspires others

## INSTRUCTIONS

1. Read the journal text carefully
2. Identify all actionable items, decisions, learnings, and reflections
3. Classify each into the appropriate entity type
4. Output ONLY the structured activity lines (one per line, starting with -)
5. Preserve the original intent and key details
6. Add appropriate attributes (@when, @priority, @duration, etc.)
7. If something doesn't fit a domain, skip it (narrative text is fine)
8. A USER CONTEXT section (if present) is background about the user, NOT material
   to extract. Never output an activity line for an item that appears only in
   USER CONTEXT; use it solely to recognise and accurately classify/phrase items
   that genuinely appear in the JOURNAL TEXT.
{user_context}
## JOURNAL TEXT TO ANALYZE:

{journal_text}

## STRUCTURED OUTPUT (activity lines only):
