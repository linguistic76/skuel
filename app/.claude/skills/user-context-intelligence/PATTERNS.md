# User Context Intelligence - Patterns

The patterns are documented where they apply:

- [SKILL.md](SKILL.md) § Rich Context Is Required, § Anti-Patterns
- [FACTORY_PATTERN.md](FACTORY_PATTERN.md) § Runtime Usage, § Anti-Patterns
- [MIXIN_ARCHITECTURE.md](MIXIN_ARCHITECTURE.md) § Adding a Mixin, § Testing a Mixin

The rules in one place:

1. Read a **rich** context (`UserService.get_rich_unified_context`), check the `Result`, then
   `factory.create(context)`.
2. Take the factory from the container (`services.context_intelligence`) or by injection. Do not
   construct `UserContextIntelligence` directly, and do not build a second factory.
3. Create an instance per request. The context cache is the reuse mechanism.
4. Check each method's `Result` and propagate a failure with `Result.fail(result)`.
   Every hub method returns one; method 8's is always ok (fail-soft: fewer candidates,
   never an error), but it is read like the others.
