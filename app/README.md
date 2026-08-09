# SKUEL

**Knowledge-Centric Productivity Platform**

SKUEL is a knowledge graph-based productivity system built on the principle that **knowledge is the fertile soil from which all productivity grows**. Every task, habit, goal, and decision connects to and enriches your understanding.

> **Philosophy**: All operations begin with knowledge discovery or application. Your productivity emerges from deep understanding, not shallow task management.

---

## Quick Start

### Prerequisites

- Python 3.14
- uv (package manager)
- Neo4j 2026.06.0 (running separately)
- Node.js (for frontend assets)

### 1. Install Dependencies

```bash
uv sync
npm install
```

### 2. Configure Environment

Non-secret config lives in `app/.env` (gitignored). Credentials are read via `get_credential()` from one of three backends, picked by `SKUEL_CREDENTIAL_BACKEND`:

| Backend | Selector | Where credentials sit | When to pick it |
|---|---|---|---|
| **OS keychain** (recommended) | `SKUEL_CREDENTIAL_BACKEND=keyring` | libsecret / macOS Keychain / Windows Credential Locker | Desktop dev — no plaintext on disk |
| Fernet-encrypted JSON | unset | `~/.skuel/credentials.enc`, keyed by `SKUEL_MASTER_KEY` | Headless boxes that can't reach the OS keychain |
| direnv two-file (Stage 2) | unset | `~/.config/skuel/secrets.env` (mode 0600) sourced by `app/.envrc` | Fallback / CI |

The `.env.example` template lists every credential the app reads (marked `[SECRET]`) and every non-secret config key. Do not paste real credentials into `.env` — leave the `[SECRET]` lines blank there and load them into the active backend.

**First-time setup (keychain path):**

```bash
cp app/.env.example app/.env
$EDITOR app/.env                           # set SKUEL_CREDENTIAL_BACKEND=keyring + non-secret config
uv run python -m core.config               # interactive: writes credentials into the keychain
```

**Migrating an older `.env` that still has credentials in it:**

```bash
# Path A: move credentials out of the worktree into ~/.config/skuel/secrets.env (Stage 2)
uv run python scripts/migrate_secrets_to_homedir.py

# Path B: move credentials from secrets.env (or env) into the OS keychain (Stage 3)
uv run python scripts/migrate_secrets_to_keychain.py
```

Both scripts are idempotent. The Stage 3 path is what you want unless you're on a box without a graphical session.

**Docker note:** Docker Compose interpolates `${VAR}` directly from a `.env`-shaped file, bypassing `get_credential()`. The two keys it needs for the Neo4j services (`NEO4J_AUTH`, `NEO4J_PASSWORD`) are kept in `~/.config/skuel/secrets.env` even after Stage 3. To run docker-compose with keychain-only credentials, use `./scripts/dev/with-secrets docker compose up`.

**Missing-credential behavior:** every credential the active intelligence tier needs is required at boot, not request time. Anything missing fails the bootstrap with a clear error (commit `fed4287f`). If the app starts, the credentials it needs are present.

See `docs/roadmap/done/secrets-out-of-worktree.md` for the full design — three stages, what each shipped, and the table of where each key actually lives today.

### 3. Start Neo4j Infrastructure

The primary workflow uses `app/docker-compose.yml`, which includes both the app and Neo4j:

```bash
docker compose up -d
```

Alternatively, start Neo4j only (for local development without Docker for the app):

```bash
cd ~/skuel/infrastructure
docker compose up -d
```

### 4. Run SKUEL

Choose one of the following:

**Option A: Local Development (Recommended)**
```bash
uv run python main.py
```

**Option B: Docker**
```bash
docker compose up -d                          # Neo4j + App
docker compose --profile monitoring up -d     # + Prometheus + Grafana
```

**Option C: Production**
```bash
docker compose -f docker-compose.production.yml up -d
```

### 5. Access the Application

Open your browser to: `http://localhost:8000`

---

## Architecture Overview

### 20 Entity Types, 7 Subsystems, 3 Layers

SKUEL organizes human experience into **20 entity types**, grouped into **7 subsystems** (Model A — Ku, Curriculum Domains, Activity Domains, Learning Loop, User, Groups, Askesis) and traced through **3 layers** (Model B — Curriculum → Action → Feedback). Five cross-cutting infrastructure systems (UserContext, Search, Calendar, Askesis, Messaging) span them. See [ADR-055](docs/decisions/ADR-055-architectural-lenses.md), [`SEVEN_SUBSYSTEMS.md`](docs/architecture/SEVEN_SUBSYSTEMS.md), and [`THREE_LAYER_LENS.md`](docs/architecture/THREE_LAYER_LENS.md).

