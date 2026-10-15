import dataclasses
import io
import json
import re
import urllib.error
from decimal import Decimal

import pytest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.system_program import CreateAccountParams, create_account
from solders.token import ID as TOKEN_PROGRAM_ID
from solders.token.state import TokenAccount
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

from demo.scenarios import CLEAN_SCENARIO, INJECTED_SCENARIO
from interlock import settlement, spl
from interlock.engine import authorize
from interlock.settlement import (
    DevnetConfig,
    JsonRpc,
    SettlementError,
    build_transfer,
    load_config,
    memo_text,
    settle,
    to_base_units,
)
from interlock.trace import Signer

AIRLINE = "merchant.airline.example"
AGENCY = "merchant.agency.example"


def _decision(scenario):
    return authorize(scenario.mandate, scenario.payment, scenario.spent, Signer.generate())


class LiteSvmRpc:
    """Runs transactions on an in-process Solana VM with the real SPL programs."""

    def __init__(self, svm):
        self.svm = svm

    def latest_blockhash(self):
        return self.svm.latest_blockhash()

    def send(self, tx):
        result = self.svm.send_transaction(tx)
        if isinstance(result, FailedTransactionMetadata):
            raise SettlementError(str(result.err))
        return str(tx.signatures[0])

    def is_confirmed(self, signature):
        return True


class FakeRpc:
    def __init__(self, send_errors=(), confirmed=True, confirm_error=None):
        self.send_errors = list(send_errors)
        self.confirmed = confirmed
        self.confirm_error = confirm_error
        self.blockhashes = 0

    def latest_blockhash(self):
        self.blockhashes += 1
        return Hash.default()

    def send(self, tx):
        if self.send_errors:
            raise SettlementError(self.send_errors.pop(0))
        return str(tx.signatures[0])

    def is_confirmed(self, signature):
        if self.confirm_error:
            raise SettlementError(self.confirm_error)
        return self.confirmed


class ExplodingRpc:
    def __getattr__(self, name):
        raise AssertionError("nothing may be sent for a denied decision")


def _offline_config():
    return DevnetConfig(
        treasury=Keypair(),
        mint=Keypair().pubkey(),
        decimals=6,
        merchants={AIRLINE: Keypair().pubkey(), AGENCY: Keypair().pubkey()},
    )


def _balance(svm, owner, mint):
    data = bytes(svm.get_account(spl.token_account(owner, mint)).data)
    return TokenAccount.from_bytes(data).amount


@pytest.fixture
def devnet():
    svm = LiteSVM()
    treasury, mint = Keypair(), Keypair()
    merchants = {AIRLINE: Keypair().pubkey(), AGENCY: Keypair().pubkey()}
    svm.airdrop(treasury.pubkey(), 10**10)
    rent = svm.minimum_balance_for_rent_exemption(spl.MINT_ACCOUNT_SIZE)
    ixs = [
        create_account(
            CreateAccountParams(
                from_pubkey=treasury.pubkey(),
                to_pubkey=mint.pubkey(),
                lamports=rent,
                space=spl.MINT_ACCOUNT_SIZE,
                owner=TOKEN_PROGRAM_ID,
            )
        ),
        spl.initialize_mint2(mint.pubkey(), 6, treasury.pubkey()),
        spl.create_token_account(treasury.pubkey(), treasury.pubkey(), mint.pubkey()),
    ]
    ixs += [spl.create_token_account(treasury.pubkey(), m, mint.pubkey()) for m in merchants.values()]
    ixs.append(
        spl.mint_to(
            mint.pubkey(),
            spl.token_account(treasury.pubkey(), mint.pubkey()),
            treasury.pubkey(),
            10**6 * 10**6,
        )
    )
    tx = Transaction([treasury, mint], Message(ixs, treasury.pubkey()), svm.latest_blockhash())
    assert not isinstance(svm.send_transaction(tx), FailedTransactionMetadata)
    return svm, DevnetConfig(treasury, mint.pubkey(), 6, merchants)


def test_allowed_decision_settles_on_chain(devnet):
    svm, config = devnet
    result = settle(_decision(CLEAN_SCENARIO), CLEAN_SCENARIO.payment, config, LiteSvmRpc(svm))
    assert result.status == "settled"
    assert result.explorer_url == (
        f"https://explorer.solana.com/tx/{result.signature}?cluster=devnet"
    )
    assert _balance(svm, config.merchants[AIRLINE], config.mint) == 540 * 10**6


def test_identical_decisions_settle_as_distinct_transactions(devnet):
    svm, config = devnet
    decision, rpc = _decision(CLEAN_SCENARIO), LiteSvmRpc(svm)
    first = settle(decision, CLEAN_SCENARIO.payment, config, rpc)
    second = settle(decision, CLEAN_SCENARIO.payment, config, rpc)
    assert first.status == second.status == "settled"
    assert first.signature != second.signature
    assert _balance(svm, config.merchants[AIRLINE], config.mint) == 1080 * 10**6


def test_denied_decision_is_never_sent():
    result = settle(
        _decision(INJECTED_SCENARIO), INJECTED_SCENARIO.payment, _offline_config(), ExplodingRpc()
    )
    assert result.status == "not_sent"


def test_missing_configuration_is_reported_not_faked():
    result = settle(_decision(CLEAN_SCENARIO), CLEAN_SCENARIO.payment, None, None)
    assert result.status == "not_configured"
    assert result.signature is None


