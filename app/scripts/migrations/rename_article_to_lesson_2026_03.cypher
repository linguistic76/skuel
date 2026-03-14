// Migration: Rename Article to Lesson
// Date: 2026-03-15
// Context: Article entity type renamed to Lesson (full clean break)
//
// What this does:
// 1. Adds :Lesson label to all :Article nodes
// 2. Removes :Article label
// 3. Updates entity_type property from "article" to "lesson"
//
// Run with: cypher-shell -f scripts/migrations/rename_article_to_lesson_2026_03.cypher

// Step 1: Add :Lesson label and update entity_type
MATCH (n:Article)
SET n:Lesson
REMOVE n:Article
SET n.entity_type = "lesson"
RETURN count(n) AS migrated_count;
