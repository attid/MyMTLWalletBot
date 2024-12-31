import asyncio
from pprint import pprint

from pytonapi import Tonapi
from pytoniq_core import Address
from tonutils.client import TonapiClient
from tonutils.utils import to_amount
from tonutils.wallet import (
    WalletV5R1,
)
from utils.config_reader import config

# API key for accessing the Tonapi (obtainable from https://tonconsole.com)
API_KEY = config.tonconsole_token

# Set to True for test network, False for main network
IS_TESTNET = False


async def main() -> None:
    client = TonapiClient(api_key=API_KEY, is_testnet=IS_TESTNET)
    mnemonic = config.ton_token
    wallet, public_key, private_key, mnemonic = WalletV5R1.from_mnemonic(client, mnemonic)

    tonapi = Tonapi(api_key=API_KEY)
    account = tonapi.accounts.get_info(account_id=wallet.address.to_str())

    print(f"Raw form: {account.address.to_raw()}")
    # output: 0:bede2955afe5b451cde92eb189125c12685c6f8575df922400dc4c1d5411cd35

    print(f"User-friendly: {account.address.to_userfriendly()}")
    # output: UQC-3ilVr-W0Uc3pLrGJElwSaFxvhXXfkiQA3EwdVBHNNbbp

    print(f"User-friendly (bounceable): {account.address.to_userfriendly(is_bounceable=True)}")
    # output: EQC-3ilVr-W0Uc3pLrGJElwSaFxvhXXfkiQA3EwdVBHNNess

    print(f"Balance nanoton: {account.balance.to_nano()}")
    # output: 1500000000

    print(f"Balance TON: {account.balance.to_amount(precision=5)}")
    # output: 1.5
    USDT_MASTER_ADDRESS = Address("EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs")

    # Получаем баланс USDT
    usdt_balance = tonapi.accounts.get_jetton_balance(
        account_id=wallet.address.to_str(),
        jetton_id=USDT_MASTER_ADDRESS.to_str()
    )

    print(f"USDT Balance: {to_amount(int(usdt_balance.balance), decimals=6 )}")


import asyncio
from pytoniq import LiteClient, MessageAny, LiteBalancer, WalletV4R2


async def main0():
    client = LiteBalancer.from_mainnet_config(trust_level=1)

    await client.start_up()

    """wallet seqno"""
    result = await client.run_get_method(address='EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG', method='seqno', stack=[])
    print(result)  # [242]
    wallet = await WalletV4R2.from_address(provider=client, address='EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG')
    print(wallet.seqno)  # 242
    print(await wallet.get_seqno())  # 242
    print(await wallet.run_get_method(method='seqno', stack=[]))  # [242]

    """dex router get method"""
    result = await client.run_get_method(address='EQB3ncyBUTjZUA5EnFKR5_EnOMI9V1tTEAAPaiU71gc4TiUt', method='get_router_data', stack=[])
    print(result)  # [0, <Slice 267[80093377825F7267A94C4EF8966051F874BF125171483071FC33E1E05EBFF4DF6E00] -> 0 refs>, <Cell 130[0000000000000000000000000000000000] -> 1 refs>, <Cell 80[FF00F4A413F4BCF2C80B] -> 1 refs>, <Cell 80[FF00F4A413F4BCF2C80B] -> 1 refs>, <Cell 80[FF00F4A413F4BCF2C80B] -> 1 refs>]
    print(result[1].load_address())  # EQBJm7wS-5M9SmJ3xLMCj8Ol-JKLikGDj-GfDwL1_6b7cENC

    """jetton wallets"""
    owner_address = Address('EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG')
    request_stack = [owner_address.to_cell().begin_parse()]
    result = await client.run_get_method(address='EQBynBO23ywHy_CgarY9NK9FTz0yDsG82PtcbSTQgGoXwiuA', method='get_wallet_address', stack=request_stack)
    print(result)   # [<Slice 267[801B54D587424F634D8AC9DC74071390A2EBDA9F0410E4F19F734DD133C9F136F4A0] -> 0 refs>]
    jetton_wallet_address = result[0].load_address()
    print(jetton_wallet_address)  # EQDapqw6EnsabFZO46A4nIUXXtT4IIcnjPuabomeT4m3paST

    result = await client.run_get_method(address='EQDapqw6EnsabFZO46A4nIUXXtT4IIcnjPuabomeT4m3paST', method='get_wallet_data', stack=[])
    print(result)  # [2005472, <Slice 267[800DEB78CF30DC0C8612C3B3BE0086724D499B25CB2FBBB154C086C8B58417A2F040] -> 0 refs>, <Slice 267[800E538276DBE580F97E140D56C7A695E8A9E7A641D8379B1F6B8DA49A100D42F840] -> 0 refs>, <Cell 80[FF00F4A413F4BCF2C80B] -> 1 refs>]

    await client.close_all()

    """can run get method for any block liteserver remembers"""
    client = LiteClient.from_mainnet_config(2, 2)  # archive liteserver
    await client.connect()
    blk, _ = await client.lookup_block(wc=0, shard=-2**63, seqno=33000000)
    result = await client.run_get_method(address='EQBvW8Z5huBkMJYdnfAEM5JqTNkuWX3diqYENkWsIL0XggGG', method='seqno', stack=[], block=blk)
    await client.close()
    print(result)


if __name__ == '__main__':
    asyncio.run(main0())

