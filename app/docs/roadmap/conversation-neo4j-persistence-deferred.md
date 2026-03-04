# Conversation Neo4j Persistence — Deferred Design

> "Cross-session memory is what transforms Askesis from a chat interface into a companion
> that knows you."

**Status:** Deferred — in-memory sessions are sufficient until curriculum graph has real data
**Trigger condition:** Any user completes 3+ conversation sessions AND requests cross-session
memory; OR a teacher needs to review conversation history
**See:** `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — full pedagogical vision

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
        self, user_uid: str, limit: int = 5
    ) -> Result[list[ConversationSession]]: ...

    async def get_sessions_for_ku(
        self, user_uid: str, ku_uid: str
    ) -> Result[list[ConversationSession]]: ...

    async def get_cross_session_summary(
        self, user_uid: str, ku_uid: str
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
