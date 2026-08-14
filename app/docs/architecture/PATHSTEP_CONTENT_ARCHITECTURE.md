# PathStep Content Architecture
## How YAML Files, Neo4j Nodes, and Content Blocks Relate

*Last updated: 2026-07-02 (ADR-074 — post-persist embedding events, chunk unification)*

**The embedding split (ADR-074):** the PathStep **entity** vector is built from
frontmatter fields only (`title`, `intent`, `description`, `summary`) on every trigger
path — ingest, in-app update, backfill. Body-content semantics live in the
**ContentChunk** vectors. One recipe, all triggers.

---

## The Core Distinction: Metadata vs Body

A PathStep YAML file contains two fundamentally different kinds of information:

1. **Metadata** — structured fields that describe the entity (uid, title, tags, learning objectives, domain). These are stored directly as **properties on the Entity node** in Neo4j.
2. **Body / prose content** — the actual readable text (lessons, explanations, practice instructions). This is stored in a **separate Content node**, linked via a `HAS_CONTENT` relationship.

This separation exists because metadata is queried constantly (listing, filtering, searching), while body text is only needed when a user opens a specific PathStep to read it. Storing multi-kilobyte prose on every entity node would make graph traversal slow and expensive.

---

## A Real YAML File, Annotated

Here is a representative PathStep file, broken into its two tracks:

```yaml
---
version: 1.0
type: PathStep                          # ← tells ingestion: this is a PathStep node

# ─── TRACK 1: Entity node properties ─────────────────────────────────────────
uid: ps.mindfulness-101.intro
title: Mindfulness 101 — Two Minutes, One Breath, No Perfection
sel_category: self_awareness
learning_level: beginner
complexity: basic
domain: personal
estimated_time_minutes: 15
learning_objectives:
  - Understand what mindfulness practice actually is (and isn't)
  - Complete a two-minute breath awareness session
  - Recognize mind wandering as normal and expected
  - Practice the gentle return — the core skill of mindfulness
uses_kus:
  - ku.mindfulness.breath
  - ku.mindfulness.attention
  - ku.mindfulness.mind-wandering
  - ku.mindfulness.gentle-return
tags:
  - mindfulness
  - breath
  - beginner
quality_score: 0.90

# ─── TRACK 2: Content body (extracted before node creation) ───────────────────
content: |
  ## What Is Mindfulness?

  Mindfulness is paying attention, on purpose, to what's happening right now...
  [... thousands of words of prose ...]

---
```

The `content:` key is the dividing line. Everything else in frontmatter becomes node properties. The `content:` value is extracted and stored separately.

---

## What Neo4j Stores: The Node Graph

After ingestion, this YAML produces the following graph structure:

```
(:Entity:PathStep {
    uid: "ps.mindfulness-101.intro",
    entity_type: "path_step",
    title: "Mindfulness 101 — Two Minutes, One Breath, No Perfection",
    learning_level: "beginner",
    complexity: "basic",
    domain: "personal",
    estimated_time_minutes: 15,
    learning_objectives: ["Understand what mindfulness...", ...],
    tags: ["mindfulness", "breath", "beginner"],
    quality_score: 0.90,
    word_count: 1247,           ← calculated from content body at ingest time
    mastery_threshold: 0.7,
    current_mastery: 0.0,
    created_at: "...",
    status: "active"
})

    -[:HAS_CONTENT]->

(:Content {
    uid: "ps.mindfulness-101.intro",
    body: "## What Is Mindfulness?\n\nMindfulness is ...",
    format: "markdown",
    word_count: 1247,
    chunk_count: 5,
    updated_at: datetime()
})

    -[:HAS_CHUNK {sequence: 0}]->

(:ContentChunk {
    uid: "ps.mindfulness-101.intro:chunk:0",   ← deterministic: {parent_uid}:chunk:{index}
    chunk_type: "section",              ← ContentChunkType value (section | definition |
                                          example | exercise | code | summary | ...)
    text: "## What Is Mindfulness?\n\nMindfulness is paying attention...",
    context_window: "...",              ← text + ~100-word pre/post buffer (what gets embedded)
    start_index: 0,
    end_index: 512,
    chunking_version: "v1",
    embedding: [0.23, -0.17, ...]       ← 1024-dim vector, written later by the
                                          background worker (ChunkEmbeddingRequested,
                                          ADR-074) — null until then
})

    -[:HAS_CHUNK {sequence: 1}]->

(:ContentChunk { uid: "...:chunk:1", ... })
...
```

> **`chunk_type` is stored as the `ContentChunkType` *value* — lowercase.** Both
> writers persist `chunk.chunk_type = chunk.chunk_type.value`
> (`Neo4jContentAdapter`, `Neo4jReferenceChunkAdapter`), and every reader that
> filters on it does a bare equality test (`chunk.chunk_type IN $chunk_types`,
> `vector_search_backend.py`). Neo4j matches **zero rows** on a value no node
> carries rather than erroring, so a member NAME (`"DEFINITION"`) is a silent-zero
> bug, not a crash — this is how Askesis lost chunk retrieval for five of eight
> query intents until 2026-07-27. Retrieval code holds `ContentChunkType` members
> and passes `.value`; it never spells the string by hand.

