---
name: prompt-templates
description: >
  Expert guide for SKUEL's centralized LLM prompt template registry.
  Use when adding a new LLM prompt, editing existing templates, or understanding
  how PROMPT_REGISTRY connects services to templates.
  TRIGGER when: implementing any LLM-powered feature, working on Askesis prompts,
  editing ProgressReportGenerator, JournalOutputService, LLMDSLBridgeService,
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
- **Hardcoded system prompt bug** — the journal LLM path always sent "formats journal transcripts"

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
    ├── entry_response.md
    ├── journal_activity.md
    ├── journal_articulation.md
    ├── journal_exploration.md
    ├── dsl_domain_recognition.md
    ├── dsl_domain_recognition_compact.md
    ├── dsl_domain_recognition_system.md
    ├── prereq_edge_judge.md
    ├── entry_ku_grounding_judge.md
    ├── task_ku_grounding_judge.md
    ├── transcript_formatting.md
    ├── transcript_editing.md
    ├── transcript_editing_context.md
    ├── lifepath_vision_themes.md
    ├── askesis_stance.md
    ├── askesis_response_guidelines.md
    ├── askesis_curriculum_reference.md
    ├── askesis_tool_selection.md
    ├── askesis_guided_redirect.md
    ├── askesis_guided_direct.md
    ├── askesis_guided_out_of_scope.md
    ├── askesis_guided_assess.md
    ├── askesis_guided_probe.md
    ├── askesis_guided_scaffold.md
    ├── askesis_guided_connection.md
    ├── askesis_guided_practice.md
    ├── askesis_scaffold_entry.md
    ├── askesis_socratic_turn.md
    ├── askesis_ku_bridge.md
    ├── askesis_journal_reflection.md
    ├── {domain}_ai_*.md                # 28 — one per *AIService prompt method (tasks_ai_breakdown.md, …)
    └── ps_ai_explain_level_*.md        # 6 — explain_step's level fragments
