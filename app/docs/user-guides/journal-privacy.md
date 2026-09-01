---
updated: 2026-06-28
---

# Journal Privacy — What SKUEL Stores, Who Can See It, and Our Commitment

This document covers journal entries specifically. For how SKUEL handles all other content types (tasks, goals, audio, vault files), see [How Your Content Is Used](how-your-content-is-used.md).

This document explains exactly what happens to the content you write in the SKUEL journal, who has access to it, and what SKUEL.app commits to as policy.

---

## What the journal stores

When you write a journal entry and click **Add to Journal**, SKUEL saves it as a personal record under your account. It stores:

- The text you wrote (`content`)
- An optional title
- Metadata: when it was created, your account ID, the pipeline label `journal`

When you request an AI response (Respond / Scribe / Thought Partner / What Is Related), your note and a short summary of your active goals, tasks, and habits are sent to a third-party AI model to generate the response. The response is shown to you and discarded — it is not automatically saved unless you click **Add to Journal**.

---

## Who can read your journal entries

### Through the SKUEL application

| Role | Can read your journal content? |
|------|-------------------------------|
| You | ✅ Yes — your entries only |
| Other users | ❌ No — ownership is enforced at every query |
| Teachers | ❌ No — teaching tools cover exercise submissions only |
| SKUEL Admins | ❌ No — admin routes cover user accounts and platform statistics; no admin route reads journal content |

This is technically enforced, not just policy. Every query that reads a journal entry is scoped to `(YourAccount)-[:OWNS]->(Entry)`. There is no admin route in the codebase that traverses this relationship across users.

### At the raw database level

SKUEL's data lives in a Neo4j database. Currently, journal content is stored as **plaintext** in that database. Anyone with direct database access (for example, a server administrator running a raw Cypher query) can technically read every node in the database, including journal entries.

**SKUEL's policy commitment on this point is stated below.**

---

## SKUEL.app's policy commitment

SKUEL.app commits to the following:

1. **No operator access to journal content.** SKUEL's development team and operators will not read, export, query, or otherwise access a user's journal entries. This applies to direct database access, log inspection, or any other path.

2. **Journals are excluded from administrative statistics.** The admin dashboard shows platform-level metrics (user counts, active goals, tasks created). Journal entry counts and content are not included in any admin view — and this is enforced in the codebase.

3. **AI processing is request-scoped.** When you request an AI response, your journal text is transmitted to the configured AI provider's API for that request only. SKUEL does not log the content of your entries to application logs. Entry UIDs and your account ID are logged for operational purposes (e.g., confirming a save succeeded), but never the text of what you wrote.

4. **AI provider data handling.** Journal content sent to the AI provider is subject to that provider's privacy policy and API terms of service. SKUEL uses provider APIs under terms that prohibit the provider from training on API-submitted data by default.

5. **No sharing with third parties.** Journal content is never sold, exported, or shared with any party other than the configured AI provider (for AI response generation, as described above).

---

## What SKUEL is working toward (technical roadmap)

The current architecture enforces journal privacy at the **application layer** — the app will never expose your entries to another user or to an admin. The remaining gap is at the **database layer**: raw database access by a server operator could in principle expose plaintext.

SKUEL intends to close this gap with **field-level encryption**: encrypting journal content before writing it to the database, using a key that lives in the server environment (not in the database itself). With this in place, a raw database dump would show ciphertext — unreadable without the application's encryption key. This makes the policy commitment technically enforced rather than relying solely on operator conduct.

Until that is implemented, the protection rests on the combination of:
- Application-layer enforcement (implemented)
- This policy commitment (this document)

---

## Summary

| Protection | Status |
|-----------|--------|
| Admin cannot read your journals via the app | ✅ Technically enforced |
| Other users cannot read your journals | ✅ Technically enforced |
| Journal counts excluded from admin analytics | ✅ Technically enforced |
| AI responses use your content for that request only | ✅ By design |
| SKUEL operators commit not to access journal content | ✅ Policy commitment (this document) |
| Journal content encrypted at rest in the database | 🔲 Planned — field-level encryption |

---

*Last updated: 2026-06-26*
