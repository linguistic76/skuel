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
  directly under the `nous:` block.
- **Vocabulary is graph-derived, never hardcoded.** A sub-topic exists (and renders as
  a faucet option) only once ≥1 entity carries it; deleting the last carrier removes
  it. Backed by `distinct_values_raw("nous_subtopic")`
  (`adapters/persistence/neo4j/_search_raw_mixin.py`) via
  `KuService.list_nous_subtopics()`.
- **Fail-soft:** with no authored data the vocabulary is empty, so the search `<select>`
  (`ui/search/components.py::_render_nous_subtopic_select`) and the Askesis scope
  selector (`ui/askesis/chat.py`) render nothing rather than an empty control.
- **Search filter:** `SearchRequest.nous_subtopic` → property filter (array membership)
  in `core/models/search_request.py`.

## Authoring & changing the ontology

Edit `nous_subtopic:` frontmatter in the content vault, then re-sync
(`./dev vault-sync --vault content`). The faucets follow the graph. The taxonomy
reference lives with the content (vault), not here.

## Follow-up

The dependent `nous → nous_subtopic` dropdown (pick a topic → only its sub-topics
appear) is not modeled yet — tracked in issue #547. It needs a `nous → subtopics` map
built from the graph once the corpus carries the data (it now does).

**See:** `docs/architecture/SEARCH_ARCHITECTURE.md`,
`docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`
