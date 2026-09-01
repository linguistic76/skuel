---
updated: 2026-08-21
---

# Conversation Neo4j Persistence — Deferred Design

> "Cross-session memory is what transforms Askesis from a chat interface into a companion
> that knows you."

**Status:** RESOLVED by ADR-078 (2026-08-21 triage) — this design is historical, kept as the
source ADR-078 adapted. The **persistence half shipped** (PRs #634/#636/#638):
`adapters/persistence/neo4j/backends/conversation_backend.py`, `ConversationSession`/
`ConversationTurn` labels, `HAS_SESSION`/`HAS_TURN` edges, retention exclusion for saved
discussions. The **pedagogical half was REJECTED, not deferred** — ADR-078 deliberately
dropped `guidance_mode`, `anchor_ku_uid`, `ANCHORED_TO`, `topic_summary`, `ku_refs`,
`MENTIONS`, `MONITORS` (stored-not-understood).
⚠️ **Do not implement from this doc.** The Backend Design below specs
`ConversationBackend(UniversalNeo4jBackend[...])` — the exact shape ADR-078 §2 forbids; the
shipped backend is a thin session runner precisely to keep discussions out of the universal
search/embedding path.
**See:** `docs/decisions/ADR-078-discussion-sessions-stored-not-understood.md` (the ruling),
`docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — full pedagogical vision

---

## Why Deferred

In-memory `ConversationSession` objects (in `core/models/user/conversation.py`) are
sufficient for the current phase. Sessions survive within a single process run. Users
restart conversations naturally.

Neo4j persistence becomes valuable when:
- Askesis needs cross-session continuity ("last week we talked about X, how does that feel now?")
- Teachers need to review conversation history (requires the teacher-Askesis interface — also deferred)
- ZPDService needs to know which KUs a user has explored in conversation (richer current-zone signal)

Build this after the curriculum graph has real data and users have conversation histories worth persisting.

---

## Neo4j Schema

### Nodes

```cypher
// Conversation session — one per user interaction
(:ConversationSession {
    session_id: string,          // UUID
    user_uid: string,            // FK to User node
    started_at: datetime,
    last_activity: datetime,
    state: string,               // "active" | "completed" | "abandoned"
    guidance_mode: string,       // "SOCRATIC" | "EXPLORATORY" | "ENCOURAGING" | "DIRECT"
    anchor_ku_uid: string,       // ku_uid of the curriculum anchor (nullable for open sessions)
    topic_summary: string,       // LLM-generated 1-sentence summary of what was discussed
    turn_count: integer
})

// Individual conversation turn
(:ConversationTurn {
    turn_id: string,             // UUID
    session_id: string,          // FK to session
    role: string,                // "user" | "assistant"
    content: string,             // Message text
    timestamp: datetime,
    turn_number: integer,        // Ordinal within session
    ku_refs: list<string>        // ku_uids mentioned in this turn
})
```

### Relationships

```cypher
// Session ownership
(:User)-[:HAS_SESSION {started_at: datetime}]->(:ConversationSession)

// Turn membership (ordered)
(:ConversationSession)-[:HAS_TURN {turn_number: integer}]->(:ConversationTurn)

// Curriculum anchor
(:ConversationSession)-[:ANCHORED_TO]->(:Curriculum)  // anchor_ku_uid FK

// Mentions within a turn (for graph traversal — which KUs came up?)
(:ConversationTurn)-[:MENTIONS]->(:Entity)

// Teacher visibility (opt-in by student)
(:User)-[:MONITORS {granted_at: datetime}]->(:ConversationSession)
```

---

## Backend Design

```python
# core/services/askesis/conversation_backend.py (when implemented)
class ConversationBackend(UniversalNeo4jBackend[ConversationSession]):
    """
    Persists and retrieves conversation sessions and turns.

    Extends UniversalNeo4jBackend for standard CRUD; adds session-specific
    methods for turn management and cross-session continuity queries.
    """

    async def get_recent_sessions(
        self, user_uid: UserUID, limit: int = 5
    ) -> Result[list[ConversationSession]]: ...

    async def get_sessions_for_ku(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[list[ConversationSession]]: ...

    async def get_cross_session_summary(
        self, user_uid: UserUID, ku_uid: str
    ) -> Result[str]: ...
    # Returns LLM-generated summary of all past sessions on this KU
```

---

## Cross-Session Continuity Query

The key capability that justifies Neo4j persistence — finding what a user has discussed
about a specific KU across all sessions:

```cypher
// What has the user discussed about this KU across all sessions?
MATCH (u:User {uid: $user_uid})-[:HAS_SESSION]->(s:ConversationSession)
WHERE s.anchor_ku_uid = $ku_uid OR (s)-[:HAS_TURN]->(:ConversationTurn)-[:MENTIONS]->(ku:Curriculum {uid: $ku_uid})
MATCH (s)-[:HAS_TURN]->(t:ConversationTurn)
RETURN s.session_id, s.topic_summary, s.started_at,
       collect({role: t.role, content: t.content, turn_number: t.turn_number}) AS turns
ORDER BY s.started_at DESC
LIMIT $session_limit
```

---

## Migration Script

```cypher
// scripts/migrations/create_conversation_nodes_YYYY.cypher

// Constraints
CREATE CONSTRAINT conversation_session_id IF NOT EXISTS
FOR (s:ConversationSession) REQUIRE s.session_id IS UNIQUE;

CREATE CONSTRAINT conversation_turn_id IF NOT EXISTS
FOR (t:ConversationTurn) REQUIRE t.turn_id IS UNIQUE;

// Indexes
CREATE INDEX conversation_session_user IF NOT EXISTS
FOR (s:ConversationSession) ON (s.user_uid);

CREATE INDEX conversation_session_anchor IF NOT EXISTS
FOR (s:ConversationSession) ON (s.anchor_ku_uid);

CREATE INDEX conversation_turn_session IF NOT EXISTS
FOR (t:ConversationTurn) ON (t.session_id);
```

---

## Migration from In-Memory

When Neo4j persistence is added:

1. `ConversationContext` (in-memory dict) is replaced by `ConversationBackend.get_or_create_session()`
2. `ConversationSession.to_llm_messages()` reads from Neo4j instead of the in-memory turns list
3. Session continuity across restarts becomes automatic
4. No in-memory state is lost — the switch is transparent to callers

---

## Privacy Model

- Conversation sessions are **PRIVATE by default** — only the session owner can read them
- Student explicitly grants teacher access via a "Share session" action (same privacy model as Submissions)
- `(Teacher)-[:MONITORS]->(ConversationSession)` is only created with student consent
- Topic summaries (not full transcripts) are what teachers see by default

---

## Relationship to Other Systems

| System | How It Uses Conversation Persistence |
|--------|-------------------------------------|
| ZPDService | `get_sessions_for_ku()` adds conversation-explored KUs to current zone |
| TeacherAskesisService | `get_sessions_by_group()` shows teacher students' shared sessions |
| UserContextIntelligence | `get_cross_session_summary()` feeds Askesis context window |
