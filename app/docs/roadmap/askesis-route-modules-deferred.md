# Deferred: Askesis Route Module Split

**Status:** Deferred — not worth churn at current scale
**Revisit when:** Any single Askesis concern (e.g. chat, history, analytics) exceeds ~150 lines of substantive route logic

## What and Why

`askesis_ui.py` and `askesis_api.py` are currently monolithic route factories covering chat, history, analytics, and settings. As Askesis feature surface grows, these could be split into bounded modules — one per concern.

**Example target structure:**
```
adapters/inbound/askesis/
    askesis_chat_api.py       # /api/askesis/query, /api/askesis/answer
    askesis_history_api.py    # /api/askesis/history, /api/askesis/clear
    askesis_analytics_api.py  # /api/askesis/insights, /api/askesis/health
    askesis_ui.py             # All page routes
```

## Why Deferred

Routes are mostly stubs today. Splitting files before the logic exists is premature abstraction — adding filesystem complexity with no navigability benefit. The current monolithic factories are readable and correct.

## Trigger Condition

Revisit when:
1. Any single concern (chat, history, analytics) exceeds ~150 lines of substantive route logic, OR
2. Two developers are regularly editing the same route file for different features

At that point the split becomes an organizational gain, not churn.
