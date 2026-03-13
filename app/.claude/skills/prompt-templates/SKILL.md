---
name: prompt-templates
description: >
  Expert guide for SKUEL's centralized LLM prompt template registry.
  Use when adding a new LLM prompt, editing existing templates, or understanding
  how PROMPT_REGISTRY connects services to templates.
  TRIGGER when: implementing any LLM-powered feature, working on Askesis prompts,
  editing ProgressReportGenerator, JournalOutputGenerator, LLMDSLBridgeService,
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

- **File-per-service** — `core/services/report/prompts/`, `core/services/submissions/journal_prompts/`
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
    ├── dsl_domain_recognition_compact.md
    ├── askesis_guided_redirect.md
    ├── askesis_guided_out_of_scope.md
    ├── askesis_guided_assess.md
    ├── askesis_guided_probe.md
    ├── askesis_guided_scaffold.md
    ├── askesis_guided_connection.md
    ├── askesis_guided_practice.md
    ├── askesis_scaffold_entry.md
    ├── askesis_socratic_turn.md
    ├── askesis_ku_bridge.md
    └── askesis_journal_reflection.md
```

`PromptRegistry` lazy-loads on first access and caches for the process lifetime.
Missing template → `FileNotFoundError` (not `Result.fail`) — a missing template is a
programming error, not a domain failure.

---

## Template Catalog

| Template ID | Consumers | Placeholders |
|-------------|-----------|--------------|
| `activity_feedback` | `ProgressReportGenerator._build_llm_prompt()` | `{time_period}`, `{depth}`, `{stats_json}`, `{insights_section}` |
| `journal_activity` | `JournalOutputGenerator._format_activity()` | `{content}` |
| `journal_articulation` | `JournalOutputGenerator._format_articulation()` | `{content}` |
| `journal_exploration` | `JournalOutputGenerator._format_exploration()` | `{content}` |
| `dsl_domain_recognition` | `LLMDSLBridgeService.transform()` (default) | `{journal_text}` |
| `dsl_domain_recognition_compact` | `LLMDSLBridgeService.transform()` (compact mode) | `{journal_text}` |
| `askesis_guided_redirect` | `ResponseGenerator._build_direct_prompt()` | `{articles_text}`, `{resource_refs}` |
| `askesis_guided_out_of_scope` | `ResponseGenerator._build_direct_prompt()` | `{ls_title}`, `{ls_intent}` |
| `askesis_guided_assess` | `ResponseGenerator._build_socratic_prompt()` | `{concepts}` |
| `askesis_guided_probe` | `ResponseGenerator._build_socratic_prompt()` | `{concepts}` |
| `askesis_guided_scaffold` | `ResponseGenerator._build_exploratory_prompt()` | `{concepts}`, `{resource_refs}` |
| `askesis_guided_connection` | `ResponseGenerator._build_exploratory_prompt()` | `{edges_text}` |
| `askesis_guided_practice` | `ResponseGenerator._build_encouraging_prompt()` | `{practice_text}`, `{resource_refs}` |
| `askesis_scaffold_entry` | Phase 2 — session opener | `{ku_title}`, `{ku_description}`, `{user_current_zone}`, `{journal_open_questions}`, `{journal_concepts}`, `{user_momentum}`, `{guidance_mode}`, `{conversation_history}` |
| `askesis_socratic_turn` | Phase 2 — mid-conversation | `{ku_title}`, `{conversation_history}`, `{user_message}`, `{user_understanding_estimate}`, `{awaiting_response_to}` |
| `askesis_ku_bridge` | Phase 2 — ZPD traversal | `{current_ku_title}`, `{current_ku_engagement}`, `{target_ku_title}`, `{target_ku_description}`, `{bridge_connection}` |
| `askesis_journal_reflection` | Phase 2 — journal-triggered | `{user_name}`, `{journal_open_questions}`, `{journal_struggles}`, `{related_ku_title}`, `{related_ku_description}` |

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

## Askesis & Pedagogical Dialogue

Askesis is a ZPD-aware Socratic companion anchored to curriculum objects (KU, LP, Exercise).
Two template layers define its pedagogical vocabulary:

### Layer 1: Guided System Prompts (Active)

`ResponseGenerator.build_guided_system_prompt()` dispatches to 4 mode-specific builders,
each rendering templates via `PROMPT_REGISTRY.render()`. Dynamic context (article refs, KU
names, resource refs, edge text, practice items) is computed in Python and passed as
template placeholders.

| GuidanceMode | PedagogicalIntent | Template |
|-------------|-------------------|---------|
| `DIRECT` | REDIRECT_TO_CURRICULUM | `askesis_guided_redirect` |
| `DIRECT` | OUT_OF_SCOPE | `askesis_guided_out_of_scope` |
| `SOCRATIC` | ASSESS_UNDERSTANDING | `askesis_guided_assess` |
| `SOCRATIC` | PROBE_DEEPER | `askesis_guided_probe` |
| `EXPLORATORY` | SCAFFOLD | `askesis_guided_scaffold` |
| `EXPLORATORY` | SURFACE_CONNECTION | `askesis_guided_connection` |
| `ENCOURAGING` | ENCOURAGE_PRACTICE | `askesis_guided_practice` |

### Layer 2: Interaction Pattern Templates (Phase 2 — Defined, Not Yet Wired)

Four templates define future interaction patterns. These become valuable when journal
signals provide variables like `{journal_open_questions}` and `{user_momentum}`.

| Template | Interaction Pattern |
|----------|-------------------|
| `askesis_scaffold_entry` | Session opener — invite, don't lecture |
| `askesis_socratic_turn` | Mid-conversation Socratic turn |
| `askesis_ku_bridge` | Introduce adjacent KU as natural next step |
| `askesis_journal_reflection` | Respond to journal open questions |

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
