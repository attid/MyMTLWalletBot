from contextlib import suppress
import asyncio
import base58
import requests
from tronpy import Tron, AsyncTron, exceptions
from tronpy.keys import PrivateKey, is_address
from tronpy.providers import HTTPProvider, AsyncHTTPProvider
from config_reader import config
from utils.aiogram_utils import get_web_request

# api_key from https://www.trongrid.io
api_key = config.tron_api_key.get_secret_value()
tron_master_address = config.tron_master_address
tron_master_key = config.tron_master_key.get_secret_value()
usdt_contract = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
usdt_hex_contract = '41a614f803b6fd780986a42c78ec9c7f77e6ded13c'


def create_trc_private_key():
    private_key = PrivateKey.random()
    # print("Private Key is ", private_key)
    # account = private_key.public_key.to_base58check_address()
    # print("Account Address is ", account)
    return private_key.hex()


def show_balance(public_key):
    from tronpy import Tron
    from tronpy.providers import HTTPProvider

    client = Tron(HTTPProvider(api_key=api_key))  # Use mainnet(trongrid) with a single api_key

    s = client.get_account_balance(public_key)
    print('TRX=', s)

    cntr = client.get_contract(usdt_contract)
    print('USDT=', cntr.functions.balanceOf(public_key) / 1000000)


def send_usdt(public_key_to, amount, private_key_from):
    client = Tron(HTTPProvider(api_key=api_key))

    contract = client.get_contract(usdt_contract)
    private_key = PrivateKey(bytes.fromhex(private_key_from))
    public_key_from = private_key.public_key.to_base58check_address()

    txn = (
        contract.functions.transfer(public_key_to, amount * 10 ** 6)
        .with_owner(public_key_from)
        .fee_limit(20_000_000)
        # .memo("test memo")
        .build()
        .sign(private_key)
    )

    print(txn.txid)
    print(txn.broadcast().wait())


def send_trx(public_key_to, amount, private_key_from):
    client = Tron(HTTPProvider(api_key=api_key))
    private_key = PrivateKey(bytes.fromhex(private_key_from))
    public_key_from = private_key.public_key.to_base58check_address()

    txn = (
        client.trx.transfer(public_key_from, public_key_to, amount * 10 ** 6)
        # .memo("test memo")
        .build()
        .sign(private_key)
    )
    print(txn.txid)
    print(txn.broadcast().wait())


def get_transactions(address, limit=10):
    api_url = f"https://api.trongrid.io/v1/accounts/{address}/transactions?limit={limit}&only_confirmed=true"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()
        transactions = data["data"]

        # Получение текущего номера блока
        client = Tron(HTTPProvider(api_key=api_key))
        current_block = client.get_latest_block_number()

        print(transactions)

        for txn in transactions:
            # Получение номера блока, в котором была включена транзакция
            block_number = txn.get("blockNumber")

            # Если поле blockNumber отсутствует, пропустить эту транзакцию
            if block_number is None:
                continue

            # Вычисление количества подтверждений
            confirmations = current_block - block_number

            print(f"Transaction ID: {txn['txID']}")
            print(f"From: {txn['raw_data']['contract'][0]['parameter']['value']['owner_address']}")
            print(f"To: {txn['raw_data']['contract'][0]['parameter']['value']['to_address']}")
            print(f"Amount: {txn['raw_data']['contract'][0]['parameter']['value']['amount'] / 1000000} TRX")
            print(f"Confirmations: {confirmations}")
            print("-----")
    else:
        print("Error: Unable to fetch transactions.")


