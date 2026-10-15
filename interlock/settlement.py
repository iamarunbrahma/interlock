"""Settle an allowed decision on Solana devnet.

One transaction: an SPL TransferChecked from the treasury's token account to the
merchant's, plus a Memo that ties the transfer to the signed decision. Nothing is
sent for a denied decision, and nothing is reported settled unless devnet says so.
"""

import base64
import json
import os
import secrets
import time
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from . import spl
from .engine import payment_terms
from .models import PaymentRequest
from .trace import canonical_payload, verify

DEFAULT_RPC_URL = "https://api.devnet.solana.com"
CONFIG_PATH = Path(__file__).with_name("devnet.json")
CONFIRM_TIMEOUT_S = 30.0


class SettlementError(Exception):
    pass


class TransportError(SettlementError):
    """The RPC could not be reached or refused the request. Says nothing about
    whether a transaction already sent will land."""


@dataclass(frozen=True)
class DevnetConfig:
    treasury: Keypair
    mint: Pubkey
    decimals: int
    merchants: dict[str, Pubkey]
    authority: str  # public key (hex) of the Interlock signer whose allow moves funds


@dataclass(frozen=True)
class Settlement:
    status: str  # settled | unconfirmed | failed | not_sent | not_configured
    signature: str | None = None
    explorer_url: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "signature": self.signature,
            "explorer_url": self.explorer_url,
            "error": self.error,
        }


class Rpc(Protocol):
    def latest_blockhash(self) -> Hash: ...

    def send(self, tx: Transaction) -> str: ...

    def is_confirmed(self, signature: str) -> bool: ...


class JsonRpc:
    """Minimal Solana JSON-RPC client over urllib - no SDK on the request path."""

    def __init__(self, url: str = DEFAULT_RPC_URL, timeout: float = 10.0):
        self._url = url
        self._timeout = timeout

    def call(self, method: str, params: list):
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode()
        request = urllib.request.Request(
            self._url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                data = json.loads(response.read())
        except (OSError, ValueError) as exc:
            raise TransportError(f"devnet RPC error: {exc}") from exc
        if "error" in data:
            error = data["error"]
            raise SettlementError(error.get("message", str(error)))
        return data["result"]

    def latest_blockhash(self) -> Hash:
        result = self.call("getLatestBlockhash", [{"commitment": "confirmed"}])
        return Hash.from_string(result["value"]["blockhash"])

    def send(self, tx: Transaction) -> str:
        encoded = base64.b64encode(bytes(tx)).decode()
        return self.call(
            "sendTransaction",
            [encoded, {"encoding": "base64", "preflightCommitment": "confirmed"}],
        )

    def is_confirmed(self, signature: str) -> bool:
        status = self.call("getSignatureStatuses", [[signature]])["value"][0]
        if status is None:
            return False
        if status.get("err"):
            raise SettlementError(f"transaction failed on chain: {status['err']}")
        return status.get("confirmationStatus") in ("confirmed", "finalized")


def load_config(
    path: Path = CONFIG_PATH, env=os.environ, *, authority: str
) -> DevnetConfig | None:
    """Devnet config from the committed addresses plus the treasury key, or None.

    `authority` is the public key whose signed allow decisions may move funds.
    """
    key = env.get("SOLANA_TREASURY_KEY", "").strip()
    if not key or not path.exists():
        return None
    data = json.loads(path.read_text())
    treasury = Keypair.from_base58_string(key)
    if str(treasury.pubkey()) != data["treasury"]:
        raise ValueError("SOLANA_TREASURY_KEY does not match the treasury in devnet.json")
    return DevnetConfig(
        treasury=treasury,
        mint=Pubkey.from_string(data["mint"]),
        decimals=int(data["decimals"]),
        merchants={name: Pubkey.from_string(a) for name, a in data["merchants"].items()},
        authority=authority,
    )


def explorer_url(signature: str) -> str:
    return f"https://explorer.solana.com/tx/{signature}?cluster=devnet"


def to_base_units(amount: Decimal, decimals: int) -> int:
    scaled = amount * (10**decimals)
    if scaled <= 0 or scaled != scaled.to_integral_value():
        raise SettlementError(f"cannot settle {amount} with {decimals} decimals")
    return int(scaled)


def memo_text(decision) -> str:
    """Payment id and signature prefix tie the transfer to its decision; the nonce
    keeps two identical decisions from producing byte-identical transactions."""
    return (
        f"interlock {decision.payment_id} {decision.signature[:32]} "
        f"{secrets.token_hex(4)}"
    )


def build_transfer(
    config: DevnetConfig, recipient: str, amount: Decimal, memo: str, blockhash: Hash
) -> Transaction:
    merchant = config.merchants.get(recipient)
    if merchant is None:
        raise SettlementError(f"no devnet address for {recipient}")
    owner = config.treasury.pubkey()
    instructions = [
        spl.transfer_checked(
            spl.token_account(owner, config.mint),
            config.mint,
            spl.token_account(merchant, config.mint),
            owner,
            to_base_units(amount, config.decimals),
            config.decimals,
        ),
        spl.memo(memo, owner),
    ]
    return Transaction([config.treasury], Message(instructions, owner), blockhash)


def _refusal(decision, payment: PaymentRequest, authority: str) -> str | None:
    """Funds move only for an allow decision Interlock signed over exactly these terms."""
    if decision.public_key != authority:
        return "refused: the decision was not signed by this deployment's Interlock key"
    if decision.payment_id != payment.payment_id or decision.payment != payment_terms(payment):
        return "refused: the payment does not match the terms the decision approved"
    payload = canonical_payload(
        decision.payment_id, decision.allowed, decision.checks, decision.issued_at, decision.payment
    )
    if not verify(payload, decision.signature, authority):
        return "refused: the decision's signature does not verify"
    return None


def _send(config: DevnetConfig, payment: PaymentRequest, memo: str, rpc: Rpc) -> str:
    for attempt in (1, 2):
        tx = build_transfer(config, payment.recipient, payment.amount, memo, rpc.latest_blockhash())
        try:
            return rpc.send(tx)
        except SettlementError as exc:
            if attempt == 2 or "blockhash not found" not in str(exc).lower():
                raise
    raise AssertionError("unreachable")


def settle(
    decision,
    payment: PaymentRequest,
    config: DevnetConfig | None,
    rpc: Rpc | None,
    *,
    timeout: float = CONFIRM_TIMEOUT_S,
    poll: float = 1.0,
    sleep=time.sleep,
    clock=time.monotonic,
) -> Settlement:
    if not decision.allowed:
        return Settlement("not_sent")
    if config is None or rpc is None:
        return Settlement("not_configured", error="devnet settlement is not configured")
    refusal = _refusal(decision, payment, config.authority)
    if refusal:
        return Settlement("failed", error=refusal)

    try:
        signature = _send(config, payment, memo_text(decision), rpc)
    except SettlementError as exc:
        return Settlement("failed", error=str(exc))

    url = explorer_url(signature)
    deadline = clock() + timeout
    last_transport_error = None
    while True:
        try:
            if rpc.is_confirmed(signature):
                return Settlement("settled", signature, url)
        except TransportError as exc:  # broadcast already; keep asking until the deadline
            last_transport_error = str(exc)
        except SettlementError as exc:  # the chain itself reported a failure
            return Settlement("failed", signature, url, str(exc))
        if clock() >= deadline:
            detail = f"not confirmed within {int(timeout)}s"
            if last_transport_error:
                detail += f" ({last_transport_error})"
            return Settlement("unconfirmed", signature, url, detail)
        sleep(poll)
