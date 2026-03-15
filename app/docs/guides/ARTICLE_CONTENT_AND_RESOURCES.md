# Article Content and Resources Guide

How SKUEL stores and serves two distinct kinds of content: **Article Content** (body text for curriculum entities) and **Resources** (curated external references).

---

## The Distinction

| | Article Content | Resource |
|---|---|---|
| **What it is** | The body text of a curriculum entity (Lesson, LS, LP) | A curated reference to external material (book, talk, film, podcast) |
| **EntityType** | Not an entity — a facet attached via `HAS_CONTENT` | `EntityType.RESOURCE` — a first-class entity |
| **Extends** | Standalone frozen dataclass (`CurriculumContent`) | `Entity` (7 resource-specific fields) |
| **Ownership** | Attached to its parent curriculum entity | `ContentScope.SHARED` — admin-created, all users read |
| **Content origin** | Written by curriculum authors (markdown) | Points to external works (URL, ISBN, author) |
| **Purpose** | RAG retrieval, reading, learning loop | Askesis recommendations, reading lists, reference |
| **Location** | `core/models/article_content/` | `core/models/resource/` |

**Key insight:** Article Content is _text you read inside SKUEL_. A Resource is _a pointer to something you read outside SKUEL_.

---

## Article Content (`core/models/article_content/`)

Article Content is the **body text facet** of curriculum entities. When a Lesson is ingested from markdown, the raw text is stored as a `CurriculumContent` node connected to the Lesson via a `HAS_CONTENT` relationship. This keeps the Lesson graph node lean (metadata only) while the full text lives separately for RAG.

### Three Models

| Model | File | Purpose |
|-------|------|---------|
| `CurriculumContent` | `content.py` | Body text storage — markdown, format, language, SHA-256 hash, auto-chunked |
| `ContentChunk` | `content_chunks.py` | Semantic segment of body text — typed (DEFINITION, EXAMPLE, CODE, etc.), with context windows for embedding |
| `ContentMetadata` | `content_metadata.py` | Derived analytics — word count, headings, keywords, complexity, readability score |

### How It Works

```
Markdown file
    ↓ (ingestion)
CurriculumContent node ←─HAS_CONTENT─ Lesson node
    ↓ (auto-chunking)
ContentChunk nodes ←─HAS_CHUNK─ CurriculumContent
    ↓ (embedding)
Vector index for RAG retrieval
```

1. **Ingestion:** Markdown is parsed into a `CurriculumContent` instance. The body is hashed (SHA-256) for integrity.
2. **Chunking:** The `ContentChunkingStrategy` splits the body into semantic chunks by headers, paragraphs, and content patterns. Each chunk is typed (`DEFINITION`, `EXAMPLE`, `CODE`, `EXERCISE`, etc.).
3. **Context preservation:** Each chunk carries `context_before` and `context_after` from adjacent chunks, so RAG retrieval gets surrounding context.
4. **Metadata:** `ContentMetadata.from_content()` extracts headings, keywords, technical terms, complexity indicators, and reading time.

### Chunk Types

```python
class ContentChunkType(Enum):
    DEFINITION   # "What is X" — definitional text
    EXPLANATION  # Expository paragraphs
    EXAMPLE      # "For example..." passages
    EXERCISE     # "Try this..." / practice prompts
    CODE         # Fenced code blocks
    SUMMARY      # Concluding/summarising text
    SECTION      # Generic section (plain text fallback)
    INTRODUCTION # Opening section
    CONCLUSION   # Closing section
```

### Key Service

`EntityChunkingService` (`core/services/entity_chunking_service.py`) orchestrates chunking and embedding for all curriculum entities.

---

## Resource (`core/models/resource/`)

A Resource is a **curated pointer to external material** — books, talks, films, music, podcasts. It is a first-class entity in the graph, not a facet of another entity.

### Model

`Resource(Entity)` adds 7 fields beyond the base Entity:

| Field | Purpose |
|-------|---------|
| `source_url` | URL to the original resource |
| `author` | Creator name |
| `publisher` | Publisher or platform |
| `publication_year` | Year published |
| `isbn` | ISBN for books |
| `media_type` | book, talk, film, music, article, podcast |
| `resource_duration_minutes` | Duration for time-based media |

### How It Differs from Curriculum

Resources are **Tier A (Raw Content)** — they carry no learning/substance fields, no body text chunking, no `HAS_CONTENT` relationship. They are admin-curated shared content that feeds Askesis recommendations and reading lists.

```
Resource node (in graph)
    ↓ (Askesis recommendation)
User sees: "Read 'Thinking, Fast and Slow' by Daniel Kahneman"
    ↓ (user follows link)
External content (outside SKUEL)
```

### Relationship to Articles

An Lesson might reference a Resource via relationships:
- `(Lesson)-[:REFERENCES]->(Resource)` — the Lesson cites or recommends the Resource
- `(Resource)-[:RELATED_TO]->(Lesson)` — topical connection

But the Resource's actual content lives _outside_ SKUEL. The Lesson's content lives _inside_ SKUEL (as `CurriculumContent`).

---

## When to Use Which

| Scenario | Use |
|----------|-----|
| Writing a teaching essay about stoic philosophy | **Lesson** with `CurriculumContent` body |
| Recommending "Meditations" by Marcus Aurelius | **Resource** with `media_type="book"` |
| Ingesting a markdown file from the vault | **Lesson** → `CurriculumContent` (auto-chunked) |
| Linking to a YouTube lecture | **Resource** with `source_url` and `media_type="talk"` |
| RAG retrieval for Askesis conversation | Searches **ContentChunk** vectors from `CurriculumContent` |
| Building a reading list for a Learning Path | Links to **Resource** entities via relationships |

---

## File Layout

```
core/models/
├── article_content/          # Body text facet (RAG layer)
│   ├── content.py            # CurriculumContent — body storage + auto-chunking
│   ├── content_chunks.py     # ContentChunk, ContentChunkType, chunking strategy
│   └── content_metadata.py   # ContentMetadata — derived analytics
├── lesson/                  # Lesson entity (curriculum leaf)
│   ├── article.py            # Lesson(Curriculum) frozen dataclass
│   └── lesson_dto.py        # Mutable DTO
└── resource/                 # Resource entity (external references)
    ├── resource.py           # Resource(Entity) frozen dataclass
    └── resource_dto.py       # Mutable DTO
```

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`, `/docs/architecture/MODEL_ARCHITECTURE.md`