```
┌─────────────────────────────────────────────────────────────────┐
│                    CROSS-CUTTING SYSTEMS (5)                    │
│   UserContext • Search • Calendar • Askesis • Messaging         │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│  ACTIVITY (6)          Tasks • Goals • Habits • Events           │
│                        Choices • Principles                     │
│  FINANCE               Expenses & budgets (admin-only)          │
│  CURRICULUM            Ku • PS • LP • Exercise                   │
│  CURATED CONTENT       Resource (books, talks, films)           │
│  CONTENT PROCESSING    Submission • Journal • ActivityReport    │
│                        EntryReport                         │
│  ORGANIZATION          Groups • MOC (emergent)                  │
│  DESTINATION           LifePath — "Everything flows here"       │
└─────────────────────────────────────────────────────────────────┘
```

### System Architecture Layers

```
External World (HTTP/Files)
        ↓
┌─────────────────────────────────────────────────────────────┐
│                    INBOUND LAYER                            │
│  Routes (FastHTML) → Pydantic Validation → @boundary_handler│
│  Location: /adapters/inbound/                               │
│  Pattern: Factory → API + Intelligence + UI                 │
└─────────────────────────────────────────────────────────────┘
        ↓ Services Container
┌─────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                            │
│  Business Logic with Protocol Dependencies                  │
│  Location: /core/services/                                  │
│  Returns: Result[T] for all operations                      │
└─────────────────────────────────────────────────────────────┘
        ↓ Protocol Interfaces
┌─────────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                             │
│  Pure Domain Models (Frozen Dataclasses)                    │
│  Location: /core/models/                                    │
│  Pattern: Three-Tier (Pydantic → DTO → Domain)             │
└─────────────────────────────────────────────────────────────┘
        ↓ Backend Protocols
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                        │
│  Universal Backends with Protocol Implementation            │
│  Location: /adapters/persistence/                           │
│  Storage: Neo4j Graph Database                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
skuel/app/
├── core/                      # Domain logic & services
│   ├── models/                # Domain models (frozen dataclasses)
│   ├── services/              # Business logic (protocol-based)
│   └── utils/                 # Shared utilities
├── adapters/                  # External interfaces
│   ├── inbound/               # Routes (FastHTML)
│   └── persistence/           # Database backends (Neo4j)
├── static/                    # Frontend assets (CSS, JS)
├── templates/                 # HTML templates
├── docs/                      # Documentation (PRIMARY)
│   ├── decisions/             # Architecture Decision Records (ADRs)
│   ├── patterns/              # Implementation patterns
│   ├── architecture/          # System architecture
│   └── reference/             # Templates & references
├── tests/                     # Test suite
│   ├── integration/           # Integration tests
│   └── unit/                  # Unit tests
├── main.py                    # Application entry point
├── pyproject.toml             # uv dependencies
└── CLAUDE.md                  # Quick reference guide
```

---

## Core Principles

### 1. Knowledge-First Design
All operations begin with knowledge discovery or application. Tasks emerge from understanding, not arbitrary lists.

### 2. One Path Forward
Single, clear way to accomplish each task. No backward compatibility burden. Deprecated code is archived or deleted, never maintained.

### 3. Protocol-Based Dependency Injection
All services use Python Protocol interfaces for maximum flexibility and testability.

### 4. Three-Tier Type System
- **Pydantic** at system boundaries (HTTP, files)
- **DTOs** for data transfer between layers
- **Frozen dataclasses** for domain models (immutable core)

### 5. Fail-Fast Philosophy
Required infrastructure (Neo4j) must work — the system fails loud and clear if core dependencies are unavailable. Optional AI services (OpenAI, embeddings) degrade gracefully: the app runs without them, falling back to keyword search and skipping LLM features.

### 6. LifePath Destination
Everything flows toward your ultimate life vision. Every task, habit, and goal aligns with where you're going.

### 7. Analog-to-Digital Development
Development mirrors analog note-taking: think deeply, plan on paper, then implement in code. See `CLAUDE.md` for details.

---

## Development

### Running Tests

**Integration Tests**
```bash
uv run pytest tests/integration/
```

**Unit Tests**
```bash
uv run pytest tests/unit/
```

**All Tests**
```bash
uv run pytest
```

### Code Quality

**Type Checking**
```bash
uv run mypy core/
uv run pyright core/
```

**Linting**
```bash
uv run ruff check .
uv run ruff format .
```

### Development Workflow

1. **Read documentation first**: Check `/docs/` for patterns and ADRs
2. **Follow file naming**: File names must reflect function (no random/whimsical names)
3. **Use local docs**: Curated docs in `/docs/` before external sources
4. **Write tests**: Integration tests required for all new features
5. **Document decisions**: Create ADR for significant architectural choices

---

## Documentation

### Primary Documentation: `/docs/`

- **[Architecture](docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)** - Entity Type Architecture and system design
- **[Architecture Decision Records (ADRs)](docs/decisions/)** - 20+ documented decisions
- **[CLAUDE.md](CLAUDE.md)** - Quick reference for AI assistants and developers
- **[TESTING.md](docs/TESTING.md)** - Test strategy and patterns

### Key ADRs

