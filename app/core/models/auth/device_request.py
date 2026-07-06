"""
Device Request Models — API boundary validation (ADR-075)
=========================================================

Pydantic request model for the code-authenticated enrollment door
(``POST /api/devices/enroll``). Field names match the ADR-075 Decision 2
wire shape exactly: ``{code, device_pubkey, device_name}``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.models.auth.device import DEVICE_NAME_MAX_LENGTH


class DeviceEnrollRequest(BaseModel):
    """Agent-submitted enrollment payload — the pairing code IS the credential."""

    code: str = Field(min_length=1, max_length=64, description="One-time pairing code")
    device_pubkey: str = Field(
        min_length=1,
        max_length=128,
        description="base64url DER-SPKI Ed25519 public key",
    )
    device_name: str = Field(
        min_length=1,
        max_length=DEVICE_NAME_MAX_LENGTH,
        description="User-chosen device label",
    )


__all__ = ["DeviceEnrollRequest"]
