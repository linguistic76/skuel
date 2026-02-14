// Migration: Add JOURNAL + RESOURCE KuType values
// Date: 2026-02-15
// Context: KuType.JOURNAL distinguishes raw student submissions (voice/text)
//          from system-driven assignments. Existing journal Ku nodes were
//          created with ku_type='assignment' and need migration to 'journal'.
//          KuType.RESOURCE is new (no existing data to migrate).

// Migrate existing journal Ku from 'assignment' to 'journal' type.
// Journals are identified by having processor_type='llm' — all LLM-processed
// submissions created via /journals route used this processor type.
// Regular assignments use processor_type='human' or 'automatic'.
MATCH (ku:Ku {ku_type: 'assignment', processor_type: 'llm'})
SET ku.ku_type = 'journal'
RETURN count(ku) AS migrated_journals;
