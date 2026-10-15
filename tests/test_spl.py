import pytest
from solders.keypair import Keypair
from solders.litesvm import LiteSVM
from solders.message import Message
from solders.system_program import CreateAccountParams, create_account
from solders.token import ID as TOKEN_PROGRAM_ID
from solders.token.state import TokenAccount
from solders.transaction import Transaction
from solders.transaction_metadata import FailedTransactionMetadata

from interlock import spl


def _send(svm, signers, instructions):
    tx = Transaction(
        signers, Message(instructions, signers[0].pubkey()), svm.latest_blockhash()
    )
    result = svm.send_transaction(tx)
    assert not isinstance(result, FailedTransactionMetadata), result
    return result


def _balance(svm, owner, mint):
    data = bytes(svm.get_account(spl.token_account(owner, mint)).data)
    return TokenAccount.from_bytes(data).amount


@pytest.fixture
def chain():
    svm = LiteSVM()
    payer, mint, merchant = Keypair(), Keypair(), Keypair()
    svm.airdrop(payer.pubkey(), 10**10)
    rent = svm.minimum_balance_for_rent_exemption(spl.MINT_ACCOUNT_SIZE)
    _send(
        svm,
        [payer, mint],
        [
            create_account(
                CreateAccountParams(
                    from_pubkey=payer.pubkey(),
                    to_pubkey=mint.pubkey(),
                    lamports=rent,
                    space=spl.MINT_ACCOUNT_SIZE,
                    owner=TOKEN_PROGRAM_ID,
                )
            ),
            spl.initialize_mint2(mint.pubkey(), 6, payer.pubkey()),
            spl.create_token_account(payer.pubkey(), payer.pubkey(), mint.pubkey()),
            spl.create_token_account(payer.pubkey(), merchant.pubkey(), mint.pubkey()),
            spl.mint_to(
                mint.pubkey(),
                spl.token_account(payer.pubkey(), mint.pubkey()),
                payer.pubkey(),
                1_000 * 10**6,
            ),
        ],
    )
    return svm, payer, mint.pubkey(), merchant.pubkey()


def test_setup_mints_the_supply_to_the_payer(chain):
    svm, payer, mint, _ = chain
    assert _balance(svm, payer.pubkey(), mint) == 1_000 * 10**6


def test_transfer_checked_moves_tokens_and_the_memo_is_logged(chain):
    svm, payer, mint, merchant = chain
    result = _send(
        svm,
        [payer],
        [
            spl.transfer_checked(
                spl.token_account(payer.pubkey(), mint),
                mint,
                spl.token_account(merchant, mint),
                payer.pubkey(),
                540 * 10**6,
                6,
            ),
            spl.memo("interlock pay_1 abc", payer.pubkey()),
        ],
    )
    assert _balance(svm, merchant, mint) == 540 * 10**6
    assert any("interlock pay_1 abc" in line for line in result.logs())


def test_transfer_checked_rejects_the_wrong_decimals(chain):
    svm, payer, mint, merchant = chain
    ix = spl.transfer_checked(
        spl.token_account(payer.pubkey(), mint),
        mint,
        spl.token_account(merchant, mint),
        payer.pubkey(),
        540,
        9,
    )
    tx = Transaction([payer], Message([ix], payer.pubkey()), svm.latest_blockhash())
    assert isinstance(svm.send_transaction(tx), FailedTransactionMetadata)


def test_create_token_account_is_idempotent(chain):
    svm, payer, mint, merchant = chain
    _send(svm, [payer], [spl.create_token_account(payer.pubkey(), merchant, mint)])
