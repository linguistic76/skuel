# SKUEL

**Knowledge-Centric Productivity Platform**

SKUEL is a graph-powered productivity system built on the principle that **knowledge is the fertile soil from which all productivity grows**. Every task, habit, goal, and decision connects to a Neo4j knowledge graph — so your productivity emerges from deep understanding, not shallow task management.

## Repository Layout

```
skuel/
├── app/                  # Application code (Python/FastHTML)
│   ├── core/             #   Domain models, services, business logic
│   ├── adapters/         #   Routes (FastHTML) + persistence (Neo4j)
│   ├── ui/               #   Server-rendered UI components
│   ├── static/           #   Frontend assets (CSS, JS, PWA)
│   ├── docs/             #   Architecture docs, ADRs, patterns
│   └── tests/            #   Integration + unit tests
├── infrastructure/       # Docker Compose for Neo4j (runs separately)
└── .github/workflows/    # CI/CD
```

## Key Technologies

**Python 3.14** · **FastHTML** · **Neo4j** · **HTMX + Alpine.js** · **MonsterUI (Tailwind)** · **uv**

## Quick Start

```bash
cd app
uv sync                          # Install dependencies
docker compose up -d             # Start Neo4j + app
# Or: uv run python main.py     # Local dev (Neo4j must be running separately)
```

Then open **http://localhost:8000**.

## Documentation

Full setup guide, architecture overview, and development workflow: **[`app/README.md`](app/README.md)**

## License

[MIT](LICENSE)
