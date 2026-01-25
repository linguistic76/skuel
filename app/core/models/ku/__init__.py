"""
Knowledge Models - Three-Tier Architecture with RAG Support
===========================================================

This module provides a comprehensive three-tier model structure for Knowledge
with separation of concerns and automatic content chunking for RAG:

Core Architecture:
1. ku.py - Immutable domain model with business logic
2. ku_dto.py - Mutable data transfer objects
3. ku_request.py - External API models (Pydantic)

Content & RAG Support:
4. ku_content.py - Rich content storage with automatic chunking
5. ku_chunks.py - Semantic chunking for RAG retrieval
6. ku_metadata.py - Analytics and search optimization

Separation of Concerns:
- Ku: Lean graph metadata
- KuContent: Rich content with chunks
- KuMetadata: Analytics and search optimization

Usage:
    from core.models.ku import Ku, KuContent, KuChunk
"""

from .ku import Ku
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_dto import KuDTO
from .ku_metadata import KuMetadata
from .ku_request import KuCreateRequest, KuListResponse, KuResponse, KuUpdateRequest

__all__ = [
    # Core domain models
    "Ku",
    "KuChunk",
    "KuChunkType",
    # Content models
    "KuContent",
    # API models
    "KuCreateRequest",
    "KuDTO",
    "KuListResponse",
    "KuMetadata",
    "KuResponse",
    "KuUpdateRequest",
    # Functions
    "chunk_content",
]