(No metadata node: the write-only `:ContentMetadata` node — fabricated constants,
zero readers — was deleted 2026-07-02; deletion paths keep a cleanup MATCH for
stragglers. The staged metadata-aware path finder that would have consumed it
(`PsService.find_time_aware_learning_path`) was itself deleted 2026-07-06 once
the chunk semantic layer superseded the content-metadata campaign — content
analytics would return with a live metadata write-path first, not as scaffolding.)

Also created from the `uses_kus:` list:

```
(:Entity:PathStep {uid: "ps.mindfulness-101.intro"})
    -[:USES_KU]->
(:Entity:Ku {uid: "ku.mindfulness.breath"})
```

---

## The Three Layers Explained

### Layer 1: Entity Node (`:Entity:PathStep`)

**Purpose:** Fast graph traversal, search, listing, and metadata display.

**What's here:** uid, title, entity_type, status, tags, domain, complexity, learning_level, estimated_time_minutes, learning_objectives, word_count, mastery_threshold, quality_score, timestamps.

**What's NOT here:** The actual body text. The body is never stored on the Entity node — it would bloat every graph query that touches the node.

**When it's used:** `/path-steps` list page, search results, sidebar links, enrollment buttons, card views. Any query that needs to display a PathStep title or filter by domain reads only this node.

### Layer 2: Content Node (`:Content`)

**Purpose:** Store the full prose body for display when a user opens the PathStep.

**What's here:** `body` (the complete markdown text), `format` ("markdown"), `word_count`, `chunk_count`, `updated_at` (written by `store_content_with_chunks` — the one live write path).

**Relationship:** `(Entity)-[:HAS_CONTENT]->(Content)` — one-to-one. Each PathStep has at most one Content node.

**When it's used:** `/path-steps/{uid}/details` — the reading page. The route calls `ps_service.get_with_content(uid)` which fetches the Entity node, then reads the :Content body via `UniversalNeo4jBackend.get_content` (inline `content` field first, when present; a backend read failure propagates instead of rendering a body-less page), then renders the markdown.

**Key code:** `adapters/persistence/neo4j/neo4j_content_adapter.py` — the `Neo4jContentAdapter` manages Content node creation, updating, and retrieval.

### Layer 3: ContentChunk Nodes (`:ContentChunk`)

**Purpose:** RAG (Retrieval-Augmented Generation) — breaking the body into searchable segments with vector embeddings.

**What's here:** A slice of the body text (`text`) plus its grounding buffer (`context_window` — what actually gets embedded), position metadata (`start_index`, `end_index`), `chunk_type`, `chunking_version`, and the vector `embedding` (1024 dimensions, OpenAI `text-embedding-3-small` — written asynchronously by the background worker when it processes `ChunkEmbeddingRequested`, ADR-074).

**Relationship:** `(Content)-[:HAS_CHUNK {sequence: N}]->(ContentChunk)` — one-to-many. A 1,200-word PathStep might produce 4–6 chunks.

**When it's used:** Semantic/vector search. When Askesis or the search system needs to find "which PathStep talks about the gentle return technique?", it encodes the query into a vector and finds the nearest ContentChunks — then traverses back to the parent Entity.

**Key traversal for RAG:**
```cypher
MATCH (chunk:ContentChunk)<-[:HAS_CHUNK]-(content:Content)<-[:HAS_CONTENT]-(entity:Entity)
WHERE chunk.embedding IS NOT NULL
RETURN entity.uid, entity.title, chunk.text
ORDER BY vector.similarity.cosine(chunk.embedding, $query_embedding) DESC
LIMIT 5
```

(Production retrieval goes through the `contentchunk_embedding_idx` vector index via `db.index.vector.queryNodes` — see `Neo4jVectorSearchService.find_similar_chunks_by_text()`.)

---

## The Ingestion Pipeline

Both ingest doors — single-file (`ingest_file`) and batch/directory (`ingest_directory`,
the vault-sync path) — produce the same shape through one shared chunk step (ADR-074):

```
YAML/Markdown file
    │
    ▼
Parse frontmatter                    ← PyYAML splits --- blocks
    │
    ├── entity_data = all fields except 'content'
    └── content_body = value of 'content:' key (popped, never stored on the node)
    │
    ▼
Create/MERGE Entity node             ← entity_data → bulk upsert
    │
    ├── word_count = len(content_body.split())  ← written unconditionally
    │   (0 for an emptied body — `n += props` never removes omitted keys)
    └── (USES_KU relationships created for uses_kus: list)
    │
    ▼ POST-PERSIST (ADR-074)
PathStepEmbeddingRequested published  ← entity vector = frontmatter fields only
    │
    ▼ _chunk_entity_content() — the shared step, both doors (all chunks_body_content types: PathStep, Ku)
    │
    ├── non-empty body: split into chunks → Content + ContentChunk persisted
    │   → ONE ChunkEmbeddingRequested with every chunk id
    │   (FULL tier; in CORE the event_bus is None — chunks persist unembedded)
    └── EMPTY body: delete the stale :Content subtree (clear path)
    │
    ▼ (~30s later, app process, FULL tier)
EmbeddingBackgroundWorker embeds entity + chunks, stores vectors + v3 metadata
```

