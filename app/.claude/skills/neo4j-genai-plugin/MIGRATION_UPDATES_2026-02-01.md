# Neo4j GenAI Plugin Skill - Migration Updates (2026-02-01)

## Summary

Updated the neo4j-genai-plugin skill based on real-world migration from AuraDB Free to local Neo4j Docker with GenAI plugin. The documentation previously contained incorrect function names that didn't match the actual bundled plugin.

## Critical Corrections

### 1. Function Names

**OLD (Incorrect):**
- `ai.text.embed()` - Single embedding
- `ai.text.embedBatch()` - Batch embeddings

**NEW (Correct):**
- `genai.vector.encode()` - Single embedding
- `genai.vector.encodeBatch()` - Batch embeddings

### 2. Required Token Parameter

**Key Discovery:** Local Neo4j installations require passing OpenAI API key as `token` parameter in each function call, unlike AuraDB which configures it at database level.

**Correct Syntax:**
```cypher
RETURN genai.vector.encode(
    $text,
    'OpenAI',
    {
        token: $openai_api_key,  # REQUIRED
        model: 'text-embedding-3-small',
        dimensions: 1536
    }
) AS embedding
```

### 3. Docker Configuration

Added section on local Neo4j Docker setup with GenAI plugin auto-loading:

```yaml
environment:
  NEO4J_PLUGINS: '["genai"]'  # Auto-loads bundled plugin
  NEO4J_genai_openai_api__key: "${OPENAI_API_KEY}"  # Optional
  NEO4J_dbms_security_procedures_unrestricted: "genai.*"
  NEO4J_dbms_security_procedures_allowlist: "genai.*"
```

### 4. Neo4j Versioning

Updated documentation to reflect:
- Neo4j 2025.12.1 (calendar versioning)
- GenAI plugin bundled with Neo4j 5.26+ in `/products` directory
- No manual JAR download required

## New Sections Added

### Local vs AuraDB Configuration

Complete comparison table showing differences in:
- Plugin installation (auto-loaded vs pre-installed)
- API key configuration (per-query vs database-level)
- Neo4j version requirements
- Function syntax differences

### Troubleshooting

Added 7 common issues encountered during migration with solutions:

1. **"Unknown function 'ai.text.embed'"** - Use correct `genai.vector.encode()` name
2. **"'token' is expected to have been set"** - Pass API key as token parameter
3. **"'list' object has no attribute 'get'"** - Correct result tuple unpacking
4. **GenAI plugin not found** - Add `NEO4J_PLUGINS='["genai"]'` to docker-compose
5. **Authentication failure after password change** - Delete Neo4j data directory (bind-mount persists)
6. **"OPENAI_API_KEY not set" warning** - Load .env before importing services
7. **Embeddings work in Browser but fail in Python** - Verify parameter name matching

Each issue includes verification commands and code examples.

## Files Modified

- `/home/mike/skuel/app/.claude/skills/neo4j-genai-plugin/SKILL.md` (1556 lines)
  - Updated 15+ code examples with correct function names
  - Added Local vs AuraDB configuration section
  - Added Docker setup section
  - Added Troubleshooting section with 7 issues
  - Updated skill description to include new trigger keywords

## Code Examples Updated

Updated all Cypher patterns throughout the file:
- Single embedding generation (3 variants)
- Batch embedding generation (2 patterns)
- Metadata storage patterns
- Anti-patterns section (5 examples)
- Python integration examples (references to Cypher)

## Verification

All changes verified against:
- Working local Neo4j 2025.12.1 Docker instance
- Successfully generated 1536-dimensional embeddings
- Created 5 vector indexes (all ONLINE status)
- SKUEL application running successfully with GenAI enabled

## Migration Context

These updates resulted from actual migration work documented in:
- `/home/mike/skuel/infrastructure/docker-compose.yml` (Neo4j 2025.12.1)
- `/home/mike/skuel/infrastructure/.env` (GenAI configuration)
- `/home/mike/skuel/app/core/services/neo4j_genai_embeddings_service.py` (Updated service)
- `/home/mike/skuel/app/scripts/create_vector_indexes.py` (Vector index creation)

## Impact

**Before:** Skill contained theoretical documentation with incorrect function names
**After:** Skill contains production-verified patterns from actual migration

**Benefit:** Future developers won't encounter the same "function not found" errors and will have correct Docker setup from the start.

---

**Updated by:** Claude Code (based on migration work with user Mike)
**Date:** 2026-02-01
**Status:** ✅ Complete - All function references updated, new sections added
