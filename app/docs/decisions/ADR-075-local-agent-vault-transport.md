---
title: "ADR-075: Stage-2 LocalAgentVaultAdapter — Hosted Vault Sync Transport"
updated: 2026-07-06
status: accepted
category: decisions
tags: [adr, decisions, vault, vault-bridge, local-agent, security, websocket, ed25519]
related: [ADR-044, ADR-070, ADR-073]
related_skills: [security]
---

# ADR-075: Stage-2 LocalAgentVaultAdapter — Hosted Vault Sync Transport

**Status:** Accepted — implemented (B2 server enrollment + channel, B3 user-side agent, B4 adapter + reconciler bridge + `VAULT_TRANSPORT` toggle; see *PR Plan* appendix)

**Date:** 2026-07-05

**Decision Type:** ⬜ Pattern/Practice  ⬜ Infrastructure  ✅ Architecture

**Related ADRs:**
- Builds out: ADR-070 Decision 6 (security north star) + Decision 5 (`VaultBridgePort` drop-in guarantee)
- Depends on: ADR-044 (hexagonal boundary), ADR-070 Decisions 7–9 (descriptor-by-path ownership, code-defined allowlist, human-initiated sync), ADR-073 (vault is the only memory channel)
- Context: the 2026-07-05 vault security arc, PRs #521–#527 (per-user roots, owner-scoped deletion, consent-before-read, threshold valve, per-root lock + sanitized errors, visible privacy wall, dry-run preview)

---

## Context

ADR-070 Decision 6 sketched the Stage-2 security model as a north star and explicitly did NOT
implement it: "the local-agent security model (Stage 2) is NOT implemented now — Stage 1 is
local-only; cloud deployment cannot proceed without completing Stage 2."

Stage 1 is now hardened and complete. The 2026-07-05 security arc (#521–#527) made personal
vault roots per-user, owner-scoped deletion reconciliation, consent gates the first READ,
added the mass-deletion threshold valve, the per-root sync lock, vault-relative error
sanitization, the visible privacy wall, and the dry-run preview. Every one of those
invariants was designed transport-agnostically — this ADR is where that pays off.

What remains before cloud deployment (Neo4j infrastructure Stage 2/3: Droplet → AuraDB) is
the transport itself: today `FilesystemVaultAdapter` reads the vault off the server's local
disk, and `ingest_directory` walks the server filesystem via `collect_files`. When the app
runs on a Droplet and the vault lives on the user's laptop, neither works. ADR-070 named the
successor (`LocalAgentVaultAdapter`, "encrypted outbound-only channel") but left every
concrete question open: what the channel is, how devices authenticate, what messages cross
the wire, and — the real architectural work — how a filesystem-walking ingestion engine
ingests a vault it cannot walk.

This ADR turns the north star into a buildable spec: eight decisions and a 3-PR plan
(B2 server enrollment + channel, B3 user-side agent, B4 adapter + reconciler bridge).

---

## Decision

### Decision 1 — Topology honesty: the server is the counterparty, not a relay

ADR-070 Decision 6 said "cloud stores and routes ciphertext only," borrowing Syncthing's
relay model. **That sentence describes a RELAY topology, and SKUEL's Stage-2/3 deployment is
not one.** In Syncthing, the relay is a dumb intermediary between two peers who share keys;
it genuinely never sees plaintext. In SKUEL, the counterparty at the other end of the channel
IS the SKUEL app server — and it MUST read note plaintext, because its entire job is to
ingest that content into Neo4j (parse frontmatter, extract tasks, build entities, embed).
End-to-end encryption *past* the app server is a contradiction in terms: the app is the
endpoint.

**Ruling:** channel security = **TLS + per-device authentication, end-to-end from agent to
app server** (Decisions 2–3). The "ciphertext-only" property from ADR-070 Decision 6 is
re-scoped: it applies to any **separate dumb relay** ever inserted between agent and app
(e.g. a NAT-traversal hop). The message envelope (Decision 3) is designed so that inserting
such a relay later requires no protocol change — the signed handshake authenticates the app
server's session regardless of intermediaries, and payloads could be wrapped in a second
encryption layer keyed past the relay. **We design for the relay; we do not build it**
(explicitly deferred, Decision 7).

**What the server can and cannot see — stated plainly:**

| The server CAN see | The server can NEVER see |
|---|---|
| File contents of ALLOWED folders only (the doorway wall, ADR-070 Decision 8) | Anything outside the wall — the agent enforces the allowlist on ITS side (Decision 5), so walled content **never leaves the device**; the server does not receive-and-discard it, it never receives it |
| Vault-RELATIVE paths of allowed files (`periodic_notes/2026-07-05.md`) | The vault's absolute path on the user's machine (never transmitted — carried forward from ADR-070 Decision 6 verbatim) |
| Content hashes, sizes, mtimes of allowed files (sync metadata) | The `je_*` journal staging folders (ADR-073 floor, beneath the allowlist, enforced agent-side too) |
| The agent's self-reported allowed-folder list (`describe_wall`, keeps the #526 privacy-wall UI honest) | Device private keys (never leave the device, Decision 2) |

This is the same privacy budget the graph already has: SKUEL ingests allowed-folder content
into Neo4j today. The transport adds zero new server-side visibility — it only moves where
the wall is enforced first (device-side, which is strictly stronger).

---

### Decision 2 — Device identity: agent-side Ed25519 keypair; graph-native enrollment

**Per-device Ed25519 keypair, generated on the agent, private key never leaves the device.**
Ed25519: small keys, fast signatures, no parameter footguns, first-class in Python's
`cryptography` package — the same choice Syncthing/SSH converged on for device identity.

**Private-key storage: a file at `~/.config/skuel-agent/device.key`, mode `0600` (directory
`0700`).** Chosen over the OS keyring, for reasons that compound:

1. **The keyring is not reliably present.** Headless boxes, WSL, containers, and SSH sessions
   lack a desktop secret service; `python-keyring`'s fallback backends vary per-OS in quality
   and some are plaintext files anyway. The agent must run anywhere Obsidian's vault lives.
2. **`0600` file is the SSH threat model** — identical to `~/.ssh/id_ed25519`, universally
   understood, auditable with `ls -l`, backed up with dotfiles. If a local attacker can read
   the user's `0600` files, they already own the vault itself; the key adds nothing.
3. **One fewer dependency** on an agent whose dependency surface must stay minimal (B3).

The agent refuses to start if the key file's permissions are broader than `0600` (same
posture as OpenSSH).

