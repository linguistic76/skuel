"""
Service Mixins
==============

Reusable mixins for SKUEL services.

BaseService Decomposition Mixins (January 2026):
    - ConversionHelpersMixin: DTO conversion and result handling
    - CrudOperationsMixin: Core CRUD and ownership-verified CRUD
    - SearchOperationsMixin: Text search, graph search, filtering
    - RelationshipOperationsMixin: Graph relationships and prerequisites
    - TimeQueryMixin: Date-based queries for calendar integration
    - UserProgressMixin: Progress and mastery tracking
    - ContextOperationsMixin: Graph context retrieval and enrichment
"""

# BaseService decomposition mixins (January 2026)
from core.services.mixins.context_operations_mixin import ContextOperationsMixin
from core.services.mixins.conversion_helpers_mixin import ConversionHelpersMixin
from core.services.mixins.crud_operations_mixin import CrudOperationsMixin
from core.services.mixins.relationship_operations_mixin import RelationshipOperationsMixin
from core.services.mixins.search_operations_mixin import SearchOperationsMixin
from core.services.mixins.time_query_mixin import TimeQueryMixin
from core.services.mixins.user_progress_mixin import UserProgressMixin

__all__ = [
    # BaseService decomposition mixins
    "ConversionHelpersMixin",
    "CrudOperationsMixin",
    "SearchOperationsMixin",
    "RelationshipOperationsMixin",
    "TimeQueryMixin",
    "UserProgressMixin",
    "ContextOperationsMixin",
]
