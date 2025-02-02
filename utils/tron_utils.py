from contextlib import suppress
import asyncio
import base58
import requests
from loguru import logger
from tronpy import Tron, AsyncTron, exceptions
from tronpy.keys import PrivateKey, is_address
from tronpy.providers import HTTPProvider, AsyncHTTPProvider
from utils.config_reader import config
from utils.aiogram_utils import get_web_request
from tronpy.keys import to_hex_address
from dataclasses import dataclass

TRX_TO_SUN = 10 ** 6  # Константа для конвертации TRX в SUN

# api_key from https://www.trongrid.io
api_key = config.tron_api_key.get_secret_value()
tron_master_address = config.tron_master_address
tron_master_key = config.tron_master_key.get_secret_value()
usdt_contract = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
usdt_hex_contract = '41a614f803b6fd780986a42c78ec9c7f77e6ded13c'
transfer_contract = 'TEZ8rh3z7Hxbx6HjS3KzEQQ8wNxHT4sLLJ'



@dataclass
class EnergyObject:
    total_energy_limit: int  # Общий лимит энергии в сети
    total_energy_weight: int  # Общий вес энергии в сети
    energy_limit: int
    energy_used: int
    need_delegate_energy: int = 65_000
    energy_delegated: int = 0

    @property
    def energy_amount(self) -> float:
        return self.energy_limit - self.energy_used

    @property
    def energy_per_trx(self) -> float:
        return self.total_energy_limit / self.total_energy_weight

    def calculate_energy_amount_in_trx(self, energy_amount: int = None) -> int:
        """Вычисляет количество TRX для указанного или текущего energy_amount."""
        if energy_amount is None:
            energy_amount = self.energy_amount
        return int(energy_amount / self.energy_per_trx) + 1


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


def send_trx(public_key_to, amount, private_key_from, private_key_to=None):
    client = Tron(HTTPProvider(api_key=api_key))
    private_key = PrivateKey(bytes.fromhex(private_key_from))
    public_key_from = private_key.public_key.to_base58check_address()

    if private_key_to is not None:
        public_key_to = PrivateKey(bytes.fromhex(private_key_to)).public_key.to_base58check_address()

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


async def send_usdt_async(public_key_to=None, amount=0, private_key_from=tron_master_key, private_key_to=None,
                          sun_fee=0):
    if private_key_to:
        public_key_to = PrivateKey(bytes.fromhex(private_key_to)).public_key.to_base58check_address()

    if sun_fee == 0:
        sun_fee = 30_000_000  # 10m sum = 10 trx ~ 1.1 usdt
    else:
        sun_fee = int(sun_fee * 1.2)  # add 20% for fee

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        contract = await client.get_contract(usdt_contract)
        private_key = PrivateKey(bytes.fromhex(private_key_from))
        public_key_from = private_key.public_key.to_base58check_address()

        txb = await contract.functions.transfer(public_key_to, int(amount * 10 ** 6))
        # print(txb, type(txb))
        # print(public_key_from, type(public_key_from))
        txb = txb.with_owner(public_key_from).fee_limit(sun_fee)
        # txn = txn.sign(priv_key).inspect()
        txn = await txb.build()
        txn_ret = await txn.sign(private_key).broadcast()
        transaction_hash = txn_ret.txid
        logger.info(f"Транзакция отправлена. Hash: {transaction_hash}")

        result = await txn_ret.wait()

        if result and 'receipt' in result and 'result' in result['receipt'] and result['receipt'][
            'result'] == 'SUCCESS':
            logger.info("Транзакция успешно выполнена")
            return True, transaction_hash
        else:
            logger.error(f"Транзакция не удалась. Статус: {result}")
            return False, transaction_hash


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


async def estimate_usdt_transfer_fee0(public_key_from, amount):
    """
    Оценивает стоимость отправки определённого количества USDT.
    :param public_key_from: Публичный ключ отправителя.
    :param amount: Количество USDT для отправки.
    :return: Оценочная стоимость отправки в TRX.
    """
    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        contract = await client.get_contract(usdt_contract)

        txb = await contract.functions.transfer(
            public_key_from,
            int(amount * 10 ** 6)
        )

        txb_with_owner = txb.with_owner(public_key_from).fee_limit(100_000_000)

        estimated_fee = await client.trigger_constant_contract(txb_with_owner)
        energy_used = estimated_fee["energy_used"]
        total_fee_in_trx = energy_used / client.energy_price  # Конвертация использованной энергии в TRX

        return total_fee_in_trx


