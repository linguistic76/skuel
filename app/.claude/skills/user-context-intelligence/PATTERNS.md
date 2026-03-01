# User Context Intelligence - Patterns

Common usage patterns are documented inline in [SKILL.md](SKILL.md) under **Usage Examples** and **Anti-Patterns**.

Factory-specific patterns live in [FACTORY_PATTERN.md](FACTORY_PATTERN.md) under **Runtime Usage** and **Anti-Patterns**.

This file is intentionally minimal — patterns for this service are straightforward:
1. Get context, create intelligence, call method, check Result.
2. Never cache intelligence instances (context goes stale).
3. Never bypass the factory.
