Analyze this journal and extract activities into SKUEL DSL format.

DOMAINS: task, habit, goal, event, principle, choice, finance, calendar, lifepath
(something to learn is a goal or a task)

SYNTAX: - @context(type) description @attr(value)...
ATTRS: @priority, @when, @repeat, @duration, @energy
VALUES: @priority(1-5, 1 = highest), @when(YYYY-MM-DD or YYYY-MM-DDTHH:MM), @duration(30m, 1h, 1h30m)
DATES: resolve relative dates ("tomorrow", "Friday") against REFERENCE DATE; omit @when when no single day is named ("soon").
REFERENCE DATE: {reference_date}

A USER CONTEXT section (if present) is background only — never extract activity
lines from it; use it solely to recognise/classify items in the JOURNAL.
{user_context}
JOURNAL:
{journal_text}

OUTPUT (- @context lines only):