**Enrollment — pairing-code flow:**

1. User, in an **authenticated SKUEL session**, opens Settings → Devices and clicks
   "Pair a device." Server generates a short-lived one-time pairing code (8 chars, base32,
   **10-minute TTL, single-use**), stores it **hashed** (same discipline as session tokens —
   see security posture) with its expiry, and shows it once.
2. User runs `skuel-vault-agent enroll`, pastes the code. The agent generates its keypair
   (if absent) and submits `POST /api/devices/enroll` over HTTPS with
   `{code, device_pubkey, device_name}`. The code IS the authentication for this one call;
   the route is rate-limited (two-axis throttle, existing infra).
3. Server verifies the code (hash match, unexpired, unredeemed), consumes it, and binds the
   device to the user **graph-native**:

```cypher
MATCH (u:User {uid: $user_uid})
CREATE (u)-[:HAS_DEVICE]->(d:Device {
    uid: $device_uid,          // device_<8 random>
    pubkey: $pubkey,           // base64url Ed25519 public key
    name: $device_name,        // user-chosen label ("mike-laptop")
    enrolled_at: datetime(),
    revoked_at: null,
    last_seen_at: null
})
```

**`Device` is NOT an EntityType.** It is auth infrastructure — like sessions and unlike the
25 domain entities — so it takes no `:Entity` multi-label, no DTO, no DomainConfig. It lives
where auth data lives: in the graph, behind `UserService` (graph-native authentication
principle). `HAS_DEVICE` goes into `RelationshipName` (SKUEL013).

**Revocation:** Settings → Devices lists the user's devices (name, enrolled_at,
last_seen_at). "Revoke" stamps `revoked_at = datetime()`. The handshake (Decision 3) loads
only devices with `revoked_at IS NULL`; a revoked device fails the handshake and any live
session for it is closed server-side at revocation time. Rows are stamped, not deleted — the
device list doubles as an audit surface.

---

### Decision 3 — Session + message protocol: outbound-only WebSocket, challenge-signature handshake, JSON-RPC-ish envelope

