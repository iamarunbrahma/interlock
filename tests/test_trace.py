from interlock.models import CheckResult
from interlock.trace import Signer, canonical_payload, verify


def test_signature_verifies_against_public_key():
    signer = Signer.generate()
    payload = canonical_payload(
        "p_1", True, (CheckResult("amount", True, "ok"),), "2026-09-13T00:00:00Z"
    )
    assert verify(payload, signer.sign(payload), signer.public_key_hex)


def test_tampered_payload_fails_verification():
    signer = Signer.generate()
    payload = canonical_payload(
        "p_1", False, (CheckResult("amount", False, "over cap"),), "2026-09-13T00:00:00Z"
    )
    signature = signer.sign(payload)
    payload["allowed"] = True
    assert not verify(payload, signature, signer.public_key_hex)


def test_canonical_payload_is_order_independent():
    checks = (CheckResult("b", True, "x"), CheckResult("a", True, "y"))
    one = canonical_payload("p_1", True, checks, "2026-09-13T00:00:00Z")
    two = canonical_payload("p_1", True, tuple(reversed(checks)), "2026-09-13T00:00:00Z")
    assert one == two


def test_signer_round_trips_through_hex():
    signer = Signer.generate()
    assert Signer.from_hex(signer.private_key_hex).public_key_hex == signer.public_key_hex


def test_wrong_public_key_fails_verification():
    signer, other = Signer.generate(), Signer.generate()
    payload = canonical_payload("p_1", True, (), "2026-09-13T00:00:00Z")
    assert not verify(payload, signer.sign(payload), other.public_key_hex)
