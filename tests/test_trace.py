from interlock.models import CheckResult
from interlock.trace import Signer, canonical_payload, payload_from_decision, verify


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


def test_payload_without_payment_has_no_payment_key():
    payload = canonical_payload("p_1", True, (), "2026-09-13T00:00:00Z")
    assert "payment" not in payload


def test_payload_from_decision_rebuilds_the_signed_payload():
    signer = Signer.generate()
    checks = (CheckResult("amount", True, "ok"),)
    terms = {"recipient": "m", "amount": "1", "currency": "USDC", "chain": "solana"}
    payload = canonical_payload("p_1", True, checks, "2026-09-13T00:00:00Z", terms)
    body = {
        "payment_id": "p_1",
        "allowed": True,
        "issued_at": "2026-09-13T00:00:00Z",
        "checks": [{"name": "amount", "passed": True, "detail": "ok"}],
        "payment": terms,
    }
    assert payload_from_decision(body) == payload
    assert verify(payload_from_decision(body), signer.sign(payload), signer.public_key_hex)
