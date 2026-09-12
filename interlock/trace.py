import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .models import CheckResult


def canonical_payload(
    payment_id: str,
    allowed: bool,
    checks: tuple[CheckResult, ...],
    issued_at: str,
) -> dict:
    """Deterministic dict for signing.

    Checks are sorted by name so that ordering cannot change the signature.
    """
    return {
        "payment_id": payment_id,
        "allowed": allowed,
        "issued_at": issued_at,
        "checks": sorted(
            ({"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks),
            key=lambda c: c["name"],
        ),
    }


def _encode(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class Signer:
    """Ed25519 signer - the same curve Solana uses for account keys."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key

    @classmethod
    def generate(cls) -> "Signer":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_hex(cls, private_key_hex: str) -> "Signer":
        return cls(Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex)))

    @property
    def private_key_hex(self) -> str:
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()

    @property
    def public_key_hex(self) -> str:
        return (
            self._private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            .hex()
        )

    def sign(self, payload: dict) -> str:
        return self._private_key.sign(_encode(payload)).hex()


def verify(payload: dict, signature_hex: str, public_key_hex: str) -> bool:
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    try:
        public_key.verify(bytes.fromhex(signature_hex), _encode(payload))
    except InvalidSignature:
        return False
    return True
