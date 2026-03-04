---
name: prompt-templates
description: >
  Expert guide for SKUEL's centralized LLM prompt template registry.
  Use when adding a new LLM prompt, editing existing templates, or understanding
  how PROMPT_REGISTRY connects services to templates.
  TRIGGER when: implementing any LLM-powered feature, working on Askesis prompts,
  editing ProgressFeedbackGenerator, JournalOutputGenerator, LLMDSLBridgeService,
  or when asked "where do prompts live?"
allowed-tools: Read, Grep, Glob
---

# Prompt Templates — SKUEL's Centralized Registry

> "One Path Forward — prompts live in `core/prompts/templates/`, not in service code."

## Quick Reference

```python
from core.prompts import PROMPT_REGISTRY

# Render with placeholders
prompt = PROMPT_REGISTRY.render("activity_feedback",
    time_period="7d", stats_json="...", insights_section="...")

# Get template object (e.g. to access .content directly)
template = PROMPT_REGISTRY.get("activity_feedback")
```

---

## Why a Registry?

Before `core/prompts/` (March 2026), prompts lived in three places:

- **File-per-service** — `core/services/feedback/prompts/`, `core/services/submissions/journal_prompts/`
- **Inline string constants** — `DOMAIN_RECOGNITION_PROMPT` in `llm_dsl_bridge.py` (141 lines)
- **Hardcoded system prompt bug** — `OpenAIService` always sent "formats journal transcripts"

PROMPT_REGISTRY solves all three: one import, one location, one editing surface.

---

## Architecture

`core/prompts/` contains 3 Python files and 1 templates directory:

```
core/prompts/
├── __init__.py               # Exports: PromptTemplate, PROMPT_REGISTRY
├── prompt_template.py        # PromptTemplate(frozen dataclass): template_id, content, render(**kwargs)
├── registry.py               # PromptRegistry + PROMPT_REGISTRY singleton
└── templates/
    ├── activity_feedback.md
    ├── journal_activity.md
    ├── journal_articulation.md
    ├── journal_exploration.md
    ├── dsl_domain_recognition.md
    └── dsl_domain_recognition_compact.md
```

`PromptRegistry` lazy-loads on first access and caches for the process lifetime.
Missing template → `FileNotFoundError` (not `Result.fail`) — a missing template is a
programming error, not a domain failure.

---

## Template Catalog

| Template ID | Consumers | Placeholders |
|-------------|-----------|--------------|
| `activity_feedback` | `ProgressFeedbackGenerator._build_llm_prompt()` | `{time_period}`, `{depth}`, `{stats_json}`, `{insights_section}` |
| `journal_activity` | `JournalOutputGenerator._format_activity()` | `{content}` |
| `journal_articulation` | `JournalOutputGenerator._format_articulation()` | `{content}` |
| `journal_exploration` | `JournalOutputGenerator._format_exploration()` | `{content}` |
| `dsl_domain_recognition` | `LLMDSLBridgeService.transform()` (default) | `{journal_text}` |
| `dsl_domain_recognition_compact` | `LLMDSLBridgeService.transform()` (compact mode) | `{journal_text}` |

---

## Adding a New Template

1. Create `core/prompts/templates/{template_id}.md` with `{placeholder}` syntax
2. Use `PROMPT_REGISTRY.render("template_id", placeholder=value)` in the service
3. Add a row to the catalog table above

**Naming convention:**
- Domain-specific: `{domain}_{purpose}.md` — e.g., `askesis_daily_plan.md`, `askesis_qa_response.md`
- Cross-domain service: `{service}_{purpose}.md` — e.g., `activity_feedback.md`, `journal_activity.md`
- DSL pipeline: `dsl_{purpose}.md`

---

## Placeholder Rules

Templates use Python's `str.format()` syntax: `{placeholder_name}`.

```markdown
# My Template

You are analyzing {time_period} of data.

Data: {stats_json}
```

All placeholder names must be passed as keyword arguments to `render()` or `PromptTemplate.render()`.
A `KeyError` at render time means a placeholder was not provided — fix by passing the argument.

---

## Anti-Patterns

```python
# WRONG — inline prompt in service code
prompt = f"You are a coach. Analyze these stats: {json.dumps(stats)}"

# WRONG — fallback inline when file not found (pattern deleted with registry)
try:
    template = Path("prompts/foo.md").read_text()
except FileNotFoundError:
    template = "fallback string..."

# CORRECT
prompt = PROMPT_REGISTRY.render("activity_feedback", stats_json=json.dumps(stats), ...)
```

---

## Askesis & Prompts (Current and Future)

**Current state:** Askesis's `QueryProcessor` uses `LLMService.generate_context_aware_answer()`
which builds context inline via `ResponseGenerator.build_llm_context()`. No PROMPT_REGISTRY
use yet — context building is programmatic string assembly, not a template.

**Why this will change:** As Askesis's LLM interactions mature and stabilize, they should
become proper prompt templates. This is the "major aspect of Askesis" — separating prompt
engineering from service logic so prompts can be edited without touching Python code.

**The migration path:** Each `generate_context_aware_answer()` call → one
`core/prompts/templates/askesis_*.md` file. Each method gets documented placeholders.

**Planned additions:**

| Template ID (planned) | Service | Purpose |
|----------------------|---------|---------|
| `askesis_qa_response.md` | `QueryProcessor` | System instructions for Q&A mode |
| `askesis_daily_plan.md` | `ActionRecommendationEngine` | Daily plan generation |
| `askesis_synergy_detection.md` | `UserStateAnalyzer` | Cross-domain pattern analysis |

---

## System Prompt Pattern (`OpenAIService`)

`OpenAIService.generate_completion()` accepts `system_prompt: str | None = None`.
When `None`, no system message is sent (templates are self-contained). Use it only for
role framing that doesn't belong in the template itself:

```python
await openai_service.generate_completion(
    prompt=PROMPT_REGISTRY.render("my_template", ...),
    system_prompt="You are a personal development coach.",  # Optional role framing
)
```

---

## Related Skills

- [base-ai-service](../base-ai-service/SKILL.md) — BaseAIService for LLM-powered features
- [learning-loop](../learning-loop/SKILL.md) — Feedback generation uses `activity_feedback.md`
- [user-context-intelligence](../user-context-intelligence/SKILL.md) — UserContext feeds prompts
