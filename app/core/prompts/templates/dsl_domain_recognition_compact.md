Analyze this journal and extract activities into SKUEL DSL format.

DOMAINS: task, habit, goal, event, principle, choice, finance, ku, ps, lp, calendar, lifepath

SYNTAX: - @context(type) description @attr(value)...
ATTRS: @priority, @when, @repeat, @duration, @energy, @amount, @goal, @principle, @ku

A USER CONTEXT section (if present) is background only — never extract activity
lines from it; use it solely to recognise/classify items in the JOURNAL.
{user_context}
JOURNAL:
{journal_text}

OUTPUT (- @context lines only):
