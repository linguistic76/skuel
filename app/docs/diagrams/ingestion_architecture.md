# Ingestion System Architecture Diagrams

**Last Updated:** 2026-02-06

Visual architecture diagrams for SKUEL's MD/YAML → Neo4j ingestion system.

**See:** `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md` for full context.

---

## 1. Data Flow: Markdown → Neo4j → UX

The complete pipeline from human-written content to user-facing interface.

```mermaid
flowchart TD
    A["Markdown/YAML Files<br/>(Obsidian vault)"] --> B["UnifiedIngestionService"]

    subgraph Ingestion["Ingestion Pipeline (core/services/ingestion/)"]
        B --> C["detect_format()<br/>MD vs YAML"]
        C --> D["parse_markdown() / parse_yaml()<br/>Extract frontmatter + body"]
        D --> E["detect_entity_type()<br/>14 entity types"]
        E --> F["validate_required_fields()<br/>Early fail-fast"]
        F --> G["prepare_entity_data()<br/>UID generation, normalization"]
        G --> H["validate_entity_data()<br/>Post-preparation checks"]
        H --> I["BulkIngestionEngine<br/>Batch upsert + relationships"]
    end

    I --> J[("Neo4j Graph<br/>Nodes + Edges")]

    J --> K["UniversalNeo4jBackend[T]<br/>Generic CRUD"]
    K --> L["Domain Services<br/>Tasks, Goals, KU, etc."]
    L --> M["Route Factories<br/>DomainRouteConfig"]
    M --> N["FastHTML Routes<br/>Server-rendered HTML"]
    N --> O["User Interface<br/>HTMX + Alpine.js + MonsterUI"]

    O --> P["User Action<br/>(complete task, etc.)"]
    P --> Q["Event Published<br/>(task.completed)"]
    Q --> R["Knowledge Substance<br/>Updated"]
    R --> J

    style Ingestion fill:#f0f4ff,stroke:#4a6fa5
    style J fill:#ffd700,stroke:#b8860b
```

---

## 2. Ingestion Modes Decision Flow

How the system decides which files to process based on ingestion mode.

```mermaid
flowchart TD
    A["Files in Directory"] --> B{"Ingestion Mode?"}

    B -->|"full"| C["Process ALL Files"]
    B -->|"incremental"| D["Query IngestionMetadata<br/>from Neo4j"]
    B -->|"smart"| E["Check file mtime<br/>(filesystem)"]
    B -->|"dry_run=True"| F["Validate Only<br/>(no writes)"]

    %% Full mode
    C --> G["BulkIngestionEngine<br/>Upsert all to Neo4j"]
    G --> H["Return IngestionStats"]

    %% Incremental mode
    D --> I["Compute SHA-256 Hash<br/>of file content"]
    I --> J{"Hash matches<br/>stored hash?"}
    J -->|"Yes"| K["Skip File<br/>(unchanged)"]
    J -->|"No"| L["Process File"]
    L --> M["Update IngestionMetadata<br/>(new hash + mtime)"]
    M --> N["Return IncrementalStats<br/>(with skip_efficiency)"]
    K --> N

    %% Smart mode
    E --> O{"mtime changed<br/>since last ingestion?"}
    O -->|"No"| K
    O -->|"Yes"| I

    %% Dry-run mode
    F --> P["Check entity existence<br/>in Neo4j"]
    P --> Q{"Entity exists?"}
    Q -->|"Yes"| R["Add to files_to_update"]
    Q -->|"No"| S["Add to files_to_create"]
    R --> T["Return DryRunPreview"]
    S --> T

    style K fill:#e8f5e9,stroke:#4caf50
    style L fill:#fff3e0,stroke:#ff9800
    style F fill:#e3f2fd,stroke:#2196f3
    style T fill:#e3f2fd,stroke:#2196f3
```

### Ingestion Modes Comparison

| Mode | Speed | Use Case | Return Type | Writes to DB |
|------|-------|----------|-------------|--------------|
| **Full** | Slowest | First ingestion, clean slate | `IngestionStats` | Yes |
| **Incremental** | Fast | Regular ingestion, large vaults | `IncrementalStats` | Yes (changed only) |
| **Smart** | Fastest | Frequent ingestion, optimization | `IncrementalStats` | Yes (changed only) |
| **Dry-Run** | Fast | Preview before execution | `DryRunPreview` | No |

---

## 3. WebSocket Real-Time Progress Architecture

Sequence diagram showing how real-time ingestion progress flows from backend to UI.

```mermaid
sequenceDiagram
    participant Admin as Admin User
    participant UI as Browser<br/>(Alpine.js)
    participant API as ingestion_api.py<br/>(POST endpoint)
    participant WS as WebSocket<br/>(/ws/ingest/progress/)
    participant Service as UnifiedIngestionService<br/>(batch.py)
    participant Tracker as ProgressTracker
    participant Neo4j as Neo4j Database

    Admin->>UI: Click "Ingest Directory"
    UI->>API: POST /api/ingest/directory<br/>{directory, pattern, dry_run}

    Note over API: Validate path (traversal protection)
    Note over API: Generate operation_id (UUID)

    API->>Service: ingest_directory(path, progress_callback)

    UI->>WS: Connect to /ws/ingest/progress/{operation_id}
    Note over WS: Verify admin session<br/>(close 4003 if unauthorized)
    WS-->>UI: Connection accepted

    Note over UI: Alpine.js ingestionProgress component<br/>initializes WebSocket

    loop For each file in directory
        Service->>Tracker: tracker.update(file_index, file_path)
        Tracker->>Tracker: Calculate ETA<br/>(elapsed / processed * remaining)
        Tracker->>WS: websocket_callback(progress_data)
        WS-->>UI: JSON: {current, total, percentage,<br/>current_file, eta_seconds}
        UI-->>Admin: Update progress bar + ETA
        Service->>Neo4j: Batch UPSERT (per batch_size)
    end

    Service-->>API: Return IngestionStats/IncrementalStats
    API-->>UI: HTTP Response with IngestionResultsSummary
    UI-->>Admin: Display formatted results<br/>(MonsterUI stat cards + tables)
    WS--xUI: Connection closed
```

