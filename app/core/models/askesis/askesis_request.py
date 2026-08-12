"""
Askesis Request Models (Tier 1 - External)
===========================================

Pydantic models for API validation and external interfaces.
Handles input validation for the Askesis instance create/update API.
"""

from pydantic import BaseModel, ConfigDict, Field

from core.models.enums import GuidanceMode
from core.models.enums.askesis_enums import QueryComplexity


class AskesisCreateRequest(BaseModel):
    """Request model for creating Askesis instances."""

    name: str = Field(
        default="Askesis", min_length=1, max_length=100, description="Askesis instance name"
    )
    version: str = Field(default="1.0", description="Version identifier")
    preferred_guidance_mode: GuidanceMode = Field(
        default=GuidanceMode.DIRECT, description="Preferred guidance mode"
    )
    preferred_complexity_level: QueryComplexity = Field(
        default=QueryComplexity.MODERATE, description="Preferred query complexity level"
    )

    model_config = ConfigDict(
        use_enum_values=True
        # Pydantic V2 serializes enums automatically
    )


class AskesisUpdateRequest(BaseModel):
    """Request model for updating Askesis instances."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    version: str | None = None
    preferred_guidance_mode: GuidanceMode | None = None
    preferred_complexity_level: QueryComplexity | None = None

    # Intelligence settings
    proactive_guidance_enabled: bool | None = None
    auto_domain_suggestions: bool | None = None
    learning_mode: str | None = Field(default=None, pattern="^(conservative|adaptive|aggressive)$")

    model_config = ConfigDict(use_enum_values=True)
