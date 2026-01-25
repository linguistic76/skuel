---
title: Semantic Analysis Implementation Roadmap
updated: 2025-11-27
status: current
category: intelligence
tags: [analysis, intelligence, roadmap, semantic]
related: []
---

# Semantic Analysis Implementation Roadmap

**Endpoint:** `/api/search/semantic-analysis`
**Status:** FUTURE_VISION (Shelved until prerequisites met)
**Priority:** Medium
**Estimated Effort:** 3-4 days

---

## What It Does

Analyzes text content to understand:
- Linguistic structure (sentence complexity, readability)
- Semantic roles (who does what to whom)
- Knowledge extraction (facts, relationships, concepts)
- Discourse analysis (coherence, argumentation structure)

---

## Prerequisites (Check These First)

- [ ] SKUEL has 50+ knowledge units with rich text content
- [ ] Users are creating and editing content regularly
- [ ] OpenAI API integration is stable and tested
- [ ] Core search functionality is proven valuable

**DO NOT implement until all prerequisites are met.**

---

## Implementation Plan

### Day 1: TextAnalysisService Foundation
Create `/core/services/text_analysis_service.py`:
```python
class TextAnalysisService:
    def analyze_readability(self, text: str) -> dict:
        """Calculate Flesch reading ease, grade level"""

    def extract_sentences(self, text: str) -> List[str]:
        """Simple sentence tokenization"""

    def calculate_complexity(self, text: str) -> float:
        """Word count, avg sentence length, vocabulary diversity"""
```

**Tools:** Python stdlib only (no external NLP libraries initially)

---

### Day 2: Semantic Role Extraction
Extend TextAnalysisService:
```python
def extract_semantic_roles(self, text: str) -> dict:
    """Pattern-based extraction of agents, actions, objects"""
    # Use SearchIntelligenceService for domain detection
    # Use simple regex patterns for verb/noun identification
```

**Keep It Simple:** Start with pattern matching, not full NLP parsing

---

### Day 3: Integration with OpenAI
```python
async def analyze_semantic_content(
    self,
    content: str,
    embeddings_service: OpenAIEmbeddingsService
) -> dict:
    # 1. Basic text analysis (TextAnalysisService)
    linguistic = self.text_analysis.analyze_readability(content)

    # 2. Get embeddings for similarity
    embedding = await embeddings_service.get_embedding(content)

    # 3. Extract concepts (SearchIntelligenceService)
    intent = self.search_intelligence.analyze_query_intent(content)

    return {
        "linguistic_analysis": linguistic,
        "semantic_features": {...},
        "knowledge_extraction": {...}
    }
```

---

### Day 4: Testing & Refinement
- Test with real knowledge units
- Compare results with user expectations
- Adjust complexity metrics
- Document limitations

---

## Services Needed

| Service | Status | Create? |
|---------|--------|---------|
| OpenAIEmbeddingsService | ✅ Exists | No |
| SearchIntelligenceService | ✅ Exists | No |
| TextAnalysisService | ❌ Doesn't exist | Yes |

---

## Success Criteria

**Before considering this "done":**
- [ ] Returns meaningful readability scores
- [ ] Identifies key concepts accurately
- [ ] Complexity metrics match human judgment
- [ ] Helps users understand their content better

**Not required:** Perfect NLP, academic-grade analysis

---

## Limitations to Accept

This will NOT be:
- Full linguistic parsing (no parse trees)
- Multi-language support (English only initially)
- Academic-quality NLP (good enough is fine)
- Real-time (can be slow for large content)

**That's okay!** Start simple, improve based on real usage.

---

## When to Implement

✅ **Implement when:**
- You have 100+ knowledge units with varied content
- Users want to understand content complexity
- Search results need better relevance scoring
- You have 2-3 days to focus on this feature

❌ **Don't implement if:**
- Core features aren't stable yet
- Content corpus is still small
- Users haven't requested content analysis
- You have higher priority work
