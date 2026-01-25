# SKUEL

**Knowledge-Centric Productivity Platform**

SKUEL is a knowledge graph-based productivity system built on the principle that **knowledge is the fertile soil from which all productivity grows**. Every task, habit, goal, and decision connects to and enriches your understanding.

> **Philosophy**: All operations begin with knowledge discovery or application. Your productivity emerges from deep understanding, not shallow task management.

---

## Quick Start

### Prerequisites

- Python 3.12+
- Poetry (package manager)
- Neo4j 5.26.0+ (running separately)
- Node.js (for frontend assets)

### 1. Install Dependencies

```bash
poetry install
npm install
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Neo4j Connection (running in separate /infra)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# Application Settings
APP_HOST=0.0.0.0
APP_PORT=5001
APP_DEBUG=false

# AI Services (optional)
OPENAI_API_KEY=your_key_here
OLLAMA_URL=http://localhost:11434

# Paths
OBSIDIAN_VAULT_PATH=./vault

# Logging
LOG_LEVEL=INFO
```

### 3. Start Neo4j Infrastructure

```bash
cd ~/infra
docker compose up -d
```

### 4. Run SKUEL

Choose one of the following:

**Option A: Local Development (Recommended)**
```bash
poetry run python main.py
```

**Option B: Docker**
```bash
docker compose up -d
```

**Option C: Production**
```bash
docker compose -f docker-compose.production.yml up -d
```

### 5. Access the Application

Open your browser to: `http://localhost:5001`

---

## Architecture Overview

### The 14-Domain + 5 Systems Architecture

SKUEL organizes human experience into **14 domains** with **5 cross-cutting systems**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CROSS-CUTTING SYSTEMS (5)                    │
│   UserContext • Search • Calendar • Askesis • Messaging         │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↓ ↓
┌─────────────────────────────────────────────────────────────────┐
│                      ACTIVITY DOMAINS (6)                       │
│   Tasks • Habits • Goals • Events • Principles • Choices        │
│                     "What I DO"                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     FINANCE DOMAIN (1)                          │
│                   "What I MANAGE"                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   CURRICULUM DOMAINS (3)                        │
│   KnowledgeUnit • LearningStep • LearningPath                  │
│                    "What I LEARN"                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              CONTENT/ORGANIZATION DOMAINS (3)                   │
│          Assignments • Journals • MOC                           │
│                 "How I ORGANIZE"                                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     LIFEPATH DOMAIN (1)                         │
│              "Where I'm GOING - The Destination"                │
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
skuel00/
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
│   ├── integration/           # Integration tests (100% passing)
│   └── unit/                  # Unit tests
├── main.py                    # Application entry point
├── pyproject.toml             # Poetry dependencies
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
Components must work properly - no graceful degradation. If a dependency fails, the system fails loud and clear.

### 6. LifePath Destination
Everything flows toward your ultimate life vision. Every task, habit, and goal aligns with where you're going.

### 7. Analog-to-Digital Development
Development mirrors analog note-taking: think deeply, plan on paper, then implement in code. See `CLAUDE.md` for details.

---

## Development

### Running Tests

**Integration Tests (Recommended - 100% passing)**
```bash
poetry run pytest tests/integration/
```

**Unit Tests (Migration in progress)**
```bash
poetry run pytest tests/unit/
```

**All Tests**
```bash
poetry run pytest
```

### Code Quality

**Type Checking**
```bash
poetry run mypy core/
poetry run pyright core/
```

**Linting**
```bash
poetry run ruff check .
poetry run ruff format .
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

- **[Architecture Overview](docs/architecture/ARCHITECTURE_OVERVIEW.md)** - Complete system architecture
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

- **Imports**: Use `from result import Result, Ok, Err`
- **Error Pattern**: Use `.is_error` (not `.is_err`)
- **Logging**: Use structured logging (not `print()`)
- **Async**: Prefix async functions with `async def`
- **Types**: Use Python 3.12+ type parameter syntax

---

## Technology Stack

### Core Technologies

- **Language**: Python 3.12+
- **Web Framework**: FastHTML
- **Database**: Neo4j 5.26.0 (Graph Database)
- **Package Manager**: Poetry
- **Type Checking**: MyPy + Pyright
- **Testing**: pytest

### Key Libraries

- **Pydantic** - Data validation and settings
- **structlog** - Structured logging
- **python-result** - Result type for error handling
- **LangChain** - AI/LLM integration
- **OpenAI** - AI services
- **uvicorn** - ASGI server

### Frontend

- **MonsterUI** - UI components
- **HTMX** - Dynamic interactions
- **Tailwind CSS** - Styling

---

## Status

### Current State

- **Architecture**: Stable - 14-domain + 5-system architecture complete
- **Integration Tests**: 100% passing (434/434)
- **Unit Tests**: Migration in progress (~95% passing)
- **Documentation**: 20+ ADRs, comprehensive `/docs/`
- **Version Control**: Git integration developed but **not currently deployed**

### Recent Improvements

- Deleted 720KB of archived code (zarchives/, archive/ dirs, *.backup files)
- Expanded README from 247 bytes to comprehensive guide
- Enhanced .gitignore for future git adoption

---

## Getting Help

### Documentation Resources

1. **Quick questions**: Check `CLAUDE.md`
2. **Architecture decisions**: Review ADRs in `/docs/decisions/`
3. **Implementation patterns**: See `/docs/patterns/`
4. **System architecture**: Read `/docs/architecture/ARCHITECTURE_OVERVIEW.md`

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

**Important**: This repository contains SKUEL application code only. Neo4j infrastructure runs separately from `/infra`. Do not assume access to Docker, infrastructure configs, or system-level settings beyond this directory.

---

**Last Updated**: January 2, 2026