def get_last_usdt_transaction(address):
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?only_confirmed=true&limit=10&contract_address={usdt_contract}"
    headers = {
        "accept": "application/json",
        "TRON-PRO-API-KEY": api_key
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        transactions = data["data"]

        last_usdt_txn = None

        for txn in transactions:
            if "token_info" in txn and txn["token_info"]["address"] == usdt_contract:
                if txn["to"] == address:
                    last_usdt_txn = txn
                    break

        if last_usdt_txn:
            # Получение номера блока, в котором была включена транзакция
            print(last_usdt_txn)
            # block_number = last_usdt_txn.get("blockNumber")

            # Получение текущего номера блока
            client = Tron(HTTPProvider(api_key=api_key))
            current_block = client.get_latest_block_number()
            transaction = client.get_transaction_info(last_usdt_txn["transaction_id"])
            block_number = transaction['blockNumber']
            # transaction = client.get_transaction(last_usdt_txn["transaction_id"])
            # print(transaction)

            # Вычисление количества подтверждений
            confirmations = current_block - block_number

            amount = int(last_usdt_txn['value'])

            print(f"Last USDT Transaction ID: {last_usdt_txn['transaction_id']}")
            print(f"Amount: {amount / 10 ** 6} USDT")
            print(f"Confirmations: {confirmations}")
        else:
            print("No USDT transactions found.")
    else:
        print("Error: Unable to fetch transactions.")


def tron_hex_decode(hex_address):
    # hex_address = '41a614f803b6fd780986a42c78ec9c7f77e6ded13c'
    decoded = bytes.fromhex(hex_address)
    encoded = base58.b58encode_check(decoded)
    print(encoded.decode('utf-8'))
    return encoded.decode('utf-8')


async def send_trx_async(public_key_to=None, amount=0, private_key_from=tron_master_key, private_key_to=None):
    if private_key_to:
        public_key_to = PrivateKey(bytes.fromhex(private_key_to)).public_key.to_base58check_address()

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        private_key = PrivateKey(bytes.fromhex(private_key_from))
        public_key_from = private_key.public_key.to_base58check_address()

        txb = (
            client.trx.transfer(public_key_from, public_key_to, amount * 10 ** 6)
            # .memo("test memo")
            .fee_limit(20_000_000)
        )
        txn = await txb.build()
        txn_ret = await txn.sign(private_key).broadcast()
        await txn_ret.wait()


async def send_usdt_async(public_key_to=None, amount=0, private_key_from=tron_master_key, private_key_to=None):
    if private_key_to:
        public_key_to = PrivateKey(bytes.fromhex(private_key_to)).public_key.to_base58check_address()

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        contract = await client.get_contract(usdt_contract)
        private_key = PrivateKey(bytes.fromhex(private_key_from))
        public_key_from = private_key.public_key.to_base58check_address()

        txb = await contract.functions.transfer(public_key_to, int(amount * 10 ** 6))
        # print(txb, type(txb))
        # print(public_key_from, type(public_key_from))
        txb = txb.with_owner(public_key_from).fee_limit(20_000_000)
        # txn = txn.sign(priv_key).inspect()
        txn = await txb.build()
        txn_ret = await txn.sign(private_key).broadcast()
        await txn_ret.wait()


async def get_usdt_balance(public_key=None, private_key=None):
    if private_key:
        public_key = PrivateKey(bytes.fromhex(private_key)).public_key.to_base58check_address()

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        contract = await client.get_contract(usdt_contract)
        balance = (await contract.functions.balanceOf(public_key)) / 10 ** 6

    return balance


def check_valid_trx(public_key):
    try:
        return is_address(public_key)
    except:
        return False


async def get_trx_balance(public_key=None, private_key=None):
    if private_key:
        public_key = PrivateKey(bytes.fromhex(private_key)).public_key.to_base58check_address()

    balance = 0
    with suppress(exceptions.AddressNotFound):
        async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
            balance = await client.get_account_balance(public_key)
    return balance


async def get_last_usdt_transaction_sum(public_key=None, private_key=None):
    if private_key:
        public_key = PrivateKey(bytes.fromhex(private_key)).public_key.to_base58check_address()

    url = f"https://api.trongrid.io/v1/accounts/{public_key}/transactions/trc20?" \
          f"only_confirmed=true&limit=10&contract_address={usdt_contract}"
    headers = {
        "accept": "application/json",
        "TRON-PRO-API-KEY": api_key
    }
    status, response_json = await get_web_request('GET', url=url, headers=headers, return_type='json')
    transactions = response_json["data"]

    last_usdt_txn = None

    for txn in transactions:
        if "token_info" in txn and txn["token_info"]["address"] == usdt_contract:
            if txn["to"] == public_key:
                last_usdt_txn = txn
                break
            if txn["from"] == public_key:
                break

    if last_usdt_txn:
        amount = int(last_usdt_txn['value'])
        return amount / 10 ** 6
    else:
        return


def tron_get_public(private_key):
    public_key = PrivateKey(bytes.fromhex(private_key)).public_key.to_base58check_address()
    return public_key


def tron_help():
    # how do it manually
    # 1 get public key
    # GBVDLK25AILUULY6B5OYB2WCZUIESWU4KY63OKDVEYRV76NNFLT32XEH
    # 2  get usdt
    user_tron_private_key = '*'
    print(tron_get_public(user_tron_private_key))
    user_tron_public_key = 'TUTBziqeXsh3LAH7QUYoaAYruzhUqLWu2n'
    #
    # check last_usdt_transaction_sum
    usdt_balance = asyncio.run(get_last_usdt_transaction_sum(public_key=user_tron_public_key))
    print(usdt_balance)
    # 40
    # check address
    print(asyncio.run(get_trx_balance(private_key=user_tron_private_key)))
    # if 0 then
    # print(asyncio.run(send_trx_async(amount=50, private_key_to=user_tron_private_key)))

    # if last_usdt_transaction_sum
    print(asyncio.run(send_usdt_async(amount=usdt_balance,
                                      private_key_to=tron_master_key,
                                      private_key_from=user_tron_private_key)))

    pass
    # print(check_valid_trx('TEuGUhPV9a52MiV5zExwbVESojiKi1Pumn'))
    # print(asyncio.run(get_trx_balance(public_key='TEuGUhPV9a52MiV5zExwbVESojiKi1Pumn')))
    # asyncio.run(send_trx_async(public_key_to='TKvcdvh628662g142UNQe2dpXxASRp7fv2', amount=50))
    # asyncio.run(send_usdt_async(public_key_to='TNsfWkRay3SczwkB4wqyB8sCPTzCNQo4Cb', amount=520, private_key_from='*'))


if __name__ == "__main__":
    tron_help()
    # my_tron = 'TPtRHKXMJqHJ35cqdBBkA18ei9kcjVJsmZ'
    # TV9NxnvRDMwtEoPPmqvk7kt3NDGZTMTNDd
    # print(asyncio.run(get_trx_balance(private_key=create_trc_private_key())))
    # print(asyncio.run(get_trx_balance(my_tron)))
    # print(show_balance(my_tron))
    # print(show_balance(PrivateKey(bytes.fromhex(create_trc_private_key())).public_key.to_base58check_address()))