async def get_usdt_transfer_fee(from_address_base58, to_address_base58, amount):
    # Преобразование адресов отправителя и получателя из Base58 в hex
    from_address_hex = to_hex_address(from_address_base58)
    to_address_hex = to_hex_address(to_address_base58)[2:]  # Прямое преобразование в hex без '0x' и '41'

    # Преобразование суммы в наименьшие единицы и кодирование в hex с ведущими нулями до 32 байтов
    amount_hex = format(amount * 10 ** 6, '064x')

    # Соединение адреса и суммы в одну строку параметров
    parameter = '0' * 24 + to_address_hex + amount_hex

    url = "https://api.trongrid.io/wallet/triggerconstantcontract"

    payload = {
        "owner_address": from_address_hex,
        "contract_address": to_hex_address(usdt_contract),
        "function_selector": "transfer(address,uint256)",
        "parameter": parameter,
        "visible": False
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "TRON-PRO-API-KEY": api_key
    }

    # response = requests.post(url, json=payload, headers=headers)
    status, response_json = await get_web_request("POST", url, headers=headers, json=payload,
                                                  return_type='json')

    if status != 200:
        raise ValueError(f"Ошибка при запросе к API Tron: {status}")

    # Вывод ответа API
    # print(response.json())
    energy_used = response_json['energy_used']
    cost_per_energy_unit = await get_energy_fee()  # Стоимость за единицу энергии в SUN
    total_cost_in_sun = energy_used * cost_per_energy_unit  # Общая стоимость в SUN
    total_cost_in_trx = total_cost_in_sun / 1_000_000  # Конвертация в TRX
    trc_cost = await get_tron_price_from_coingecko()

    # print(f"Общая стоимость использованной энергии: {total_cost_in_trx} TRX ({total_cost_in_trx * trc_cost} USDT)")
    return total_cost_in_trx * trc_cost, total_cost_in_sun


def get_energy_fee_():
    url = "https://api.trongrid.io/wallet/getchainparameters"
    response = requests.get(url)
    energy_fee = None
    if response.status_code == 200:
        for param in response.json().get("chainParameter", []):
            if param.get("key") == "getEnergyFee":  # Это ключ может отличаться или отсутствовать
                energy_fee = int(param.get("value"))
                # print(f"Стоимость энергии: {energy_fee}")
                break
    return energy_fee


async def get_energy_fee() -> int:
    """
    Получает текущую плату за энергию Tron (TRX) из TronGrid API.

    Returns:
        int: Плата за энергию Tron (TRX).
    """
    url = "https://api.trongrid.io/wallet/getchainparameters"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "TRON-PRO-API-KEY": api_key
    }

    status, response_data = await get_web_request("GET", url, headers=headers, return_type='json')

    if status != 200:
        raise ValueError(f"Ошибка при запросе к API TronGrid: {status}")

    energy_fee = None
    for param in response_data.get("chainParameter", []):
        if param.get("key") == "getEnergyFee":
            energy_fee = int(param.get("value"))
            break

    if energy_fee is None:
        raise ValueError("Не удалось найти параметр 'getEnergyFee' в ответе API")

    return energy_fee


def test4():
    from tronpy import Tron

    client = Tron(HTTPProvider(api_key=api_key))
    contract = client.get_contract(usdt_contract)

    # Построение транзакции без непосредственной отправки
    txn = (
        contract.functions.transfer('TPtRHKXMJqHJ35cqdBBkA18ei9kcjVJsmZ', 10 * 10 ** 6)
        .with_owner(tron_master_address)
        .fee_limit(20_000_000)
        .build()
    )

    # Просмотр закодированных данных транзакции
    print("Transaction data:", txn.to_json())

    s = {'txID': '10ec1aedd7fbbaf98a51f003054d43c6331124ef3f5b324b3036d449d986b577', 'raw_data': {'contract': [{
        'parameter': {
            'value': {
                'owner_address': '415e62c22aa70ba7530c8272ee34e4cbb23174fb0b',
                'contract_address': '41a614f803b6fd780986a42c78ec9c7f77e6ded13c',
                'data': 'a9059cbb00000000000000000000000098a9eeaafd78a1c6cbb7e7901ce7b5c1310d59f80000000000000000000000000000000000000000000000000000000000989680',
                'call_token_value': 0,
                'call_value': 0,
                'token_id': 0},
            'type_url': 'type.googleapis.com/protocol.TriggerSmartContract'},
        'type': 'TriggerSmartContract'}],
        'timestamp': 1708729524697,
        'expiration': 1708729584697,
        'ref_block_bytes': 'd583',
        'ref_block_hash': 'a207774cf197fd07',
        'fee_limit': 20000000},
         'signature': [],
         'permission': {'keys': [{'address': '415e62c22aa70ba7530c8272ee34e4cbb23174fb0b', 'weight': 1}],
                        'threshold': 1, 'permission_name': 'owner'}}


