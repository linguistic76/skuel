---
updated: 2026-09-02
---

# How Your Content Is Used — SKUEL.app

This guide explains what happens to everything you put into SKUEL: your tasks and goals, your journal entries, your audio recordings, your vault files. It covers what stays on your device, what is stored by SKUEL, and what (if anything) leaves SKUEL to reach an external service.

---

## The short version

- Everything you create in SKUEL is **private to you by default**.
- You control what you share with teachers or peers — nothing is shared without your action.
- When you use an AI feature, the relevant content is sent to an external AI service for that request only. It is not retained by the AI service or used to train AI models.
- Your audio is transcribed by a third-party service (Deepgram). The audio is not stored by SKUEL after transcription.
- SKUEL's own team cannot read your private content through the application.

---

## What SKUEL stores

### Tasks, goals, habits, events, choices, principles

These are stored in SKUEL's database under your account. Only you can read them. They are never visible to other users, teachers, or SKUEL admins through the application.

When you request AI features that use these — for example, asking the Journal Thought Partner to connect your entry to your active goals — SKUEL sends a brief summary (up to six titles from each of Goals, Tasks, and Habits) to the AI service for that request. The full content of your tasks and goals is not transmitted; only titles.

### Journal entries

A typed journal discussion is not stored by default. It is processed for that request and shown to you; when you leave the page it is gone. Only a chat you explicitly **Save** is kept — under your account, always private, with no sharing option by design — and a saved chat is never used to build SKUEL's understanding of you. An uploaded file or recording leaves its transcript or compiled output as a file in your vault's `je_out/` folder, never in the database (see [Journal Privacy](journal-privacy.md)).

When you request an AI response (Scribe, Thought Partner, or What Is Related), your text is sent to the configured AI provider along with a short context summary of your active goals, tasks, and habits. The reply is shown to you and discarded with the discussion unless you save the chat.

**See:** [Journal Privacy](journal-privacy.md) for detail on journal-specific policy and the database-layer encryption roadmap.

### Activity reports

Activity reports are AI-generated summaries of your activity across a time period. They are stored under your account and are private by default. You choose whether to share one with a teacher, and you can annotate or revise it before sharing.

When a report is generated, your recent activity data (task counts, habit completion, goals progress — not the full text of your entries) is sent to the AI service to produce the summary.

### Vault files (Obsidian sync)

If you use the vault sync feature (`/submissions/sync`), SKUEL reads your personal vault folder and ingests selected files as entries in your account. Ingestion is **fail-closed**: only files inside allowed folders are ever read into your account — the code-defined doorway folders `periodic_notes/`, `personal_notes/`, `activity_notes/`, and `knowledge/`. Every other folder in your vault is walled off — SKUEL never reads it into the graph, never searches it, and never sends it to an AI service. The wall is on by default (it does not depend on any setting being present), and a new folder you create stays private until you deliberately add it to the allowlist.

In addition, the journal staging folders below are **always** excluded — unconditionally, regardless of your allowlist or their contents — because they hold pipeline artifacts (e.g. `je_out/` holds generated transcripts that must never sync back):

| Folder | Why it is never ingested |
|--------|------------------|
| `je_in/` | Audio staging — processed via the journals upload tool, not vault sync |
| `je_out/` | Transcript staging — text files written by batch transcription |
| `je_raw/` | Reference archive input |
| `je_pro/` | Reference archive output |

The wall works retroactively: if you narrow it — remove a folder from the allowlist, or a folder becomes disallowed — the entries that were previously synced from that folder are **removed from SKUEL on the next sync**, not just excluded going forward. Your vault file stays put (it is the source of truth), so re-allowing the folder re-ingests it.

Vault sync is inbound only: it reads your vault and creates SKUEL entries. It writes back only the task completion markers (`🆔 sk_<id>` and `[x] ✅ date`) for tasks you created from vault files.

### Audio recordings

When you upload an audio file through the journals page, it is sent to Deepgram's API for transcription. The transcript is returned to SKUEL and stored as a journal entry under your account. SKUEL does not store the original audio file after transcription.

Deepgram processes audio under its own privacy terms. SKUEL uses Deepgram's API in a way that does not permit Deepgram to retain or train on your audio.

---

## What leaves SKUEL — summary

| What you do | What is sent externally | To whom |
|-------------|------------------------|---------|
| Upload audio for transcription | Your audio file | Deepgram |
| Request a journal AI response | Your journal entry text + a short context summary (goal/task/habit titles) | Anthropic (Claude) |
| Request an activity report | Aggregate activity data (counts, completion rates — not entry text) | Anthropic (Claude) |
| Use Askesis | PathStep content + your learning context | Anthropic (Claude) |
| Vault sync | Nothing — inbound read only | — |
| All other SKUEL actions | Nothing leaves SKUEL | — |

All external AI calls use Anthropic's API under terms that prohibit training on API-submitted data by default.

---

## Who can read your content

| Who | Can read your private content? |
|-----|-------------------------------|
| You | Yes — your content only |
| Other users | No — ownership enforced at every query |
| Teachers | Only what you explicitly share with them |
| SKUEL admins | No — admin access covers user accounts and system metrics only; no admin route reads your content |
| SKUEL's development team | No — policy commitment; see below |

### SKUEL's policy commitment

SKUEL's development team and operators will not read, export, query, or otherwise access a user's private content — tasks, goals, habits, journal entries, activity reports, or vault files. This applies to direct database access, log inspection, or any other path.

Application logs record operational events (a save succeeded, a request failed) using entry identifiers and account IDs. They do not record the text of what you wrote.

---

## What SKUEL is working toward

Saved journal chats, synced vault notes, and activity reports are currently stored as plaintext in SKUEL's database. Application-layer access control prevents any route from exposing them to other users or admins — but a server operator with direct database access could technically read them.

SKUEL intends to close this gap with **field-level encryption**: encrypting sensitive content before it is written to the database, using a key that lives in the server environment. A raw database dump would then show ciphertext. This makes the privacy commitment technically enforced rather than relying solely on operator conduct.

---

*Last updated: 2026-06-27*
