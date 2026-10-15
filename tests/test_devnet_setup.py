from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.token.state import TokenAccount
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

from interlock import spl
from interlock.settlement import load_config
from scripts.devnet_setup import (
    DECIMALS,
    MERCHANTS,
    SUPPLY,
    setup_instructions,
    write_config,
)


def test_setup_creates_mint_accounts_and_supply():
    svm = LiteSVM()
    treasury, mint = Keypair(), Keypair()
    merchants = {name: Keypair().pubkey() for name in MERCHANTS}
    svm.airdrop(treasury.pubkey(), 10**10)
    rent = svm.minimum_balance_for_rent_exemption(spl.MINT_ACCOUNT_SIZE)
    ixs = setup_instructions(treasury.pubkey(), mint.pubkey(), merchants, rent)
    tx = Transaction([treasury, mint], Message(ixs, treasury.pubkey()), svm.latest_blockhash())
    assert not isinstance(svm.send_transaction(tx), FailedTransactionMetadata)

    def balance(owner):
        data = bytes(svm.get_account(spl.token_account(owner, mint.pubkey())).data)
        return TokenAccount.from_bytes(data).amount

    assert balance(treasury.pubkey()) == SUPPLY
    assert all(balance(owner) == 0 for owner in merchants.values())


def test_written_config_loads_back(tmp_path):
    treasury, mint = Keypair(), Keypair().pubkey()
    merchants = {name: Keypair().pubkey() for name in MERCHANTS}
    path = tmp_path / "devnet.json"
    write_config(path, treasury.pubkey(), mint, merchants)
    config = load_config(path, env={"SOLANA_TREASURY_KEY": str(treasury)})
    assert config.mint == mint
    assert config.decimals == DECIMALS
    assert config.merchants == merchants