async def get_allowance(check_address):
    """
    Asynchronously gets the allowance for a specific address by interacting with the Tron blockchain.

    Args:
        check_address: The address for which the allowance needs to be checked (str)

    Returns:
        The allowance amount (int)
    """
    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        token_contract = await client.get_contract(usdt_contract)

        allowance = await token_contract.functions.allowance(check_address, transfer_contract)
        return allowance


async def set_allowance(amount=None, private_key=None):
    if amount:
        amount = amount * 10 ** 6
    else:
        amount = 115792089237316195423570985008687907853269984665640564039457

    private_key = PrivateKey(bytes.fromhex(private_key))
    public_key = private_key.public_key.to_base58check_address()

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        token_contract = await client.get_contract(usdt_contract)

        txb = await token_contract.functions.approve(transfer_contract, amount)
        # print(txb, type(txb))
        txb = txb.with_owner(public_key).fee_limit(20_000_000)
        # txn = txn.sign(priv_key).inspect()
        txn = await txb.build()
        txn_ret = await txn.sign(private_key).broadcast()
        print(txn_ret)
        await txn_ret.wait()


async def check_unconfirmed_usdt_transactions(public_key: str = None, private_key: str = None) -> bool:
    """
    Проверяет наличие неподтвержденных транзакций USDT.

    Args:
        public_key (str): Публичный ключ адреса.
        private_key (str, optional): Приватный ключ (необязательно).

    Returns:
        bool: True, если есть неподтвержденные транзакции, False - если нет.
    """

    if private_key:
        public_key = PrivateKey(bytes.fromhex(private_key)).public_key.to_base58check_address()

    confirmed_url = f"https://api.trongrid.io/v1/accounts/{public_key}/transactions/trc20?" \
                    f"only_confirmed=true&limit=100&contract_address={usdt_contract}"
    unconfirmed_url = f"https://api.trongrid.io/v1/accounts/{public_key}/transactions/trc20?" \
                      f"only_confirmed=false&limit=100&contract_address={usdt_contract}"

    headers = {
        "accept": "application/json",
        "TRON-PRO-API-KEY": api_key
    }

    confirmed_status, confirmed_response_json = await get_web_request('GET', url=confirmed_url,
                                                                      headers=headers, return_type='json')
    unconfirmed_status, unconfirmed_response_json = await get_web_request('GET', url=unconfirmed_url,
                                                                          headers=headers, return_type='json')

    if confirmed_status != 200 or unconfirmed_status != 200:
        raise ValueError("Ошибка при запросе к API TronGrid")

    confirmed_transactions = confirmed_response_json["data"]
    unconfirmed_transactions = unconfirmed_response_json["data"]

    confirmed_tx_ids = set()
    unconfirmed_tx_ids = set()

    for txn in confirmed_transactions:
        if "token_info" in txn and txn["token_info"]["address"] == usdt_contract:
            confirmed_tx_ids.add(txn["transaction_id"])

    for txn in unconfirmed_transactions:
        if "token_info" in txn and txn["token_info"]["address"] == usdt_contract:
            unconfirmed_tx_ids.add(txn["transaction_id"])

    print(confirmed_tx_ids, '\n', unconfirmed_tx_ids)
    return confirmed_tx_ids != unconfirmed_tx_ids


async def get_tron_price_from_coingecko() -> float:
    """
    Получает текущую цену Tron (TRX) в долларах США (USD) с CoinGecko API.

    Returns:
        float: Цена Tron (TRX) в долларах США (USD).
    """
    url = "https://api.coingecko.com/api/v3/simple/price?ids=tron&vs_currencies=usd"
    headers = {"accept": "application/json"}

    status, response_data = await get_web_request("GET", url, headers=headers, return_type='json')

    if status != 200:
        raise ValueError(f"Ошибка при запросе к API CoinGecko: {status}")

    price_usd = response_data["tron"]["usd"]
    return float(price_usd)


