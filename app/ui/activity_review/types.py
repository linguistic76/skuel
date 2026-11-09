"""Activity Review domain configuration."""

from typing import get_args

from core.models.entity_requests import ActivityReviewDomain

#: (value, label) for each Activity Domain a review covers — the request models'
#: vocabulary, so a ticked box is always a value the doors accept.
DOMAIN_CHOICES: list[tuple[str, str]] = [
    (domain, domain.title()) for domain in get_args(ActivityReviewDomain)
]
