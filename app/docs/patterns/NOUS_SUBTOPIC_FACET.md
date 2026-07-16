# `nous_subtopic` Facet — Mechanism

The 2nd taxonomy level beneath `nous`: a graph-derived search facet + Askesis retrieval
scope on the curriculum corpus.

> **Content boundary:** this file documents the *mechanism* only. The *ontology* —
> which sub-topic slugs exist and what they mean — is proprietary SKUEL content and is
> **not** kept in this repo. It is authored in the private content vault as
> `nous_subtopic:` frontmatter and embodied in the graph. Do not paste the vocabulary
> here. See the content boundary guard: `scripts/audit_content_boundary.py`.

## How it works

- **Field:** `nous_subtopic: tuple[str, ...]` on `Ku` (`core/models/ku/ku.py`) and
  `PathStep` (`core/models/pathways/path_step.py`) — mirrors `nous` exactly:
  multi-valued, kebab-case, empty = deliberately unassigned. Authored in vault YAML
  directly under the `nous:` block as a **parallel array**: index i names the
  sub-topic that sits UNDER the nous topic at index i. Pair derivation is therefore
  positional (`UNWIND range(...)` over both arrays by index, guarded to equal-length
  arrays), never an element cross-product — a `[body, exercises]` x
  `[breath, practice-design]` entity authors breath↔body + practice-design↔exercises,
  NOT breath↔exercises.
- **Vocabulary is graph-derived, never hardcoded.** A sub-topic exists (and renders as
  a faucet option) only once ≥1 entity carries it (with a parent `nous`); deleting the
  last carrier removes it.
- **Cross-domain merge in the service layer.** Both `:Ku` and `:PathStep` author
  `nous_subtopic` independently, so a PathStep can contribute a pair no Ku carries. Each
  domain backend yields only its OWN label's pairs (`KuBackend`/`PsBackend.nous_subtopic_pairs`,
  scoped `:Ku` / `:PathStep`); `SearchRouter.nous_subtopic_map` +
  `SearchRouter.list_nous_subtopics` merge them. Aggregation lives in the service
  (SearchRouter is THE cross-domain search service), never in a single-domain backend.
  The flat list and the map share this one source, so they can't disagree — the flat
  list stays a superset of every scoped map, and the /search column renders whenever the
  map has any entry (even a PathStep-only sub-topic corpus).
- **Fail-soft:** with no authored data the vocabulary is empty, so the search `<select>`
  (`ui/search/components.py::_render_nous_subtopic_select`) and the Askesis scope
  selector (`ui/askesis/chat.py`) render nothing rather than an empty control. A failing
  domain contributes nothing rather than erroring the whole vocabulary.
- **Search filter:** `SearchRequest.nous_subtopic` → property filter (array membership)
  in `core/models/search_request.py`. The filter itself stays independent array
  membership; the gated dropdown is what keeps the offered combinations honest.
- **Dependent dropdown (/search):** sub-topics go deeper into ONE topic, so the control
  is gated — it starts disabled ("Choose a Nous first"; the flat vocabulary acts only
  as the render gate), and picking a NOUS topic narrows the options to those authored
  UNDER it, via `SearchRouter.nous_subtopic_map`. Wiring is pure HTMX: the sub-topic
  column (`_render_nous_subtopic_select`) listens for `change from:[name='nous']` and
  re-fetches `GET /search/subtopics?nous=…`, swapping its innerHTML with the scoped
  `render_nous_subtopic_inner` fragment — no Alpine window-global seeding. The NOUS
  `<select>` drops `nous_subtopic` from its results include so a topic switch re-scopes
  cleanly instead of carrying a now-orphaned sub-topic. "All Nous" resets the control
  to the disabled gate (the flat cross-topic list is never offered); a topic with no
  sub-topics yields a disabled "All Sub-topics". The Askesis scope selector is still
  flat (its Alpine-bound selector predates the dependency) — known follow-up.

## Authoring & changing the ontology

Edit `nous_subtopic:` frontmatter in the content vault, then re-sync
(`./dev vault-sync --vault content`). The faucets follow the graph. The taxonomy
reference lives with the content (vault), not here.

**See:** `docs/architecture/SEARCH_ARCHITECTURE.md`,
`docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`