| ADR | Topic | Category |
|-----|-------|----------|
| 001 | Unified User Context Single Query | Query Architecture |
| 013 | KU UID Flat Identity | Pattern/Practice |
| 014 | Unified Content Ingestion | Pattern/Practice |
| 015 | MEGA-QUERY Rich Queries Completion | Query Architecture |
| 016 | Context Builder Decomposition | Pattern/Practice |
| 018 | User Roles Four-Tier System | Pattern/Practice |
| 020 | FastHTML Route Registration Pattern | Pattern/Practice |

**See**: `/docs/decisions/` for all ADRs

### Documentation Hierarchy

1. **`/docs/`** - Primary source of truth (in-project)
2. **`CLAUDE.md`** - Quick reference with pointers to detailed docs
3. **`/home/mike/0bsidian/skuel/docs/`** - Secondary (Obsidian vault for prose)

---

## Contributing

### Before You Start

1. **Read the philosophy**: Understand the analog-to-digital model in `CLAUDE.md`
2. **Check existing patterns**: Review `/docs/patterns/` for established conventions
3. **Review ADRs**: See what architectural decisions have already been made

### Development Guidelines

1. **File Naming Convention**: Files must have descriptive names reflecting their purpose
2. **No Archive Files**: Delete old code completely - no `.backup`, `.old`, or `archive/` directories
3. **Error Handling**: Use `Result[T]` pattern - all service methods return `Result`
4. **Async Consistency**: All database operations must be async
5. **Type Safety**: Use MyPy/Pyright - types are required, not optional
6. **Documentation**: Update both `CLAUDE.md` summary AND detailed docs in `/docs/`

### Creating New Features

1. **Plan First**: For non-trivial features, create an ADR first
2. **Follow Factory Pattern**: Routes use factory pattern (see existing domains)
3. **Protocol-Based**: Define Protocol interface before implementation
4. **Write Integration Tests**: 100% of new features need integration tests
5. **Update Documentation**: Add to relevant `/docs/` files

### Code Style

- **Imports**: Use `from core.utils.result_simplified import Result`
- **Error Pattern**: Use `.is_error` (not `.is_err`)
- **Logging**: Use structured logging (not `print()`)
- **Async**: Prefix async functions with `async def`
- **Types**: Use Python 3.12+ type parameter syntax

---

## Technology Stack

### Core Technologies

- **Language**: Python 3.14
- **Web Framework**: FastHTML
- **Database**: Neo4j 2026.06.0 (Graph Database)
- **Package Manager**: uv
- **Type Checking**: MyPy + Pyright
- **Testing**: pytest

### Key Libraries

- **Pydantic** - Data validation and settings
- **structlog** - Structured logging
- **result_simplified** - Custom `Result[T]` type for error handling (`core/utils/result_simplified.py`)
- **OpenAI** / **Anthropic** - LLM + embedding provider SDKs, used directly behind
  `ChatCompletionPort` / `EmbeddingClientOperations` (ADR-063) — no orchestration framework
- **uvicorn** - ASGI server

### Frontend

- **MonsterUI** - UI components
- **HTMX** - Dynamic interactions
- **Tailwind CSS** - Styling

---

## Status

### Current State

- **Architecture**: Stable - entity type + 5-system architecture complete
- **Tests**: Unit + integration suites green in CI (see [TESTING.md](TESTING.md))
- **Documentation**: 20+ ADRs, comprehensive `/docs/`
- **Version Control**: Git integration developed but **not currently deployed**

### Recent Improvements

- Deleted 720KB of archived code (zarchives/, archive/ dirs, *.backup files)
- Expanded README from 247 bytes to comprehensive guide
- Enhanced .gitignore for future git adoption

---

## Demo & Examples

### Mindfulness 101 Demo

Try SKUEL with a complete curriculum bundle:

```bash
# 1. Complete database reset
uv run python scripts/clear_neo4j.py reset
# Type: DELETE EVERYTHING

# 2. Load curriculum bundle
uv run python scripts/fresh_start_mindfulness.py
# Type: FRESH START

# 3. Explore in Neo4j Browser
# Open: http://localhost:7474
```

This demo creates 6 curriculum entities (3 KUs, 2 Path Steps, 1 Learning Path) to explore SKUEL's knowledge-centric approach.

**For complete demo documentation**, see `/docs/examples/mindfulness-101-demo.md`

---

## Getting Help

### Documentation Resources

1. **Quick questions**: Check `CLAUDE.md`
2. **Architecture decisions**: Review ADRs in `/docs/decisions/`
3. **Implementation patterns**: See `/docs/patterns/`
4. **System architecture**: Read `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md`

### External Library Docs

Always check local docs first:
- **FastHTML**: `/docs/fasthtml-llms.txt` (10K+ lines)
- **Neo4j**: `/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md`
- **Pydantic**: `/docs/patterns/three_tier_type_system.md`

---

## License

**Proprietary** - This is personal productivity software. Contact the author for licensing inquiries.

---

## Project Scope

**Important**: This repository contains SKUEL application code only. Neo4j infrastructure runs separately in `~/skuel/infrastructure`. Do not assume access to Docker, infrastructure configs, or system-level settings beyond this directory.

---

**Last Updated**: March 5, 2026