**Transport: a single outbound WebSocket from agent to server** at `WS /ws/agent`, reusing
the existing starlette WS infrastructure (`adapters/inbound/ingestion_api.py` already runs
`WS /ws/ingest/progress/{operation_id}` on the same stack). The user's machine **never opens
a port**; the agent dials out over 443 like any browser tab, which survives NAT, home
routers, and corporate firewalls. Note the **role inversion**: the WS *connection* is
agent→server (outbound-only), but once established the *RPC caller* is the server — the
reconciler drives sync (human-initiated, ADR-070 Decision 9) and the agent is the responder.

**Handshake (challenge–response, replay-proof):**

```jsonc
// 1. server → agent, immediately on WS accept:
{"type": "challenge", "nonce": "kQ9f2c…-b64url-32-bytes", "protocol": 1}

// 2. agent → server — signature is Ed25519 over the byte string
//    "skuel-vault-agent-v1" || nonce  (domain-separation prefix prevents
//    cross-protocol signature reuse):
{"type": "auth",
 "device_pubkey": "MCowBQYDK2VwAyEA…-b64url",
 "signature": "hs7Kj…-b64url",
 "agent_version": "0.1.0"}

// 3. server → agent — server looked the pubkey up among enrolled,
//    non-revoked Device nodes, verified the signature, and bound a
//    short-lived session to THIS connection (no bearer token exists
//    outside it; connection closed = session gone):
{"type": "session", "ok": true, "user_uid": "user_mike"}

// 3b. failure (unknown pubkey, bad signature, or revoked_at set):
{"type": "session", "ok": false, "error": "device_not_enrolled"}   // then close
```

The session lives exactly as long as the connection — nothing to steal, nothing to expire,
nothing to store. Verification also stamps `Device.last_seen_at`. The server keeps a
per-user channel registry (one live channel per user in v1; a second connection for the same
user supersedes the first); the reconciler resolves the channel at sync time, and **no
connected agent = sync fails fast** with a clear "agent not connected" error — consistent
with human-initiated sync: you start your agent, then you click "Update from my vault."

**Envelope: JSON-RPC-ish request/response frames** carrying the `VaultBridgePort`
operations. Every request has `id`, `op`, `params`; every response echoes `id` with
`ok` + `result` or `ok: false` + `error {code, message}`. **ALL paths on the wire are
vault-RELATIVE.** The agent resolves them against its local root with exactly the
containment guard `FilesystemVaultAdapter._resolve` uses today (resolve, then
`is_relative_to(root)` — `..` and symlink escapes rejected); the server never learns the
root, so it *cannot* construct an absolute path even in error messages (#525 sanitization
becomes structural).

**The four operations, one wire example each:**

