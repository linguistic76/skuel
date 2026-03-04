# Teacher-Askesis Interface — Deferred Design

> "The teacher doesn't just assign exercises. They shape the pedagogical environment
> their students inhabit — including what Askesis says to them."

**Status:** Deferred — requires ZPDService + Neo4j conversation persistence first
**Trigger condition:** ZPDService is implemented AND at least one teacher has students
with persistent conversation histories
**See:** `docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — full pedagogical vision

---

## Prerequisites

This interface cannot be built until:
1. `ZPDService` exists and computes ZPD assessments (`docs/roadmap/zpd-service-deferred.md`)
2. Conversation sessions are persisted in Neo4j (`docs/roadmap/conversation-neo4j-persistence-deferred.md`)
3. The Groups domain is actively used (teachers with students in groups)

---

## What Teachers Can Do

### View (Read-Only by Default)
- **Session summaries** — 1-sentence LLM-generated topic summaries per session, not full transcripts
- **ZPD snapshot** — "This student is working with X, ready for Y, blocked by Z"
- **Momentum signal** — simple indicator (engaged / disengaged / declining)
- **Open questions** — recent `JournalInsight.open_questions` from the student's journals

Full transcript access requires the student's explicit consent (share the session).

### Adjust (Write)
- **GuidanceMode override** — set `preferred_guidance_mode` per student
  (`SOCRATIC`, `EXPLORATORY`, `ENCOURAGING`, `DIRECT`)
- **Focus KUs** — "Make sure Askesis revisits this KU with this student"
  (stored as `teacher_focus_ku_uids` on the student's graph context)
- **Annotate sessions** — flag a session as "needs follow-up" or "great progress"

### Teacher-Visible Flagging
- `(Teacher)-[:MONITORS {granted_at}]->(ConversationSession)` — session is visible to teacher
- Student grants this explicitly — same consent model as Submissions sharing
- Session list in teacher review queue shows flagged + shared sessions

---

## Training Signal

Teacher annotations on conversation sessions become training data for GuidanceMode
detection:

```
Teacher sets ENCOURAGING for a student
    ↓
Askesis uses ENCOURAGING mode with that student
    ↓
Session labeled ENCOURAGING in training data
    ↓
Future model learns: these UserContext signals → ENCOURAGING
```

Long-term: a fine-tuned model that has internalized the curriculum structure and the
students' patterns. The teacher's pedagogical judgment becomes encoded in the model.

---

## Graph Patterns

```cypher
// Teacher sets guidance mode for student
(:User {role: "teacher"})-[:GUIDES {
    guidance_mode: "ENCOURAGING",
    set_at: datetime,
    teacher_notes: "Student is discouraged after failing the last exercise"
}]->(:User {role: "student"})

// Teacher flags a session for follow-up
(:User {role: "teacher"})-[:MONITORS {
    granted_at: datetime,
    annotation: "needs_follow_up",
    teacher_note: "Left several questions open — revisit in next session"
}]->(:ConversationSession)

// Teacher sets focus KUs
(:User {role: "teacher"})-[:FOCUS_ON {set_at: datetime}]->(:Curriculum)
// Filtered to the student via the GUIDES relationship
```

---

## Service Design

```python
# core/services/askesis/teacher_interface.py (when implemented)
class TeacherAskesisService:
    """
    Teacher-facing interface to Askesis pedagogical data.

    Requires:
    - ZPDService (for ZPD snapshots)
    - ConversationBackend (for session access)
    - GroupService (for group-scoped queries)
    """

    async def get_student_zpd_snapshot(
        self, teacher_uid: str, student_uid: str
    ) -> Result[ZPDAssessment]: ...

    async def get_shared_sessions(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[ConversationSession]]: ...

    async def set_guidance_mode(
        self, teacher_uid: str, student_uid: str, mode: GuidanceMode
    ) -> Result[None]: ...

    async def add_focus_ku(
        self, teacher_uid: str, student_uid: str, ku_uid: str, note: str
    ) -> Result[None]: ...

    async def annotate_session(
        self, teacher_uid: str, session_id: str, annotation: str, note: str
    ) -> Result[None]: ...

    async def get_group_momentum(
        self, teacher_uid: str, group_uid: str
    ) -> Result[list[dict]]: ...
    # Returns [{student_uid, momentum_score, zpd_summary}] for all group members
```

---

## UI Integration

- **Teacher review queue** (`/teaching/review`) — already exists for Submission review
- **Student detail view** (`/teaching/students/{uid}`) — new; shows ZPD snapshot + session list
- **Group overview** (`/groups/{uid}/intelligence`) — new; momentum dashboard for all students

---

## Connection to Groups Domain

Exercises target groups via `FOR_GROUP`. The teacher interface extends this naturally:

```
Teacher creates Group
    ↓
Teacher adds students (MEMBER_OF)
    ↓
Teacher creates Exercise FOR_GROUP
    ↓
Students submit work → teacher reviews (existing)
    ↓
Students open Askesis sessions → teacher sees summaries (this interface)
```

Teachers see Askesis data for students in their groups only — scoped by `MEMBER_OF`.

---

## Privacy Principles

- **Default: private** — teacher cannot see any session unless student shares it
- **Opt-in per session** — student clicks "Share with teacher" on a session
- **Summary only** — shared sessions show topic summary + open questions; not full transcript
- **Full transcript** — available only if student explicitly grants ("share full conversation")
- **Annotations** — teacher notes on a session are not visible to the student
  (pedagogical notes, not feedback)

This parallels the Submissions privacy model: student owns the work, shares it intentionally.
