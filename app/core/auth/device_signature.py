"""
Device Signature Verification — Ed25519 Challenge-Response (ADR-075)
====================================================================

Framework-free crypto helpers for the ``WS /ws/agent`` handshake
(ADR-075 Decision 3). The agent proves possession of its enrolled device
private key by signing the server's challenge nonce with a domain-separation
prefix; the server verifies against the enrolled public key.

Wire formats:
- Public key: base64url-encoded DER SubjectPublicKeyInfo (Ed25519) — the
  ``MCowBQYDK2VwAyEA…`` shape from the ADR's handshake example.
- Nonce: the exact base64url string the server sent in the challenge frame
  (the agent signs the STRING bytes, not the decoded nonce bytes — one
  unambiguous byte sequence on both sides).
- Signature: base64url-encoded raw Ed25519 signature (64 bytes).

Signed payload: ``b"skuel-vault-agent-v1" || nonce`` — the domain-separation
prefix prevents cross-protocol signature reuse (ADR-075 Decision 3).
"""

from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

# Exact domain string from ADR-075 Decision 3. Never change without a
# protocol-version bump — enrolled agents sign this byte sequence.
AGENT_SIGNATURE_DOMAIN = b"skuel-vault-agent-v1"


def _b64url_decode(value: str) -> bytes | None:
    """Decode unpadded-or-padded base64url; None on malformed input."""
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except binascii.Error, ValueError, UnicodeEncodeError:
        return None


def decode_device_pubkey(pubkey_b64url: str) -> Ed25519PublicKey | None:
    """Parse a base64url DER-SPKI Ed25519 public key; None if malformed.

    Rejects any key that is not Ed25519 — the handshake never negotiates
    algorithms (no parameter footguns, ADR-075 Decision 2).
    """
    der = _b64url_decode(pubkey_b64url)
    if der is None:
        return None
    try:
        key = load_der_public_key(der)
    except ValueError, UnsupportedAlgorithm:
        return None
    if not isinstance(key, Ed25519PublicKey):
        return None
    return key


def build_signed_payload(nonce_b64url: str) -> bytes:
    """The exact byte string the agent must sign: domain prefix + nonce string."""
    return AGENT_SIGNATURE_DOMAIN + nonce_b64url.encode("ascii")


def verify_agent_signature(pubkey_b64url: str, nonce_b64url: str, signature_b64url: str) -> bool:
    """Verify the agent's Ed25519 signature over the domain-separated nonce.

    Returns False for ANY failure — malformed key, malformed signature, or
    signature mismatch — so callers emit one uniform ``device_not_enrolled``
    error (no oracle distinguishing the failure modes, ADR-075 Decision 3).
    """
    key = decode_device_pubkey(pubkey_b64url)
    if key is None:
        return False
    signature = _b64url_decode(signature_b64url)
    if signature is None:
        return False
    try:
        key.verify(signature, build_signed_payload(nonce_b64url))
    except InvalidSignature, ValueError:
        return False
    return True


__all__ = [
    "AGENT_SIGNATURE_DOMAIN",
    "build_signed_payload",
    "decode_device_pubkey",
    "verify_agent_signature",
]