`describe_wall` — the agent reports its allowed folders so the server UI (#526 "What SKUEL
can see" panel, the consent form) stays honest about what a sync can actually reach:

```jsonc
→ {"id": 41, "op": "describe_wall", "params": {}}
← {"id": 41, "ok": true, "result": {
     "allowed_folders": ["activity_notes", "knowledge", "periodic_notes", "personal_notes"],
     "agent_version": "0.1.0"}}
```

`list_changed_since` — sync metadata for every allowed file. `since_state` is an opaque
cursor; `null` means full listing. **v1 always sends `null`**: deletion reconciliation needs
the full-presence listing (absence = deletion candidate, Decision 4), so a delta cursor
buys nothing yet. The parameter exists so a future delta-plus-tombstones optimization is a
protocol no-op:

```jsonc
→ {"id": 42, "op": "list_changed_since", "params": {"since_state": null}}
← {"id": 42, "ok": true, "result": {
     "state": "st_a7e2c19d",
     "files": [
       {"relative_path": "periodic_notes/2026-07-05.md",
        "content_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "mtime": "2026-07-05T09:14:03Z", "size": 1832},
       {"relative_path": "knowledge/spaced-repetition.md",
        "content_hash": "sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
        "mtime": "2026-07-01T18:40:11Z", "size": 4102}
     ]}}
```

`read_note` — fetch one file's content (only issued for hash-mismatched files, Decision 4):

```jsonc
→ {"id": 43, "op": "read_note", "params": {"relative_path": "periodic_notes/2026-07-05.md"}}
← {"id": 43, "ok": true, "result": {
     "content": "---\ntags: [daily]\n---\n\n- [ ] review ADR draft 🆔 sk_x1c9q2\n…",
     "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"}}
```

`write_task_updates` — the outbound half of the round-trip, carrying the same
`TaskLineUpdate` shapes and the same `expected_sha256` stale-read guard the port already
defines; the agent applies them with the same atomic temp-file + `rename()` mechanics as
`FilesystemVaultAdapter`. The reply carries `updates_applied` — one bool per update, in the
order received (protocol v2): `success` says the file was written, not that a given update
found its line, and the server gates per-update state (persisting a minted 🆔) on the
per-update answer:

```jsonc
→ {"id": 44, "op": "write_task_updates", "params": {
     "relative_path": "periodic_notes/2026-07-05.md",
     "expected_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
     "updates": [
       {"vault_id": "sk_x1c9q2", "mark_done": true, "done_date": "2026-07-05"},
       {"vault_id": "sk_m3k8p1", "inject_vault_id": true,
        "source_line_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
     ]}}
← {"id": 44, "ok": true, "result": {"success": true,
     "new_sha256": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
     "updates_applied": [true, false]}}
```

Error frame (uniform for all ops; codes are enum-stable, messages contain relative paths
only):

```jsonc
← {"id": 43, "ok": false, "error": {
     "code": "path_escapes_wall",
     "message": "relative path is outside the allowed folders"}}
```

---

### Decision 4 — Ingest-path consequence: a server-side staging mirror feeds the EXISTING engine; the reconciler is the bridge

This is the real architectural work. Today `ingest_directory` collects files from the
**server's local disk** (`collect_files_detailed` globs `**/*.md` / `**/*.yaml` under the
root and applies the wall) and every downstream mechanism — `IngestionMetadata` hash
tracking, smart-mode skip, deletion reconciliation, the mass-deletion valve, owner scoping,
`plan_deletions` for preview — is keyed on **file paths under a scannable root**. None of
that can walk a vault on the user's laptop.

**Ruling: Stage-2 sync pulls changed files through the port into a server-side
per-user staging mirror, then feeds the EXISTING ingestion engine unchanged. The
`VaultReconciler` is the bridge** — it is already the single directory-ingest engine
(ADR-070 Decision 9), so port-transport-to-ingest bridging lands in exactly one place.

**The mirror.** A persistent server-side directory containing a copy of the agent's
allowed subtree, rooted at the user's member-vault path
(`{SKUEL_USER_VAULTS_ROOT}/{user_uid}/` — the per-user layout #521 already built; for a
`local_agent`-transport user this directory IS the mirror, populated by sync instead of by
hand). Mirror refresh is a new pre-ingest phase in `VaultReconciler.sync`, active only when
the descriptor's transport is `local_agent`:

1. `list_changed_since(null)` → full listing of allowed files (relative path, content_hash,
   mtime, size).
2. For each listed file: if absent from the mirror or the mirror copy's sha256 differs from
   the listed `content_hash` → `read_note`, verify the returned `sha256` matches the listing
   (torn-read guard), write to `{mirror_root}/{relative_path}` atomically.
3. Mirrored files **absent from the listing are deleted from the mirror** — the mirror is a
   cache of the listing, nothing more.
4. Then run the **existing** Stage-1 body verbatim: `ingest_directory(mirror_root,
   ingestion_mode="smart", …)` with the descriptor's owner and allowlist.

**Why a persistent mirror and not an in-memory batch:** the ingest engine, the tracker, and
the deletion planner all speak `Path`-under-root. An in-memory batch would require teaching
`collect_files` / `IngestionTracker.reconcile_deletions` / `plan_deletions` a second,
non-filesystem source — dual code paths through the ingestion core, precisely what One Path
Forward forbids and what ADR-070 Decision 5's drop-in guarantee promised to avoid. With the
mirror, **the entire ingestion engine cannot tell Stage 2 from Stage 1**; the transport
collapses to "keep this directory faithful to the device, then do what you already do."
The mirror holds allowed-folder content only — the exact material the graph already stores —
so it adds no new server-side data exposure (Decision 1), and it is server-internal state:
never a git repo, never synced anywhere (vault privacy foundation).

**Change detection maps onto `IngestionMetadata` untouched.** Two independent hash layers,
each already existing or trivially local:

