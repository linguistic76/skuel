# SKUEL Vault Agent (ADR-075 B3)

The user-side component of the Stage-2 vault transport: it holds the only
filesystem handle to a user's Obsidian vault, enrolls once with a pairing
code, keeps one outbound WebSocket open to the SKUEL server, and serves the
four vault RPCs (`describe_wall` / `list_changed_since` / `read_note` /
`write_task_updates`).

**User walkthrough:** `docs/guides/VAULT_AGENT_GUIDE.md`
**Wire protocol:** `docs/decisions/ADR-075-local-agent-vault-transport.md` Decision 3
**Server half:** `adapters/inbound/device_routes.py` (handshake),
`adapters/inbound/agent_channel_registry.py` (RPC envelope)

## Running

Single file, uv-runnable via PEP 723 inline metadata — from a SKUEL checkout:

```bash
uv run agent/skuel_vault_agent.py enroll --server https://… --vault ~/vault
uv run agent/skuel_vault_agent.py run
uv run agent/skuel_vault_agent.py status
```

Works both inside the repo venv and as an isolated PEP 723 script
(`uv run --no-project …`): its third-party surface is exactly
`cryptography` + `websockets`, and its only repo import —
`core/ports/vault_bridge_protocol.py`, the shared vault-line mutation
contract — is deliberately stdlib-only, reached via a `sys.path` bootstrap
to the checkout root.

## Design constraints (why the file looks the way it does)

- **NOT `scripts/`** — scripts are server-operator tooling assuming the repo
  venv; the agent runs on user machines (ADR-075 B3 placement ruling).
- **The wall is enforced HERE.** Allowed folders + the `je_*` staging floor +
  root containment + no-symlinks apply to every RPC on the agent side; walled
  content never crosses the wire in either direction (ADR-075 Decision 5).
- **Shared mutation contract, not a copy.** Task-line writes reuse
  `apply_task_updates` from `core/ports/vault_bridge_protocol.py` — the same
  function `FilesystemVaultAdapter` uses — so both transports mutate lines
  byte-identically. Two constants that CANNOT be imported without dragging
  heavy deps (the signature domain from `core/auth/`, the doorway folders
  from ingestion config) are duplicated and pinned by contract tests in
  `tests/unit/test_vault_agent.py`.
- **Interactive CLI** — `print()` is the UI (see CLAUDE.md Logging Patterns);
  the private key and pairing code are never printed or logged, and the
  pairing code is read via `getpass`, never argv.
- Packaging/distribution (installers, signed binaries) is explicitly deferred
  (ADR-075 Decision 7).