def test_memo_ties_the_transfer_to_the_decision():
    decision = _decision(CLEAN_SCENARIO)
    text = memo_text(decision)
    assert re.fullmatch(
        rf"interlock {decision.payment_id} {decision.signature[:32]} [0-9a-f]{{8}}", text
    )
    tx = build_transfer(_offline_config(), AIRLINE, Decimal("540"), text, Hash.default())
    memo_ix = tx.message.instructions[1]
    assert tx.message.account_keys[memo_ix.program_id_index] == spl.MEMO_PROGRAM_ID
    assert bytes(memo_ix.data) == text.encode()


def test_unknown_recipient_fails_without_sending():
    payment = dataclasses.replace(CLEAN_SCENARIO.payment, recipient="merchant.unknown.example")
    decision = _decision(CLEAN_SCENARIO)
    result = settle(decision, payment, _offline_config(), FakeRpc())
    assert result.status == "failed"
    assert "no devnet address" in result.error


def test_rpc_error_is_reported_as_failed():
    result = settle(
        _decision(CLEAN_SCENARIO),
        CLEAN_SCENARIO.payment,
        _offline_config(),
        FakeRpc(send_errors=["node is behind"]),
    )
    assert result.status == "failed"
    assert result.error == "node is behind"


def test_expired_blockhash_is_retried_once():
    rpc = FakeRpc(send_errors=["Blockhash not found"])
    result = settle(_decision(CLEAN_SCENARIO), CLEAN_SCENARIO.payment, _offline_config(), rpc)
    assert result.status == "settled"
    assert rpc.blockhashes == 2


def test_slow_confirmation_is_unconfirmed_not_failed():
    ticks = iter([0.0, 0.0, 31.0])
    result = settle(
        _decision(CLEAN_SCENARIO),
        CLEAN_SCENARIO.payment,
        _offline_config(),
        FakeRpc(confirmed=False),
        sleep=lambda s: None,
        clock=lambda: next(ticks),
    )
    assert result.status == "unconfirmed"
    assert result.explorer_url is not None
    assert "not confirmed within 30s" in result.error


def test_on_chain_failure_is_reported_with_its_signature():
    result = settle(
        _decision(CLEAN_SCENARIO),
        CLEAN_SCENARIO.payment,
        _offline_config(),
        FakeRpc(confirm_error="transaction failed on chain: InsufficientFunds"),
    )
    assert result.status == "failed"
    assert result.signature is not None


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1"), Decimal("0.0000001")])
def test_amounts_that_cannot_be_settled_are_rejected(amount):
    with pytest.raises(SettlementError):
        to_base_units(amount, 6)


def test_to_base_units_scales_by_decimals():
    assert to_base_units(Decimal("540"), 6) == 540_000_000
    assert to_base_units(Decimal("0.5"), 6) == 500_000


def test_load_config_needs_both_file_and_key(tmp_path):
    treasury = Keypair()
    path = tmp_path / "devnet.json"
    path.write_text(
        json.dumps(
            {
                "treasury": str(treasury.pubkey()),
                "mint": str(Keypair().pubkey()),
                "decimals": 6,
                "merchants": {AIRLINE: str(Keypair().pubkey())},
            }
        )
    )
    assert load_config(path, env={}) is None
    assert load_config(tmp_path / "missing.json", env={"SOLANA_TREASURY_KEY": str(treasury)}) is None
    config = load_config(path, env={"SOLANA_TREASURY_KEY": f"  {treasury}  "})
    assert config.treasury.pubkey() == treasury.pubkey()
    with pytest.raises(ValueError):
        load_config(path, env={"SOLANA_TREASURY_KEY": str(Keypair())})


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_json_rpc_parses_results_and_errors(monkeypatch):
    sent = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data)
        sent.append(body["method"])
        if body["method"] == "getLatestBlockhash":
            result = {"value": {"blockhash": "11111111111111111111111111111111"}}
            return _Response(json.dumps({"result": result}).encode())
        if body["method"] == "getSignatureStatuses":
            result = {"value": [{"err": None, "confirmationStatus": "confirmed"}]}
            return _Response(json.dumps({"result": result}).encode())
        return _Response(json.dumps({"error": {"message": "Blockhash not found"}}).encode())

    monkeypatch.setattr(settlement.urllib.request, "urlopen", fake_urlopen)
    rpc = JsonRpc("http://rpc.test")
    assert str(rpc.latest_blockhash()) == "11111111111111111111111111111111"
    assert rpc.is_confirmed("sig") is True
    with pytest.raises(SettlementError, match="Blockhash not found"):
        rpc.send(build_transfer(_offline_config(), AIRLINE, Decimal("1"), "m", Hash.default()))
    assert sent == ["getLatestBlockhash", "getSignatureStatuses", "sendTransaction"]


def test_json_rpc_wraps_network_errors(monkeypatch):
    def down(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(settlement.urllib.request, "urlopen", down)
    with pytest.raises(SettlementError, match="devnet RPC"):
        JsonRpc("http://rpc.test").latest_blockhash()


def test_json_rpc_reports_pending_and_failed_statuses(monkeypatch):
    statuses = iter([None, {"err": {"InstructionError": [0, "Custom"]}}])

    def fake_urlopen(request, timeout):
        return _Response(json.dumps({"result": {"value": [next(statuses)]}}).encode())

    monkeypatch.setattr(settlement.urllib.request, "urlopen", fake_urlopen)
    rpc = JsonRpc("http://rpc.test")
    assert rpc.is_confirmed("sig") is False
    with pytest.raises(SettlementError, match="failed on chain"):
        rpc.is_confirmed("sig")