---

## Why This Design

**Entity node is small by design.** Graph traversal in Neo4j is very fast for node properties, but large property values slow it down. Keeping body text off the Entity node means listing 200 PathSteps is as fast as listing 20.

**Content node enables lazy loading.** The reading page (`/path-steps/{uid}/details`) is the only place that needs the prose text. All other pages (list, sidebar, library) need only the Entity node.

**ContentChunks enable semantic search without loading full bodies.** A vector index on `ContentChunk.embedding` lets Askesis find relevant content by meaning, not keyword. The chunk-level granularity also means a specific paragraph can be retrieved without loading the entire 2,000-word PathStep.

**Change detection is file-level, not body-level:** incremental/smart ingestion skips unchanged files via the `IngestionMetadata` content hash. Re-chunking is **delete-then-create** (Arc E, 2026-07-03): `store_content_with_chunks` deletes the entire outgoing chunk set and CREATEs fresh nodes — in ONE Cypher statement (single transaction), so a mid-write failure rolls the delete back and can never leave the Content node chunkless — and stale properties from earlier chunker/schema generations can never linger on a MERGE-kept node. Embedding idempotency (ADR-074 §8) is preserved by carry-over, not node reuse — a new chunk whose `context_window` matches an old chunk's `embedding_source_text` inherits that embedding, and the worker's freshness pre-check then skips it. A re-ingest never accumulates duplicates (chunk uids stay deterministic, `{parent_uid}:chunk:{index}`) and a force re-ingest of an unchanged body never destroys good chunk vectors.

---

## Current State (2026-07-02)

The live graph predates the chunk unification: the existing PathSteps were batch-ingested before ADR-074 PR 2, so they carry `content` as an entity-node property and have **no `:Content`/`:ContentChunk` subtree**. Reads tolerate both shapes (inline-prop → `:Content` fallback), so display works — but chunk retrieval has no substrate for them.

Migration (the ADR-074 verification pass):

1. Full-mode vault re-sync — every PathStep gets the `:Content` + `:ContentChunk` shape
2. `MATCH (ps:PathStep) WHERE ps.content IS NOT NULL REMOVE ps.content` — the re-sync alone cannot clear the legacy property (`n += props` never removes omitted keys)
3. `scripts/generate_embeddings_batch.py --stale` — re-embed the drifted corpus

---

## How to Write a PathStep YAML

A minimal PathStep YAML:

```yaml
---
type: PathStep
uid: ps.your-topic.001
title: "Your PathStep Title"
domain: personal          # any Domain member — e.g. tech, business, education, creative
learning_level: beginner  # beginner | intermediate | advanced | expert
complexity: basic         # basic | medium | advanced
estimated_time_minutes: 10

learning_objectives:
  - What the learner will be able to do after completing this

uses_kus:
  - ku.your-domain.concept-name   # Ku UIDs this PathStep composes

tags:
  - your-tag

content: |
  ## Section Heading

  Your prose here. This is the body text the learner reads.

  Markdown is supported: **bold**, *italic*, lists, code blocks.

  ## Another Section

  More content...

---
```

**Rules:**
- `type: PathStep` is required (not optional — ingestion rejects files without `type`)
- `uid` must start with `ps:` (UID prefix validation enforced)
- `content:` body uses YAML block scalar (`|`) to preserve newlines
- The `uses_kus:` list creates `USES_KU` relationships to existing Ku nodes
- All other frontmatter fields map directly to Entity node properties

---

## Key Files

| Purpose | Location |
|---------|----------|
| Content node Cypher (`store_content_with_chunks`, `delete_content_subtree`) | `adapters/persistence/neo4j/neo4j_content_adapter.py` |
| Shared chunk step, both doors (PathStep + Ku) | `core/services/ingestion/unified_ingestion_service.py` — `_chunk_entity_content()` |
| Post-persist embedding publish chokepoint | `core/events/embedding_publisher.py` |
| Fetch PathStep + body for detail page | `core/services/ps_service.py` — `get_with_content()` (BaseService `ContextOperationsMixin`; :Content body read via `UniversalNeo4jBackend.get_content`) |
| Semantic vector search on chunks | `adapters/persistence/neo4j/_adaptive_mixin.py` |
| Sample vault PathStep | `/home/mike/0bsidian/0vault/Ps/ps_breath-awareness-basics.md` |
