# Adapter Organization

## Directory Structure

```
adapters/
├── inbound/          # HTTP routes and API endpoints (driving adapters)
│   ├── *_routes.py   # FastHTML route handlers
│   └── ...
│
├── outbound/         # External service adapters (driven adapters)
│   └── in_memory_conversation_repo.py
│
├── persistence/      # Database and storage adapters (driven adapters)
│   ├── neo4j/       # Neo4j specific implementations
│   ├── neo4j_adapter.py
│   ├── knowledge_graph_adapter.py
│   ├── relationships_adapter.py
│   └── base_adapter.py
│
└── *_adapters.py    # Data transformation adapters (stay at root)
    ├── askesis_adapters.py      # Transforms API requests for askesis service
    ├── search_adapters.py       # Transforms search requests
    ├── events_adapters.py       # Event bus adapter
    ├── journals_adapters.py     # Journal data transformations
    ├── tasks_adapters.py        # Task data transformations
    └── transcriptions_adapters.py # Audio transcription handling
```

## Adapter Types

### 1. Inbound Adapters (Driving)
Located in `/adapters/inbound/`
- Handle HTTP requests
- Transform HTTP data to domain models
- Call application services

### 2. Persistence Adapters (Driven)
Located in `/adapters/persistence/`
- Implement repository ports
- Handle database operations
- Manage data persistence

### 3. External Service Adapters (Driven)
Located in `/adapters/outbound/`
- Connect to external services
- Handle external API calls
- Manage external integrations

### 4. Data Transformation Adapters
Located in `/adapters/` (root)
- Transform between API models and domain models
- Handle data conversion logic
- Bridge between layers

## Principles

1. **Depend on Ports**: Adapters implement interfaces from `/ports`
2. **No Business Logic**: Adapters only handle technical concerns
3. **Clear Responsibilities**: Each adapter has a single, clear purpose
4. **Testability**: Adapters can be mocked/stubbed for testing
