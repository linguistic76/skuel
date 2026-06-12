"""
Adaptive Learning Path Services
================================

Cross-domain opportunity discovery for learning paths.

- AdaptiveLpCrossDomainService: Cross-domain opportunity discovery
  (bootstrapped at the composition root, exposed via GraphQL discover_cross_domain)
"""

from core.services.adaptive_lp.adaptive_lp_cross_domain_service import AdaptiveLpCrossDomainService

__all__ = [
    "AdaptiveLpCrossDomainService",
]