| Layer | Compares | Decides | Mechanism |
|---|---|---|---|
| Mirror refresh | agent's `content_hash` vs mirror file's sha256 | **fetch or not** (bandwidth) | new, in reconciler, `local_agent` only |
| Smart-mode ingest | mirror file's hash vs `IngestionMetadata` tracked hash | **ingest or not** (work) | existing, byte-for-byte unchanged |

Same skip semantics as smart mode because it IS smart mode — an unchanged file is skipped by
layer 1 (never fetched) *and* would be skipped by layer 2 (tracked hash matches). A file
changed on the device flows fetch → mirror → hash mismatch vs tracked → ingest. `force=True`
keeps its meaning: it bypasses layer 2 (re-process unchanged), never layer 1 (no pointless
re-fetch of hash-identical content).

**Deletion reconciliation: files absent from the agent's listing become candidates through
the SAME machinery.** Mirror refresh step 3 removes them from the mirror; the existing
`reconcile_deletions` then sees exactly what it sees today when a file is deleted locally —
a tracked row whose file is gone. Every guard from the security arc applies with zero new
code: the mass-deletion threshold valve (#524) refuses majority wipes (now *also* covering
"agent misconfigured its root and listed almost nothing" — the valve's best new customer),
owner-scoped deletion (#522) refuses cross-owner deletes, and the plan/execute split (#527)
means `VaultReconciler.preview` works against the mirror unmodified. (Preview reports the
mirror's state as of the last refresh; a preview does not dial the agent.)

---

### Decision 5 — Security invariants carried forward (each one, explicitly)

Every invariant from #521–#527 survives the transport swap. Stated one by one:

- **Consent-before-read (#523):** unchanged and still FIRST. `VaultReconciler.sync` checks
  `vault_write_consent` before any vault read — in Stage 2 that means **before the first
  `list_changed_since` or `read_note` RPC is issued**. An enrolled, connected agent whose
  owner has not consented gets `first_run_notice` and the server pulls nothing. (Enrollment
  and the WS handshake exchange no vault content — connection metadata and `describe_wall`'s
  folder names are the pre-consent maximum.)
- **Per-root lock (#525):** the lock keys on a stable per-user vault identity instead of an
  arbitrary local path. Concretely free: the key is already
  `str(descriptor.root.resolve())`, and for `local_agent` transport the descriptor root IS
  the per-user mirror root — one stable path per `(user, kind)`. Mirror refresh runs inside
  the same lock as ingest + outbound, so a preview can never race a half-refreshed mirror.
- **Error sanitization (#525):** trivially preserved, and upgraded from discipline to
  structure — wire paths are already vault-relative, and the server never learns the
  device-side absolute root, so no code path CAN leak it. Mirror-side absolute paths (server
  internal) keep the existing `display_path`/`strip_root_prefix` treatment.
- **Fail-closed doorway wall — on BOTH sides:** **agent-side enforcement is primary.** The
  agent applies its own allowlist (config file, defaulting to the same doorway folders as
  `_DEFAULT_SYNC_SUBDIRS`, plus the unconditional `je_*` staging floor) to `list_changed_since`,
  `read_note`, AND `write_task_updates` — walled content never crosses the wire in either
  direction. The server-side descriptor wall stays exactly as-is, applied over the mirror
  scan, as **defense in depth**: the effective wall is the intersection, and a compromised or
  misconfigured side cannot widen it alone. This is also the per-user allowlist shape
  ADR-070 Decision 8 predicted — the agent's config is owned and discoverable by the person
  whose privacy it governs, and `describe_wall` keeps the server's UI honest about it.
- **Per-user roots (#521):** `VaultRegistry` grows a **transport dimension**. The injected
  `PersonalDescriptorFactory` builds the descriptor's `bridge` as a `LocalAgentVaultAdapter`
  bound to the user's device channel (resolved from the channel registry at call time)
  instead of a `FilesystemVaultAdapter` bound to a filesystem root. Root, owner, allowlist,
  and `supports_task_round_trip` are untouched; `resolve_by_path`, the nested-root guards,
  and the surface-independence guard all keep working because the mirror root lives in the
  member-vault layout they already govern.

---

### Decision 6 — Composition + rollout: `VAULT_TRANSPORT` env, filesystem default, no dual paths in core

**`VAULT_TRANSPORT=filesystem|local_agent`**, default `filesystem` — Stage 1 is byte-for-byte
unchanged when unset. Read once at the composition root (`services_bootstrap/compose.py`),
which builds the `PersonalDescriptorFactory` with the chosen bridge class and, for
`local_agent`, wires the channel registry + mirror-refresh dependencies into the reconciler.
Local dev keeps `filesystem` forever — the agent is never a local-dev requirement.

**No dual code paths in `core/`.** The `VaultBridgePort` already isolates transport (ADR-070
Decision 5's drop-in guarantee); `LocalAgentVaultAdapter` lives in
`adapters/vault/local_agent_adapter.py` (the slot ADR-070 reserved), the channel registry and
WS endpoint live in `adapters/inbound/`, and the only `core/` change is the reconciler's
mirror-refresh pre-phase — expressed against the port, transport selected by descriptor
capability, not by `isinstance` sniffing (SKUEL011). The content vault is unaffected: it is
server-local by definition (admin-authored curriculum), stays on `filesystem` transport
regardless of the env, and the env applies to personal descriptors only.

---

### Decision 7 — Explicitly deferred

- **Agent auto-update / distribution packaging** (installers, signed binaries, brew/winget).
  B3 ships a uv-runnable script; packaging is downstream of the hosting milestone.
- **Multi-device conflict handling beyond the existing SHA stale-read guard.** Multiple
  devices may be enrolled; v1 syncs through the single live channel per user. Two devices
  holding divergent copies of the same vault is the user's file-sync tool's problem
  (Syncthing/iCloud), guarded per-file by `expected_sha256` exactly as Stage 1 guards
  concurrent local editors.
- **Push-from-agent.** The agent never initiates a sync; server-initiated sync stays
  human-initiated per ADR-070 Decision 9. A connected-but-idle agent transfers nothing.
- **The separate dumb-relay deployment** (Decision 1). The envelope is designed to survive
  its insertion; building it waits for a deployment that actually needs NAT traversal beyond
  outbound-WS.
- **Curriculum writeback over the channel** — `supports_task_round_trip=False` vaults remain
  inbound-only, unchanged from ADR-070.

---

## Alternatives Considered

### Alternative A — True E2E encryption with the server as a blind relay
**Rejected as incoherent for this topology (Decision 1).** The app server must read plaintext
to ingest. A blind relay would require moving ingestion onto the user's device — shipping the
entire parsing/entity/graph pipeline into the agent — which inverts the architecture and
still hands the server the resulting entities in plaintext.

### Alternative B — Agent exposes an inbound port; server dials the agent
**Rejected.** Requires port-forwarding/firewall configuration on every user machine and turns
each user's laptop into an internet-reachable service. Outbound-only WS is the Syncthing/
Tailscale-established answer and needs zero user network configuration.

### Alternative C — In-memory batch instead of a staging mirror
**Rejected (Decision 4).** Requires a second non-filesystem source of truth threaded through
`collect_files`, the tracker, deletion planning, and the valves — dual code paths through the
ingestion core for zero privacy gain (the mirror holds only what the graph already stores).

### Alternative D — Periodic-sync daemon mode in the agent
**Rejected.** A background timer in the agent is Alternative E of ADR-070 wearing a client
hat — ADR-070 Decision 9 rejected exactly this shape ("a scheduled `--once` is a continuous
watcher wearing a cron hat"). The agent holds a channel open; humans trigger syncs.

### Alternative E — mTLS client certificates instead of Ed25519 challenge–response
**Rejected.** mTLS at the app layer fights every reverse proxy / PaaS TLS terminator between
agent and app (DO App Platform terminates TLS before the app sees the connection). The
in-band challenge-signature handshake works through any TLS-terminating infrastructure and
keeps device identity in the graph where SKUEL's auth already lives.

---

## Consequences

### Positive
- ✅ Cloud deployment (Neo4j Stage 2/3) is unblocked: the vault no longer needs to share a
  disk with the app.
- ✅ The privacy wall is enforced on the user's own device before content ever leaves it —
  strictly stronger than Stage 1's server-side wall.
- ✅ The ingestion engine, valves, owner scoping, preview, and consent gate are reused
  byte-for-byte; the transport swap is invisible below the reconciler's mirror phase.
- ✅ Device enrollment/revocation is graph-native and auditable, consistent with SKUEL's
  graph-native auth.

### Negative
- ⚠️ The server holds a mirror of allowed vault content on its disk (same data the graph
  holds, but a second copy to protect operationally — disk encryption at the hosting layer
  becomes part of the deployment checklist).
- ⚠️ Sync availability now depends on the user's agent being running and connected; the
  failure mode is explicit ("agent not connected") but new.
- ⚠️ A user-side component exists for the first time — version skew between agent and server
  protocol is a real category (mitigated by the `protocol` field in the handshake; hard-fail
  on mismatch in v1).

### Open questions (all resolved)
- **Mirror retention on revocation/departure. RESOLVED in B4: revoking the last device
  RETAINS the mirror; account deletion owns its purge.** The mirror IS the user's synced
  data store server-side — the staging copy of exactly the content the graph already holds.
  Revocation is an *access* event (the device can no longer connect), not a *data-deletion*
  event; deleting user data as a side effect of revoking a credential would violate the
  deletion-valve philosophy (deletions are explicit, guarded, and owner-driven — never
  implied). Retention also makes re-enrollment cheap: a fresh device resumes with an intact
  mirror and the first sync fetches only what changed. Account-deletion flows, when built,
  own removing `{SKUEL_USER_VAULTS_ROOT}/{user_uid}/` alongside the user's graph data —
  the mirror is purged where the rest of the user's data is purged, in one deliberate flow.
- **`list_vault_notes` harmonization. RESOLVED in B4: the port returns vault-RELATIVE POSIX
  paths for ALL adapters** (One Path Forward — #525 made relative the only shape that ever
  leaves the service layer, and wire paths are structurally relative). `vault_path` scopes
  the listing to a subdirectory; returned paths stay relative to the vault ROOT.
  `FilesystemVaultAdapter` migrated with it; no production consumer existed beyond protocol
  conformance, so the swap was call-site-free. Relatedly, B4 realized "the port grows
  `list_changed_since` + `describe_wall`" as a **`RemoteVaultBridgePort` extension protocol**
  (same module) rather than widening `VaultBridgePort` itself: the filesystem transport has
  no self-reported wall (the server-side allowlist IS its wall) and the ingest engine walks
  its root directly — a filesystem `describe_wall` would fabricate honesty, and One Path
  Forward deletes fake implementations rather than shipping them.
- **Pairing-code storage node:** hashed code as a property on `User` vs. a short-lived
  `(:PairingCode)` node — B2 implementation detail, decided there. **RESOLVED in B2:
  properties on `User`** (`pairing_code_hash` + `pairing_code_expires_at`) — one active
  code per user, atomic `REMOVE` burn on redemption, and no orphan-node TTL cleanup job
  (preserves the CORE-tier no-background-workers guarantee). See `core/models/auth/device.py`.

---

## PR Plan (appendix)

Three PRs, in dependency order. This ADR is B1 of the Stage-2 sub-arc following #521–#527.

### B2 — Server: device identity + channel
- `Device` node + `HAS_DEVICE` (`RelationshipName` entry), behind `UserService` methods
  (enroll, list, revoke, verify-pubkey).
- Routes: `POST /api/devices/pairing-code` (authed), `POST /api/devices/enroll`
  (code-authenticated, rate-limited), `POST /api/devices/{uid}/revoke` (authed),
  Settings → Devices UI (list + revoke + pair flow).
- `WS /ws/agent` endpoint: challenge–signature handshake (Decision 3), per-user
  `AgentChannelRegistry` (adapters-side), `last_seen_at` stamping, revocation closes live
  sessions.
- Unit tests: handshake accept/reject matrix (unknown key, bad signature, revoked, expired
  code, replayed code).

### B3 — Agent: the user-side component
- **Placement: `agent/` top-level package** (`agent/skuel_vault_agent.py` + `agent/README.md`),
  NOT `scripts/`. Rationale: `scripts/` is server-operator tooling that assumes the repo's
  venv; the agent runs on user machines that may not have the repo. Single-file,
  **uv-runnable via PEP 723 inline script metadata** (`uv run agent/skuel_vault_agent.py`),
  minimal deps (`websockets`, `cryptography`).
- Config: `~/.config/skuel-agent/config.toml` — vault root, server URL, allowed folders
  (defaulting to the doorway set); key at `~/.config/skuel-agent/device.key` (0600,
  permission-checked at startup).
- Commands: `enroll` (pairing-code flow), `run` (connect + serve the four ops).
- Serves `describe_wall` / `list_changed_since` / `read_note` / `write_task_updates` with
  agent-side containment (`_resolve`-equivalent) + allowlist + `je_*` floor on every op;
  atomic writes via temp-file + `rename()`.

### B4 — Adapter + reconciler bridge + toggle
- `adapters/vault/local_agent_adapter.py`: `LocalAgentVaultAdapter` implementing
  `VaultBridgePort` over the channel registry; port grows `list_changed_since` +
  `describe_wall`; `list_vault_notes`/path shapes harmonized to vault-relative for both
  adapters (open question above, resolved here).
- Reconciler mirror-refresh pre-phase (Decision 4) inside the per-root lock; `describe`
  sources the wall from `describe_wall` for `local_agent` descriptors.
- `VAULT_TRANSPORT` wiring in `compose.py` (Decision 6); `FilesystemVaultAdapter` default
  untouched.
- **Integration test with an in-process fake agent**: a fake WS peer speaking the exact
  envelope (handshake + four ops) against a temp directory, driving a full sync — listing →
  fetch → mirror → smart ingest → deletion valve → outbound write-back — and a
  revoked-device negative path. (Shipped as `tests/unit/test_local_agent_transport.py` — an
  in-process end-to-end proof with no sockets or live DB, so CI's `unit_tests` job runs it.)

---

## Documentation

### Related Documentation
- ADR-070: Bidirectional VaultBridge (Decisions 5, 6, 9 — this ADR implements Decision 6's
  Stage 2)
- ADR-044: Hexagonal boundary (port in `core/ports/`, transport in `adapters/`)
- ADR-073: Journals zero-persistence (`je_*` floor enforced agent-side too)
- `docs/patterns/UNIFIED_INGESTION_GUIDE.md` § remote vaults ride a staging mirror
- `core/services/vault/vault_descriptor.py` (descriptor/registry — the transport dimension
  is `VaultDescriptor.mirror_pull`; `None` = filesystem)
- `core/services/vault/mirror_sync.py` (`VaultMirrorPuller` — the Decision 4 refresh)

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-07-05 | Claude Code | Initial design ADR — Stage-2 transport spec (topology honesty, Ed25519 device identity, WS protocol, staging-mirror ingest bridge, invariants carried forward, B2/B3/B4 plan) | 0.1 |
| 2026-07-06 | Claude Code | B3 shipped — `agent/skuel_vault_agent.py` (enroll/run/status, four RPC ops, agent-side wall; line mutations shared via `/core/ports/vault_bridge_protocol.py`). See `/docs/guides/VAULT_AGENT_GUIDE.md` | 0.2 |
| 2026-07-06 | Claude Code | B4 shipped — sub-arc complete. `LocalAgentVaultAdapter` (`adapters/vault/local_agent_adapter.py`) + `RemoteVaultBridgePort`; `VaultMirrorPuller` mirror-refresh pre-phase in `VaultReconciler.sync` (Decision 4, inside the per-root lock; preview never dials); `describe` sources the wall from `describe_wall` (intersection); `VAULT_TRANSPORT=filesystem\|local_agent` (Decision 6, filesystem default, personal descriptors only). Open questions RESOLVED: mirror retained on last-device revocation (account deletion owns the purge); `list_vault_notes` harmonized to vault-relative for all adapters. In-process end-to-end proof: `tests/unit/test_local_agent_transport.py` (real agent handler ↔ real registry/adapter/reconciler, no sockets) | 1.0 |
| 2026-07-06 | Claude Code | Kody #531 hardening: mirror populate scope is the ENFORCED agent ∩ server intersection (`describe_wall` binding, not decorative; sweep keeps the wider server scope so a newly-hidden agent folder retracts retroactively); `VAULT_TRANSPORT=local_agent` fails startup when `VAULT_ROOT`/`SKUEL_USER_VAULTS_ROOT` overlaps `INGESTION_PATH` (either direction — the mirror sweep treats its root as pull-managed cache, a combined layout would delete curriculum) | 1.1 |
