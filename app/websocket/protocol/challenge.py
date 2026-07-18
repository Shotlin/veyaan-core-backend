"""
Ed25519 challenge-response authentication for WebSocket device connections.

Flow:
  1. Device connects (no secret in URL)
  2. Server generates a random nonce, stores it in Valkey with 30s TTL
  3. Server sends {"type": "auth_challenge", "nonce": "<hex>"}
  4. Device signs nonce with its Ed25519 private key, responds:
     {"type": "auth_response", "device_id": "...", "signature": "<base64>", "protocol_version": "v1", "app_version": "..."}
  5. Server verifies signature against stored public key from DB
  6. Nonce is immediately deleted from Valkey (consumed once)
"""

import base64
import os
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.cache import valkey_client

_CHALLENGE_TTL = 30  # seconds


def _challenge_key(nonce: str) -> str:
    return f"ws:challenge:{nonce}"


async def generate_challenge() -> str:
    """Generate a 32-byte random hex nonce and store it in Valkey."""
    nonce = os.urandom(32).hex()
    await valkey_client.set(_challenge_key(nonce), "1", ttl=_CHALLENGE_TTL)
    return nonce


async def consume_challenge(nonce: str) -> bool:
    """
    Consume the challenge nonce — returns True if it existed and deletes it.
    A nonce can only be consumed once (replay protection).
    """
    key = _challenge_key(nonce)
    exists = await valkey_client.exists(key)
    if not exists:
        return False
    await valkey_client.delete(key)
    return True


def build_challenge_message(
    device_id: UUID,
    connection_id: UUID,
    nonce: str,
    server_time_iso: str,
    protocol_version: str,
    app_version: str,
) -> bytes:
    """Build the canonical byte sequence for Ed25519 signature."""
    msg_str = (
        f"{device_id}:{connection_id}:{nonce}:{server_time_iso}:{protocol_version}:{app_version}"
    )
    return msg_str.encode("utf-8")


def verify_ed25519_signature(
    public_key_b64: str,
    message: bytes,
    signature_b64: str,
) -> bool:
    """
    Verify an Ed25519 signature of the canonical message.

    Args:
        public_key_b64: Base64-encoded Ed25519 public key (from device registration)
        message: The canonical byte sequence message that was signed
        signature_b64: Base64-encoded signature produced by the device's private key

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        signature_bytes = base64.b64decode(signature_b64)
        public_key.verify(signature_bytes, message)
        return True
    except (InvalidSignature, Exception):
        return False


async def verify_device_challenge_response(
    device_id: UUID,
    connection_id: UUID,
    nonce: str,
    server_time_iso: str,
    signature_b64: str,
    public_key_b64: str,
    protocol_version: str,
    app_version: str,
) -> tuple[bool, str]:
    """
    Full challenge-response verification:
      1. Consume nonce (checks it exists + is fresh, deletes it)
      2. Reconstruct message
      3. Verify Ed25519 signature

    Returns (success, error_message)
    """
    nonce_valid = await consume_challenge(nonce)
    if not nonce_valid:
        return False, "Challenge nonce invalid or expired"

    message = build_challenge_message(
        device_id=device_id,
        connection_id=connection_id,
        nonce=nonce,
        server_time_iso=server_time_iso,
        protocol_version=protocol_version,
        app_version=app_version,
    )

    if not verify_ed25519_signature(public_key_b64, message, signature_b64):
        return False, "Invalid device signature"

    return True, ""
