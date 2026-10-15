"""SPL Token, Associated Token Account and Memo instructions.

solders ships the primitives but no SPL instruction builders, so the handful this
project needs are encoded here. Layouts follow the SPL Token instruction enum:
MintTo = 7, TransferChecked = 12, InitializeMint2 = 20. Amounts are u64 little-endian.
"""

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solders.token import ID as TOKEN_PROGRAM_ID
from solders.token.associated import get_associated_token_address

ATA_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
MINT_ACCOUNT_SIZE = 82


def token_account(owner: Pubkey, mint: Pubkey) -> Pubkey:
    """The owner's associated token account for this mint."""
    return get_associated_token_address(owner, mint)


def initialize_mint2(mint: Pubkey, decimals: int, authority: Pubkey) -> Instruction:
    data = bytes([20, decimals]) + bytes(authority) + bytes([0])  # no freeze authority
    return Instruction(TOKEN_PROGRAM_ID, data, [AccountMeta(mint, False, True)])


def create_token_account(payer: Pubkey, owner: Pubkey, mint: Pubkey) -> Instruction:
    """Create the owner's associated token account; a no-op if it already exists."""
    return Instruction(
        ATA_PROGRAM_ID,
        bytes([1]),  # CreateIdempotent
        [
            AccountMeta(payer, True, True),
            AccountMeta(token_account(owner, mint), False, True),
            AccountMeta(owner, False, False),
            AccountMeta(mint, False, False),
            AccountMeta(SYSTEM_PROGRAM_ID, False, False),
            AccountMeta(TOKEN_PROGRAM_ID, False, False),
        ],
    )


def mint_to(mint: Pubkey, destination: Pubkey, authority: Pubkey, amount: int) -> Instruction:
    return Instruction(
        TOKEN_PROGRAM_ID,
        bytes([7]) + amount.to_bytes(8, "little"),
        [
            AccountMeta(mint, False, True),
            AccountMeta(destination, False, True),
            AccountMeta(authority, True, False),
        ],
    )


def transfer_checked(
    source: Pubkey,
    mint: Pubkey,
    destination: Pubkey,
    owner: Pubkey,
    amount: int,
    decimals: int,
) -> Instruction:
    return Instruction(
        TOKEN_PROGRAM_ID,
        bytes([12]) + amount.to_bytes(8, "little") + bytes([decimals]),
        [
            AccountMeta(source, False, True),
            AccountMeta(mint, False, False),
            AccountMeta(destination, False, True),
            AccountMeta(owner, True, False),
        ],
    )


def memo(text: str, signer: Pubkey) -> Instruction:
    return Instruction(MEMO_PROGRAM_ID, text.encode(), [AccountMeta(signer, True, False)])
