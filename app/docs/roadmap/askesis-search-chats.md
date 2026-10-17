---
title: "Askesis \"Search chats\" — a Field With No Behaviour"
updated: 2026-10-17
status: "registered"
registered: 2026-10-17
ruled: 2026-10-17
trigger: "the Askesis review"
check: "git grep -n -A12 'def _sb_search_field' -- ui/askesis/chat.py — the Input still has no name= and no hx_*/x-* attribute; git grep -n 'ConversationContext' -- core/services/askesis/ — Askesis still keeps its turns in process memory"
---

# Askesis "Search chats" — a Field With No Behaviour

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The Askesis sidebar renders a "Search chats" field (`_sb_search_field`, `ui/askesis/chat.py`)
above the conversation history. It has no `name`, no handler and no results: typing into it does
nothing. It is decoration that looks like a control — a keyboard or screen-reader user reaches a
search box that cannot search.

There is nothing for it to search yet. The history pane beside it (`_sb_history`) is static
("No conversations yet"), and Askesis holds its turns in the process-local `ConversationContext`
(`core/services/askesis/query_processor.py`); only the journals discussion path persists
conversations, through the ADR-078 store (see
[teacher-askesis-interface-deferred.md](teacher-askesis-interface-deferred.md), item 2).

**Ruled (Mike, 2026-10-17):** not fixed in the form-residuals PR; registered here for the Askesis
review, which decides whether the field gets a real search (once Askesis histories persist) or
leaves the sidebar until then.
