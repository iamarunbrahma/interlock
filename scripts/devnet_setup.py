"""One-off devnet setup: treasury, test token, merchant token accounts.

Usage, from the repo root:

    python -m scripts.devnet_setup

Reuses SOLANA_TREASURY_KEY if set, otherwise creates a treasury and prints its key.
Airdrops devnet SOL if the treasury is low, creates a 6-decimal test mint (devnet
test USDC - not real USDC), token accounts for the treasury and both demo merchants,
mints the supply to the treasury and writes interlock/devnet.json.

The merchants' private keys are discarded: they only ever receive.
"""

import json
import os
import sys
import time
from pathlib import Path

from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import CreateAccountParams, create_account
from solders.token import ID as TOKEN_PROGRAM_ID
from solders.transaction import Transaction

from interlock import spl
from interlock.settlement import CONFIG_PATH, DEFAULT_RPC_URL, JsonRpc, SettlementError

DECIMALS = 6
SUPPLY = 1_000_000_000 * 10**DECIMALS
MERCHANTS = ("merchant.airline.example", "merchant.agency.example")
MIN_LAMPORTS = 50_000_000  # 0.05 SOL: rent for the mint and three token accounts, plus fees
AIRDROP_LAMPORTS = 1_000_000_000


def setup_instructions(
    treasury: Pubkey, mint: Pubkey, merchants: dict[str, Pubkey], mint_rent: int
) -> list:
    instructions = [
        create_account(
            CreateAccountParams(
                from_pubkey=treasury,
                to_pubkey=mint,
                lamports=mint_rent,
                space=spl.MINT_ACCOUNT_SIZE,
                owner=TOKEN_PROGRAM_ID,
            )
        ),
        spl.initialize_mint2(mint, DECIMALS, treasury),
        spl.create_token_account(treasury, treasury, mint),
    ]
    instructions += [spl.create_token_account(treasury, owner, mint) for owner in merchants.values()]
    instructions.append(spl.mint_to(mint, spl.token_account(treasury, mint), treasury, SUPPLY))
    return instructions


def write_config(path: Path, treasury: Pubkey, mint: Pubkey, merchants: dict[str, Pubkey]) -> None:
    data = {
        "treasury": str(treasury),
        "mint": str(mint),
        "decimals": DECIMALS,
        "merchants": {name: str(owner) for name, owner in merchants.items()},
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


def _balance(rpc: JsonRpc, owner: Pubkey) -> int:
    return rpc.call("getBalance", [str(owner), {"commitment": "confirmed"}])["value"]


def _fund(rpc: JsonRpc, treasury: Keypair) -> None:
    if _balance(rpc, treasury.pubkey()) >= MIN_LAMPORTS:
        return
    print(f"requesting a devnet airdrop for {treasury.pubkey()} ...")
    rpc.call("requestAirdrop", [str(treasury.pubkey()), AIRDROP_LAMPORTS])
    for _ in range(30):
        time.sleep(2)
        if _balance(rpc, treasury.pubkey()) >= MIN_LAMPORTS:
            return
    raise SettlementError("airdrop did not arrive within 60s")


def main() -> int:
    rpc = JsonRpc(os.environ.get("SOLANA_RPC_URL", DEFAULT_RPC_URL))
    existing = os.environ.get("SOLANA_TREASURY_KEY", "").strip()
    treasury = Keypair.from_base58_string(existing) if existing else Keypair()
    if not existing:
        print(f"new treasury {treasury.pubkey()}")
        print(f"SOLANA_TREASURY_KEY={treasury}")

    try:
        _fund(rpc, treasury)
    except SettlementError as exc:
        print(
            f"airdrop failed ({exc}). Fund {treasury.pubkey()} with devnet SOL at "
            "https://faucet.solana.com, then rerun with SOLANA_TREASURY_KEY set to the "
            "key printed above."
        )
        return 1

    mint = Keypair()
    merchants = {name: Keypair().pubkey() for name in MERCHANTS}
    rent = rpc.call("getMinimumBalanceForRentExemption", [spl.MINT_ACCOUNT_SIZE])
    instructions = setup_instructions(treasury.pubkey(), mint.pubkey(), merchants, rent)
    tx = Transaction(
        [treasury, mint], Message(instructions, treasury.pubkey()), rpc.latest_blockhash()
    )
    signature = rpc.send(tx)
    for _ in range(30):
        if rpc.is_confirmed(signature):
            break
        time.sleep(1)
    else:
        print(f"setup transaction {signature} did not confirm; check it on the explorer")
        return 1

    write_config(CONFIG_PATH, treasury.pubkey(), mint.pubkey(), merchants)
    print(f"setup transaction {signature}")
    print(f"wrote {CONFIG_PATH}")
    print(f"SOLANA_TREASURY_KEY={treasury}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
