---
updated: 2026-09-02
---

# Journal Privacy — What SKUEL Stores, Who Can See It, and Our Commitment

This document covers journal entries specifically. For how SKUEL handles all other content types (tasks, goals, audio, vault files), see [How Your Content Is Used](how-your-content-is-used.md).

This document explains exactly what happens to the content you write in the SKUEL journal, who has access to it, and what SKUEL.app commits to as policy.

---

## What the journal stores

**Nothing in the database, by default.** A typed discussion is processed for that request and shown to you. When you leave the page it is gone — no copy of what you typed or of the AI's reply is kept anywhere, and an unsaved discussion creates no record at all.

An uploaded file or audio recording is different in one respect: its transcript, or its compiled output, is **written as a file** into the `je_out/` folder of your own vault. That file is the deliverable, and it stays where it was written until you delete it. Nothing about the upload enters SKUEL's database, and the vault sync never reads that folder back in.

What persists, and why:

- **A saved chat** — only when you click **Save this chat**. It stores that discussion's turns and title under your account; nothing is saved until you click.
- **The output file of an upload** — because you uploaded it. It lives in your vault's `je_out/` folder as a file for you to open in Obsidian, never in the database.
- **Vault notes you sync** — because you put them in a sync doorway folder (`knowledge/`, your periodic notes). They are stored under your account as notes, and they are private unless a note's frontmatter names an `audience:`. Mark one `private: true` and the journal companion will not read it.

A saved chat is **never used to understand you**. It is not searched, embedded, or fed into the context the journal companion or Askesis works from — the only channel into that context is the vault notes you choose to sync.

When you request an AI response, your text and a short summary of your active goals, tasks, and habits are sent to the configured AI model for that request only. The reply is shown to you and, unless you save the chat, discarded with the rest of the discussion; for an upload, the reply *is* the output file described above.

---

## Who can read your journal entries

### Through the SKUEL application

| Role | Can read your journal content? |
|------|-------------------------------|
| You | ✅ Yes — your saved chats and synced notes only |
| Other users | ❌ No — ownership is enforced at every query |
| Teachers | ❌ No — a saved chat has no sharing surface, and a synced vault note is visible to your teachers only when its frontmatter names them in `audience:` |
| SKUEL Admins | ❌ No — admin routes cover user accounts and platform statistics; no admin route reads journal content |

This is technically enforced, not just policy. A saved chat is read only through the owner-scoped conversation store, and a synced note only through `(YourAccount)-[:OWNS]->(Note)`. There is no admin route in the codebase that traverses either across users.

### At the raw database level

SKUEL's data lives in a Neo4j database. Currently, saved chats and synced notes are stored as **plaintext** in that database. Anyone with direct database access (for example, a server administrator running a raw Cypher query) can technically read every node in the database, including those.

**SKUEL's policy commitment on this point is stated below.**

---

## SKUEL.app's policy commitment

SKUEL.app commits to the following:

1. **No operator access to journal content.** SKUEL's development team and operators will not read, export, query, or otherwise access a user's saved chats or synced notes. This applies to direct database access, log inspection, or any other path.

2. **Journals are excluded from administrative statistics.** The admin dashboard shows platform-level metrics (user counts, active goals, tasks created). Journal counts and content are not included in any admin view — and this is enforced in the codebase.

3. **AI processing is request-scoped.** When you request an AI response, your journal text is transmitted to the configured AI provider's API for that request only. SKUEL does not log the content of a discussion or a note to application logs. Record identifiers and your account ID are logged for operational purposes (e.g., confirming a save succeeded), but never the text of what you wrote.

4. **AI provider data handling.** Journal content sent to the AI provider is subject to that provider's privacy policy and API terms of service. SKUEL uses provider APIs under terms that prohibit the provider from training on API-submitted data by default.

5. **No sharing with third parties.** Journal content is never sold, exported, or shared with any party other than the configured AI provider (for AI response generation, as described above).

---

## What SKUEL is working toward (technical roadmap)

The current architecture enforces journal privacy at the **application layer** — nothing is stored unless you save it, and the app will never expose what you saved to another user or to an admin. The remaining gap is at the **database layer**: raw database access by a server operator could in principle expose plaintext.

SKUEL intends to close this gap with **field-level encryption**: encrypting saved chats and synced notes before writing them to the database, using a key that lives in the server environment (not in the database itself). With this in place, a raw database dump would show ciphertext — unreadable without the application's encryption key. This makes the policy commitment technically enforced rather than relying solely on operator conduct.

Until that is implemented, the protection rests on the combination of:
- Application-layer enforcement (implemented)
- This policy commitment (this document)

---

## Summary

| Protection | Status |
|-----------|--------|
| Unsaved typed discussions leave no record | ✅ Technically enforced |
| Uploads persist only as a file in your vault's `je_out/`, never in the database | ✅ Technically enforced |
| Admin cannot read your journals via the app | ✅ Technically enforced |
| Other users cannot read your journals | ✅ Technically enforced |
| Journal counts excluded from admin analytics | ✅ Technically enforced |
| AI responses use your content for that request only | ✅ By design |
| SKUEL operators commit not to access journal content | ✅ Policy commitment (this document) |
| Journal content encrypted at rest in the database | 🔲 Planned — field-level encryption |

---

*Last updated: 2026-09-02*