### Progress Data Format

```json
{
  "current": 150,
  "total": 1000,
  "percentage": 15.0,
  "current_file": "/vault/docs/ku.machine-learning.md",
  "eta_seconds": 85
}
```

### Key Components

| Component | File | Role |
|-----------|------|------|
| `ProgressTracker` | `core/services/ingestion/progress_tracker.py` | Calculates progress + ETA, calls callback |
| `broadcast_progress()` | `adapters/inbound/ingestion_api.py` | Sends JSON to WebSocket connection |
| `_active_connections` | `adapters/inbound/ingestion_api.py` | Global dict mapping operation_id to WebSocket |
| `ingestionProgress` | `static/js/skuel.js` | Alpine.js component, auto-connects WebSocket |
| `ProgressIndicator` | `ui/patterns/ingestion_results.py` | Server-rendered HTML with Alpine.js bindings |

---

## 4. Ingestion History Graph Model

How ingestion operations are tracked as Neo4j nodes for audit trail.

```mermaid
graph LR
    Admin["(:User)<br/>user_admin"] -->|"triggers"| SH

    SH["(:IngestionHistory)<br/>operation_id: uuid<br/>operation_type: directory<br/>started_at: datetime<br/>completed_at: datetime<br/>status: completed<br/>source_path: /vault/docs<br/>total_files: 1000<br/>successful: 995<br/>failed: 5"]

    SH -->|"HAD_ERROR"| E1["(:IngestionError)<br/>file: /vault/bad.md<br/>error: Missing title<br/>stage: validation<br/>suggestion: Add title"]

    SH -->|"HAD_ERROR"| E2["(:IngestionError)<br/>file: /vault/broken.yaml<br/>error: Invalid YAML<br/>stage: parsing"]

    style SH fill:#fff3e0,stroke:#ff9800
    style E1 fill:#ffebee,stroke:#f44336
    style E2 fill:#ffebee,stroke:#f44336
    style Admin fill:#e8f5e9,stroke:#4caf50
```

### IngestionHistoryService API

```python
from core.services.ingestion import IngestionHistoryService

history = IngestionHistoryService(driver)

# Create entry before ingestion
op_id = await history.create_entry("directory", "user_admin", "/vault/docs")

# Update with results
await history.update_entry(op_id, "completed", stats_dict, error_dicts)

# Retrieve history (paginated)
entries = await history.get_history(limit=50, offset=0)

# Get specific entry
entry = await history.get_entry(operation_id)

# Total count (for pagination)
total = await history.get_total_count()
```

---

## 5. Domain-Integrated Ingestion Trigger Flow

How admin users trigger ingestion from domain list pages.

```mermaid
flowchart TD
    A["Admin visits /ku page"] --> B{"is_admin?"}
    B -->|"No"| C["Normal list page<br/>(no ingest button)"]
    B -->|"Yes"| D["List page with<br/>DomainIngestionTrigger button"]

    D --> E["Admin clicks<br/>'Ingest KU' button"]
    E --> F["DomainIngestionModal opens<br/>(source dir, pattern, dry-run)"]
    F --> G["Admin submits form"]

    G -->|"HTMX POST"| H["/api/ingest/domain/ku"]
    H --> I{"dry_run?"}
    I -->|"Yes"| J["Return DryRunPreviewComponent<br/>(creates, updates, skips)"]
    I -->|"No"| K["Return IngestionResultsSummary<br/>(stat cards + tables)"]

    J --> L["Results shown in modal"]
    K --> L

    style D fill:#e3f2fd,stroke:#2196f3
    style F fill:#fff3e0,stroke:#ff9800
    style J fill:#e3f2fd,stroke:#2196f3
    style K fill:#e8f5e9,stroke:#4caf50
```

### Supported Domains

| Domain | API Endpoint | Default Source |
|--------|-------------|----------------|
| KU | `/api/ingest/domain/ku` | `/home/mike/0bsidian/skuel/docs/ku` |
| LS | `/api/ingest/domain/ls` | `/home/mike/0bsidian/skuel/docs/ls` |
| LP | `/api/ingest/domain/lp` | `/home/mike/0bsidian/skuel/docs/lp` |
| Tasks | `/api/ingest/domain/tasks` | `/home/mike/0bsidian/skuel/docs/tasks` |
| Goals | `/api/ingest/domain/goals` | `/home/mike/0bsidian/skuel/docs/goals` |
| Habits | `/api/ingest/domain/habits` | `/home/mike/0bsidian/skuel/docs/habits` |
| Events | `/api/ingest/domain/events` | `/home/mike/0bsidian/skuel/docs/events` |
| Choices | `/api/ingest/domain/choices` | `/home/mike/0bsidian/skuel/docs/choices` |
| Principles | `/api/ingest/domain/principles` | `/home/mike/0bsidian/skuel/docs/principles` |

---

## Related Documentation

- **Architecture:** `/docs/architecture/CORE_SYSTEMS_ARCHITECTURE.md`
- **Implementation Guide:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`
