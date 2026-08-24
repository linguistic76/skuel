# Vault Agent Guide — Enroll, Run, Revoke

**Purpose:** Walk a user through pairing their machine with a hosted SKUEL server and serving their Obsidian vault through the local agent (ADR-075 B3).

**Audience:** SKUEL users on a hosted deployment; operators supporting them

**Last Updated:** 2026-07-06

---

## What the agent is

When SKUEL runs in the cloud, it cannot read your vault off its own disk. The
**vault agent** is a small program you run on YOUR machine — the only thing
that ever touches your vault files. It dials one outbound WebSocket to the
server (no open ports, works behind NAT/firewalls) and answers vault requests
during a sync you trigger.

Privacy properties (enforced on your device, before anything crosses the wire):

- Only the doorway folders are served: `activity_notes/`, `knowledge/`,
  `periodic_notes/`, `personal_notes/`. Everything else — including `je_*`
  journal staging — **never leaves your machine**.
- The server never learns your vault's absolute path; all wire paths are
  vault-relative.
- Your device's Ed25519 private key never leaves
  `~/.config/skuel-agent/device.key` (mode `0600`, the SSH threat model).

## 1. Enroll (once per machine)

1. In SKUEL, open **Settings → Devices** and click **Generate pairing code**.
   The 8-character code is shown once and expires in 10 minutes.
2. On your machine, from a SKUEL checkout:

   ```bash
   uv run agent/skuel_vault_agent.py enroll \
       --server https://your-skuel-server \
       --vault ~/path/to/your/vault \
       --name my-laptop
   ```

3. Paste the pairing code when prompted (it is read like a password — never
   put it on the command line).

This generates the device keypair (reusing an existing one on re-enrollment),
registers the public key with the server, and writes
`~/.config/skuel-agent/config.toml`.

## 2. Run

```bash
uv run agent/skuel_vault_agent.py run
```

Leave it running. It connects to `wss://…/ws/agent`, proves possession of the
device key by signing the server's challenge, then answers vault RPCs. Syncs
stay **human-initiated** (ADR-070 Decision 9): a connected-but-idle agent
transfers nothing until you click "Update from my vault" in SKUEL.

If the connection drops, the agent reconnects with capped exponential backoff.
It stops (instead of reconnecting) when the server says the device was
revoked, not enrolled, or superseded by another agent for your account.

`uv run agent/skuel_vault_agent.py status` shows your config, key state, and
server reachability.

## 3. Revoke

In **Settings → Devices**, click **Revoke** next to the device. Its live
connection is closed immediately and future handshakes fail. Re-pairing later
just repeats step 1 — the agent reuses its key if the file still exists.

## Server side: enabling the local-agent transport (operators)

The agent only matters when the SKUEL server is configured to reach vaults
through it. In the server's `.env`:

```bash
VAULT_TRANSPORT=local_agent   # default: filesystem
```

- `filesystem` (default) — Stage 1, byte-for-byte unchanged: personal vaults
  are read off the server's own disk. Local dev keeps this forever; the agent
  is never a local-dev requirement.
- `local_agent` — Stage 2 (ADR-075): every personal-vault sync pulls changed
  files from the user's connected agent into a server-side **staging mirror**
  at `{SKUEL_USER_VAULTS_ROOT}/{user_uid}/`, then the existing ingestion
  engine (smart-mode skip, deletion reconciliation + valves, owner scoping,
  preview) runs on the mirror unchanged. No connected agent → the sync fails
  fast with "agent not connected — start `skuel-vault-agent run`".

Notes for operators:

- The toggle applies to PERSONAL vaults only; the content vault
  (`INGESTION_PATH`, admin curriculum) is server-local by definition and
  always stays filesystem.
- An unknown `VAULT_TRANSPORT` value fails the compose fast at startup.
- The mirror holds allowed-folder content only (the same material the graph
  stores). It is server-internal state — never a git repo, never synced
  anywhere; disk encryption at the hosting layer is part of the deployment
  checklist.
- Revoking a user's last device keeps their mirror (re-enrollment resumes
  cheaply); account-deletion flows own removing it (ADR-075 open-question
  ruling).

## Troubleshooting

| Symptom | Meaning |
|---------|---------|
| `pairing code invalid, expired, or already used` | Codes are single-use with a 10-minute TTL — generate a fresh one. |
| `Server refused this device (device_not_enrolled)` | The device was revoked or never enrolled — re-enroll. |
| `Protocol mismatch` | Agent and server speak different protocol versions — update the agent by pulling the repo on the device (the agent hard-fails on mismatch by design; no compatibility path). The shared line-hash digest is part of the protocol, so a digest change bumps it — v2 (2026-08-23) strips the `✅` done-date token. |
| `Refusing to use … permissions are too open` | `chmod 600 ~/.config/skuel-agent/device.key` (same posture as OpenSSH). |
| `rate-limited` | The server caps handshakes per IP; wait a minute. |
| `Refusing non-HTTPS server URL …` | Off localhost the agent requires `https://` — plaintext would expose the pairing code and vault content. |

## See also

- `/docs/decisions/ADR-075-local-agent-vault-transport.md` — the transport spec
  (B2 server half, B3 this agent, B4 adapter + reconciler bridge)
- `/agent/README.md` — developer notes on the agent's structure
- `/docs/decisions/ADR-070-bidirectional-vault-bridge.md` — the vault bridge itself
