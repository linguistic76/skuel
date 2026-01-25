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

Facade Delegation:
    - FacadeDelegationMixin: Auto-generates delegation methods for facade services

Static Delegation Specs:
    - CRUD_DELEGATIONS: Standard CRUD delegations to "core" sub-service
    - SEARCH_DELEGATIONS: Standard search delegations to "search" sub-service
    - RELATIONSHIP_DELEGATIONS: Standard relationship delegations

Delegation Factories (domain-prefixed):
    - create_core_delegations(domain): get_{domain}, get_user_{domain}s, get_user_items_in_range
    - create_relationship_delegations(domain): get_{domain}_cross_domain_context, etc.
    - create_intelligence_delegations(domain): get_{domain}_with_context

Utilities:
    - merge_delegations: Merge multiple delegation dictionaries
"""

# BaseService decomposition mixins (January 2026)
from core.services.mixins.context_operations_mixin import ContextOperationsMixin
from core.services.mixins.conversion_helpers_mixin import ConversionHelpersMixin
from core.services.mixins.crud_operations_mixin import CrudOperationsMixin

# Facade delegation mixin and utilities
from core.services.mixins.facade_delegation_mixin import (
    CRUD_DELEGATIONS,
    RELATIONSHIP_DELEGATIONS,
    SEARCH_DELEGATIONS,
    FacadeDelegationMixin,
    create_core_delegations,
    create_intelligence_delegations,
    create_relationship_delegations,
    merge_delegations,
)
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
    # Facade delegation
    "FacadeDelegationMixin",
    "merge_delegations",
    # Static specs (generic names - rarely used directly)
    "CRUD_DELEGATIONS",
    "SEARCH_DELEGATIONS",
    "RELATIONSHIP_DELEGATIONS",
    # Factories (domain-prefixed names - use these)
    "create_core_delegations",
    "create_relationship_delegations",
    "create_intelligence_delegations",
]