async def delegate_energy(
    energy_object: EnergyObject,
    public_key_to: str = None,
    private_key_to: str = None,
    private_key_from: str = tron_master_key,
    undo: bool = False
):
    """
    Делегирует или отменяет делегирование энергии.

    :param energy_object: Объект с информацией об энергии.
    :param public_key_to: Публичный ключ получателя (опционально, если указан private_key_to).
    :param private_key_to: Приватный ключ получателя (опционально, если указан public_key_to).
    :param private_key_from: Приватный ключ отправителя (по умолчанию tron_master_key).
    :param undo: Если True, отменяет делегирование.
    :return: Результат транзакции.
    """
    # Преобразуем приватный ключ получателя в публичный адрес, если он указан
    if private_key_to:
        public_key_to = PrivateKey(bytes.fromhex(private_key_to)).public_key.to_base58check_address()
    elif not public_key_to:
        raise ValueError("Either public_key_to or private_key_to must be provided")

    # Преобразуем приватный ключ отправителя в публичный адрес
    from_address = PrivateKey(bytes.fromhex(private_key_from)).public_key.to_base58check_address()

    # Проверяем, достаточно ли энергии для делегирования (если не отменяем)
    if energy_object.need_delegate_energy > energy_object.energy_amount and not undo:
        raise ValueError("Недостаточно энергии для делегирования")

    # Вычисляем количество энергии в TRX
    energy_amount_in_trx = energy_object.calculate_energy_amount_in_trx(energy_object.need_delegate_energy)

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        try:
            if undo:
                # Отменяем делегирование
                energy_undo = energy_object.energy_delegated if energy_object.energy_delegated > 0 else energy_amount_in_trx
                delegate_tx = await client.trx.undelegate_resource(
                    owner=from_address,
                    receiver=public_key_to,
                    balance=energy_undo * TRX_TO_SUN,
                    resource="ENERGY"
                ).build()
            else:
                # Делегируем энергию
                delegate_tx = await client.trx.delegate_resource(
                    owner=from_address,
                    receiver=public_key_to,
                    balance=energy_amount_in_trx * TRX_TO_SUN,
                    resource="ENERGY"
                ).build()
                energy_object.energy_delegated = energy_amount_in_trx  # Сохраняем количество делегированной энергии

            # Подписываем и отправляем транзакцию
            delegate_tx = delegate_tx.sign(PrivateKey(bytes.fromhex(private_key_from)))
            delegate_result = await delegate_tx.broadcast()
            await delegate_result.wait()  # Ожидаем подтверждения транзакции

            # Логируем успешное выполнение
            action = "undelegated" if undo else "delegated"
            logger.info(f"Successfully {action} {energy_amount_in_trx} TRX worth of energy to {public_key_to}")

            return delegate_result

        except Exception as e:
            # Логируем ошибку и выбрасываем исключение
            logger.error(f"An error occurred: {e}")
            raise


async def get_account_energy(address=None, private_key=tron_master_key) -> EnergyObject:
    if address is None:
        address = PrivateKey(bytes.fromhex(private_key)).public_key.to_base58check_address()

    async with AsyncTron(AsyncHTTPProvider(api_key=api_key)) as client:
        account_resources = await client.get_account_resource(address)
        # print(account_resources)  # 'TotalEnergyLimit': 180_000_000_000, 'TotalEnergyWeight': 15_972_160_745}
        # Энергия за 1 TRX = 180000000000 / 15972160745  ≈ 11.2696 энергии
        return EnergyObject(total_energy_limit=account_resources.get('TotalEnergyLimit', 0),
                            total_energy_weight=account_resources.get('TotalEnergyWeight', 0),
                            energy_limit=account_resources.get('EnergyLimit', 0),
                            energy_used=account_resources.get('EnergyUsed', 0))
        # account_resources.get('EnergyLimit', 0) - account_resources.get('EnergyUsed', 0)


async def run_test():
    # a = await delegate_energy(public_key_to='TPtRHKXMJqHJ35cqdBBkA18ei9kcjVJsmZ', energy_amount=100, undo=False)
    #    a = await get_usdt_transfer_fee(tron_master_address, 'TMVo5zCGUXUW7R62guXwNtXSstEAFm2zDY', 10)
    #   print(a)
    a = await get_account_energy()
    print(a, a.energy_amount, a.energy_per_trx, a.calculate_energy_amount_in_trx(), a.calculate_energy_amount_in_trx(65000))
    # print(await get_energy_in_trx_froze())
    # print(await get_usdt_balance('TFnuYLeMnftG4ajzRxL1o3mXJcFdFUg2Az'))
    # print(await delegate_energy(public_key_to='TFnuYLeMnftG4ajzRxL1o3mXJcFdFUg2Az', energy_amount=65_000, undo=False))


if __name__ == "__main__":
    pass
    asyncio.run(run_test())
    # print(get_account_energy(tron_master_key))
    # Private test
    # Key is df99b0d90e4b5a457516793924bd678efa1e0ac5a772b14be3cdc0c6969c9969
    # Address is TMVo5zCGUXUW7R62guXwNtXSstEAFm2zDY
