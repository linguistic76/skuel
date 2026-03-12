// Migration: Rename preferred_conversation_style → preferred_guidance_mode
// and map old GuidanceMode values to new ones.
// Date: 2026-03-12
// Context: Askesis evolution — absorb Socratic patterns into existing architecture

// Step 1: Rename property on Askesis nodes
MATCH (a:Askesis)
WHERE a.preferred_conversation_style IS NOT NULL
SET a.preferred_guidance_mode = a.preferred_conversation_style
REMOVE a.preferred_conversation_style
RETURN count(a) AS askesis_nodes_migrated;

// Step 2: Map old GuidanceMode values to new ones on any node that has them
// MINIMAL → EXPLORATORY (was "let them explore", now explicit)
// BALANCED → DIRECT (was the default, DIRECT is the new default)
// DETAILED → DIRECT (informational content, closest to DIRECT)
// ADAPTIVE → DIRECT (was dynamic, DIRECT is the safe default)
MATCH (n)
WHERE n.preferred_guidance_mode IN ['minimal', 'balanced', 'detailed', 'adaptive']
SET n.preferred_guidance_mode = CASE n.preferred_guidance_mode
    WHEN 'minimal' THEN 'exploratory'
    WHEN 'balanced' THEN 'direct'
    WHEN 'detailed' THEN 'direct'
    WHEN 'adaptive' THEN 'direct'
END
RETURN count(n) AS guidance_mode_values_migrated;

// Step 3: Same for guidance_mode on ConversationSession nodes (if stored)
MATCH (n)
WHERE n.guidance_mode IN ['minimal', 'balanced', 'detailed', 'adaptive']
SET n.guidance_mode = CASE n.guidance_mode
    WHEN 'minimal' THEN 'exploratory'
    WHEN 'balanced' THEN 'direct'
    WHEN 'detailed' THEN 'direct'
    WHEN 'adaptive' THEN 'direct'
END
RETURN count(n) AS session_guidance_values_migrated;

// Step 4: Rename conversation_style → guidance_mode on ConversationSession DTOs
MATCH (n)
WHERE n.conversation_style IS NOT NULL
SET n.guidance_mode = n.conversation_style
REMOVE n.conversation_style
RETURN count(n) AS conversation_style_renamed;