```

`PromptRegistry` lazy-loads on first access and caches for the process lifetime.
Missing template → `FileNotFoundError` (not `Result.fail`) — a missing template is a
programming error, not a domain failure.

**Founder-local override (ADR-082 D1):** `get()` resolves an optional
`data/instructions/{template_id}.md` BEFORE the committed template — the ADR-081
authoring approach (committed floor + founder-local override) at the registry
chokepoint, for every template id. Absence is the normal state (silent miss);
blank/whitespace degrades to the committed floor; the shared containment guard
(`core/utils/instruction_files.py`) blocks traversal. Overrides are read fresh on
every access (never cached) so founder edits land without a restart. The render
contract is ENFORCED: an override whose `{placeholder}` set differs from the
committed floor's (or that isn't a valid format string) degrades to the floor
with a warning — it replaces the words, never the placeholders.

---

## Template Catalog

| Template ID | Consumers | Placeholders |
|-------------|-----------|--------------|
| `activity_feedback` | `ProgressReportGenerator._build_llm_prompt()` | `{time_period}`, `{depth}`, `{stats_json}`, `{insights_section}` |
| `entry_response` | `EntryReportService.generate_entry_response()` (ADR-069 journal responses) | `{content}` |
| `journal_activity` | `InstructionResolver` via `EnrichmentMode.ACTIVITY_TRACKING` (`LLM_SUMMARY` / `TRANSCRIBE_AND_STRUCTURE` pipelines) | `{content}` |
| `journal_articulation` | `InstructionResolver` via `EnrichmentMode.IDEA_ARTICULATION` | `{content}` |
| `journal_exploration` | `InstructionResolver` via `EnrichmentMode.CRITICAL_THINKING` | `{content}` |
| `prereq_edge_judge` | `PrereqSuggestionService._judge_batch()` (admin prereq-edge queue, batch pair classification) | `{pairs_block}` |
| `entry_ku_grounding_judge` | `KnowledgeGroundingService._judge()` via `EntryGroundingService` (entry→Ku grounding engagement filter) | `{entry_title}`, `{entry_excerpt}`, `{candidates_block}` |
| `task_ku_grounding_judge` | `KnowledgeGroundingService._judge()` via `TaskGroundingService` (task→Ku grounding application filter) | `{task_title}`, `{task_excerpt}`, `{candidates_block}` |
| `transcript_formatting` | `ContentEnrichmentService.process_transcript()` — the formatting instructions for a raw transcript (reached from the staged `process_audio`) | none |
| `transcript_editing` | `ContentEnrichmentService._build_editing_prompt()` — the editing task around those instructions: the transcript and the Markdown output format | `{instructions}`, `{context_section}`, `{raw_transcript}` |
| `transcript_editing_context` | `ContentEnrichmentService._build_editing_prompt()` — fills `transcript_editing`'s `{context_section}` when a context is gathered (stripped, then `\n\n` closes it) | `{active_goals}`, `{goal_titles}` |
| `lifepath_vision_themes` | `LifePathVisionService._extract_themes_with_llm()` — a vision statement's 3–7 themes as a JSON array (FULL tier; a provider failure or a reply with no usable theme falls back to keyword matching) | `{vision_statement}` |
| `dsl_domain_recognition` | `LLMDSLBridgeService.transform()` (default) | `{journal_text}`, `{user_context}`, `{reference_date}` |
| `dsl_domain_recognition_compact` | `LLMDSLBridgeService.transform()` (compact mode) | `{journal_text}`, `{user_context}`, `{reference_date}` |
| `dsl_domain_recognition_system` | `LLMDSLBridgeService._call_llm()` — the system prompt of both recognition prompts | none |
| `askesis_stance` | `ResponseGenerator.build_guided_system_prompt()` + `LLMService._build_context_aware_system_prompt()` — heads BOTH Askesis answer branches (ADR-082 D1/D3) | none |
| `askesis_response_guidelines` | `LLMService._build_context_aware_system_prompt()` — closes the facet/context-aware system prompt (the `===` section labels before it are code) | none |
| `askesis_curriculum_reference` | `QueryProcessor._generate_guided_answer()` — the guided user turn when the bundle carries curriculum: the curriculum as reference ("do NOT share directly"), then the learner's message | `{curriculum_text}`, `{question}` |
| `askesis_tool_selection` | `select_and_run()` (`core/services/askesis/query_tools.py`) — system prompt for the aggregation tool-selection call (`LLMService.select_tool`): match every constraint or select no tool; never guess dates | none |
| `askesis_guided_redirect` | `ResponseGenerator._build_direct_prompt()` | `{lessons_text}`, `{resource_refs}` |
| `askesis_guided_out_of_scope` | `ResponseGenerator._build_direct_prompt()` | `{ls_title}`, `{ls_intent}` |
| `askesis_guided_assess` | `ResponseGenerator._build_socratic_prompt()` | `{concepts}` |
| `askesis_guided_probe` | `ResponseGenerator._build_socratic_prompt()` | `{concepts}` |
| `askesis_guided_scaffold` | `ResponseGenerator._build_exploratory_prompt()` | `{concepts}`, `{resource_refs}` |
| `askesis_guided_connection` | `ResponseGenerator._build_exploratory_prompt()` | `{edges_text}` |
| `askesis_guided_practice` | `ResponseGenerator._build_encouraging_prompt()` | `{practice_text}`, `{resource_refs}` |
| `askesis_scaffold_entry` | Staged — no render site (PLANNED, ADR-082 D4) — session opener | `{ku_title}`, `{ku_description}`, `{user_current_zone}`, `{journal_open_questions}`, `{journal_concepts}`, `{user_momentum}`, `{guidance_mode}`, `{conversation_history}` |
| `askesis_socratic_turn` | Staged — no render site (PLANNED, ADR-082 D4) — mid-conversation | `{ku_title}`, `{conversation_history}`, `{user_message}`, `{user_understanding_estimate}`, `{awaiting_response_to}` |
| `askesis_ku_bridge` | Staged — no render site (PLANNED, ADR-082 D4; first wiring candidate) — ZPD traversal | `{current_ku_title}`, `{current_ku_engagement}`, `{target_ku_title}`, `{target_ku_description}`, `{bridge_connection}` |
| `askesis_journal_reflection` | Staged — no render site (PLANNED, ADR-082 D4; je_pro shared-entry doorway only) — journal-triggered | `{user_name}`, `{journal_open_questions}`, `{journal_struggles}`, `{related_ku_title}`, `{related_ku_description}` |
| `{domain}_ai_*` (28) | One per prompt method of the eight `*AIService` classes, rendered by `BaseAIService._generate_insight(template_id, fields=…)`, named for the method's `AIRouteSpec` (`tasks_ai_breakdown` ↔ `/api/tasks/ai/breakdown`); the two unrouted PS methods' are `ps_ai_applications`, `ps_ai_learning_sequence`. The id set is `AIPromptId` (`base_ai_service.py`) | the call's `fields` keys — most take none (their entity fields go in the `Context:` block) |
| `ps_ai_explain_level_{beginner,standard,intermediate,advanced,brief,detailed}` | `PsAIService.explain_step` — the one-line guidance sentence for each target level, filling `ps_ai_explain`'s `{guidance}` (`EXPLAIN_LEVEL_TEMPLATES`; an unknown level reads as `standard`) | none |

---

## Adding a New Template

1. Create `core/prompts/templates/{template_id}.md` with `{placeholder}` syntax
2. Use `PROMPT_REGISTRY.render("template_id", placeholder=value)` in the service
3. Add a row to the catalog table above
4. A new LLM call site also needs a row in `CENSUS` (`tests/unit/test_prompt_sources_census.py`):
   every call to an LLM port method in `core/` names where its words come from (`REGISTRY`,
   `INSTRUCTION_FILE`, `AUTHORED_CURRICULUM`, `REQUEST`, `FORWARDED`), and the test traces each
   row to its source. A word argument that is literal text alone fails there at every row.

A template's file ends in a newline. Where the rendered text sits mid-prompt (a fragment filling a
placeholder, a section followed by more), `.strip()` it so the newline doesn't land in the middle.

**Naming convention:**
- A domain AI service's prompt: its route's `AIRouteSpec` name — `{domain}_ai_{action}.md`, so a
  route and its template share one name (`tests/unit/services/test_ai_prompt_templates.py` holds
  the rule). Add the id to `AIPromptId` too; `_generate_insight` takes no other.
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

`ResponseGenerator.build_guided_system_prompt()` composes **stance + pedagogy leaf +
canon block** (ADR-082 D1): the shared `askesis_stance` fragment heads the prompt, then
one of 4 mode-specific builders renders the pedagogy leaf via `PROMPT_REGISTRY.render()`.
Dynamic context (lesson refs, KU names, resource refs, edge text, practice items) is
computed in Python and passed as template placeholders. The facet/context-aware branch
(`LLMService._build_context_aware_system_prompt`) heads with the same stance — authoring
parity across both answer branches is ADR-082 D3.

| GuidanceMode | PedagogicalIntent | Template |
|-------------|-------------------|---------|
| `DIRECT` | REDIRECT_TO_CURRICULUM | `askesis_guided_redirect` |
| `DIRECT` | OUT_OF_SCOPE | `askesis_guided_out_of_scope` |
| `SOCRATIC` | ASSESS_UNDERSTANDING | `askesis_guided_assess` |
| `SOCRATIC` | PROBE_DEEPER | `askesis_guided_probe` |
| `EXPLORATORY` | SCAFFOLD | `askesis_guided_scaffold` |
| `EXPLORATORY` | SURFACE_CONNECTION | `askesis_guided_connection` |
| `ENCOURAGING` | ENCOURAGE_PRACTICE | `askesis_guided_practice` |

### Layer 2: Interaction Pattern Templates (Staged — PLANNED, ADR-082 D4)

Four templates define future interaction patterns — registered in the bloat detector's
`PLANNED_TEMPLATES` tier (`scripts/detect_bloat.py`) as a visible completion backlog.
`askesis_ku_bridge` is the first wiring candidate (citation-as-core);
`askesis_journal_reflection` may only ever wire via the je_pro/UserEntry shared-entry
doorway (the ADR-073 wall is absolute).

| Template | Interaction Pattern |
|----------|-------------------|
| `askesis_scaffold_entry` | Session opener — invite, don't lecture |
| `askesis_socratic_turn` | Mid-conversation Socratic turn |
| `askesis_ku_bridge` | Introduce adjacent KU as natural next step |
| `askesis_journal_reflection` | Respond to journal open questions |

---

## System Prompt Pattern (`ChatCompletionPort`)

The chat-completion boundary (`core/ports/llm_protocols.py`, W1 / ADR-063) takes the system
prompt *separately* from the conversation:
`ChatCompletionPort.complete(messages, *, system_prompt: str | None = None, model=..., ...)`.
When `None`, no system message is sent (templates are self-contained). A system prompt is a
prompt too: render it from the registry like the user turn (`dsl_domain_recognition_system`) —
each adapter then places it where its SDK expects (OpenAI: a system message; Anthropic: the
`system=` parameter).

```python
result = await chat_port.complete(
    [{"role": "user", "content": PROMPT_REGISTRY.render("my_template", ...)}],
    system_prompt=PROMPT_REGISTRY.render("my_template_system"),
    model="gpt-4o-mini",
)
report_text = result.value.text  # read .text off the returned LLMCompletion
```

Consumers that take an injected chat port today: `ProgressReportGenerator`,
`ContentEnrichmentService`, and `UnifiedLLMCaller` (which routes by model prefix and exposes
`generate(prompt, *, system_prompt=...) -> Result[str]`). The vendor SDKs live below the
boundary in `adapters/external/llm/`; see ADR-063.

---

## Related Skills

- [base-ai-service](../base-ai-service/SKILL.md) — BaseAIService for LLM-powered features
- [learning-loop](../learning-loop/SKILL.md) — Feedback generation uses `activity_feedback.md`
- [user-context-intelligence](../user-context-intelligence/SKILL.md) — UserContext feeds prompts
