"""
Shared base for Activity Template create-request models.

Hoists the `title` field shared by all six *TemplateCreateRequest classes so
generic code (route factories, converters) can rely on `.title` being present
without per-schema casts.
"""

from __future__ import annotations

from pydantic import Field

from core.models.request_base import CreateRequestBase


class TemplateCreateRequest(CreateRequestBase):
    """Shared base for all *TemplateCreateRequest models — guarantees `title`."""

    title: str = Field(min_length=1, max_length=200, description="Template title")
