import asyncio
import base64
from contextlib import suppress
from urllib.parse import urlparse, parse_qs
from typing import List, Optional, Union, Dict

import jsonpickle
from sqlalchemy.orm import Session
from aiogram.utils.text_decorations import html_decoration
from cryptocode import encrypt, decrypt
from stellar_sdk import AiohttpClient, ServerAsync, StrKey, MuxedAccount
from stellar_sdk import Network, TransactionBuilder, Asset, Account, Keypair, Price, TransactionEnvelope
from stellar_sdk.exceptions import BadRequestError, NotFoundError
from stellar_sdk.sep import stellar_uri
from stellar_sdk.sep.federation import resolve_stellar_address

from other.config_reader import config

from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from core.use_cases.wallet.get_balance import GetWalletBalance
from infrastructure.services.stellar_service import StellarService
from other.mytypes import MyOffers, MyAccount, Balance, MyOffer
from other.aiogram_tools import get_web_request
from other.counting_lock import CountingLock
from other.asset_visibility_tools import get_asset_visibility, ASSET_VISIBLE, \
    ASSET_EXCHANGE_ONLY  # Import for asset visibility tools

base_fee = config.base_fee

new_wallet_lock = CountingLock()

# https://stellar-sdk.readthedocs.io/en/latest/

public_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
public_mmwb = "GBSNN2SPYZB2A5RPDTO3BLX4TP5KNYI7UMUABUS3TYWWEWAAM2D7CMMW"

xlm_asset = Asset("XLM")
mtl_asset = Asset("MTL", public_issuer)
eurmtl_asset = Asset("EURMTL", public_issuer)
btcmtl_asset = Asset("BTCMTL", public_issuer)
satsmtl_asset = Asset("SATSMTL", public_issuer)
usdc_asset = Asset("USDC", 'GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN')
usdm_asset = Asset("USDM", 'GDHDC4GBNPMENZAOBB4NCQ25TGZPDRK6ZGWUGSI22TVFATOLRPSUUSDM')


# eurdebt_asset = Asset("EURDEBT", public_issuer)

async def process_uri_with_replace(data, source_account):
    """Process URI with replace parameter"""
    transaction = TransactionBuilder(
        source_account=source_account,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        base_fee=base_fee,
    )
    transaction.set_timeout(60 * 60)

    for operation in data.transaction_envelope.transaction.operations:
        transaction.append_operation(operation)
    envelope = transaction.build()
    return envelope.to_xdr()


async def parse_transaction_stellar_uri(uri_data, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE):
    """
    Parse a Stellar transaction URI and extract relevant data.
    
    Args:
        uri_data (str): The Stellar URI string
        network_passphrase (str): The network passphrase
        
    Returns:
        dict: Dictionary containing parsed data (uri_object, callback_url, return_url)
    """
    uri_object = stellar_uri.TransactionStellarUri.from_uri(uri_data, network_passphrase=network_passphrase)

    # Extract callback
    callback_url = uri_object.callback

    # Try to extract return_url safely
    return_url = None

    # Method 1: Try to access as attribute
    if hasattr(uri_object, 'return_url'):
        return_url = uri_object.return_url

    # Method 2: Try to access from uri_object.operation_attrs if it exists
    elif hasattr(uri_object, 'operation_attrs') and 'return_url' in uri_object.operation_attrs:
        return_url = uri_object.operation_attrs['return_url']

    # Method 3: Try to parse from the original URI
    else:
        try:
            parsed = urlparse(uri_data)
            query_parameters = parse_qs(parsed.query)
            if 'return_url' in query_parameters:
                return_url = query_parameters['return_url'][0]
        except Exception:
            # If all methods fail, return_url remains None
            pass

    return {
        'uri_object': uri_object,
        'callback_url': callback_url,
        'return_url': return_url
    }


async def process_transaction_stellar_uri(uri_data, session, user_id,
                                          network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE):
    """
    Process a Stellar transaction URI and generate XDR.
    
    Args:
        uri_data (str): The Stellar URI string
        session (Session): Database session
        user_id (int): User ID
        network_passphrase (str): The network passphrase
        
    Returns:
        dict: Dictionary containing processed data (xdr, callback_url, return_url)
    """
    # Parse the URI
    parsed_data = await parse_transaction_stellar_uri(uri_data, network_passphrase)
    uri_object = parsed_data['uri_object']
    callback_url = parsed_data['callback_url']
    return_url = parsed_data['return_url']

    # Process XDR
    if uri_object.replace:
        source_account = await stellar_get_user_account(session, user_id)
        xdr_to_check = await process_uri_with_replace(uri_object, source_account)
    else:
        xdr_to_check = uri_object.transaction_envelope.to_xdr()

    return {
        'xdr': xdr_to_check,
        'callback_url': callback_url,
        'return_url': return_url
    }


async def parse_pay_stellar_uri(uri_data):
    """
    Parse a Stellar payment URI (web+stellar:pay) and extract parameters.
    
    Args:
        uri_data (str): The Stellar payment URI string
        
    Returns:
        dict: Dictionary containing parsed payment parameters
    """
    parsed = urlparse(uri_data)
    query_parameters = parse_qs(parsed.query)

    # Extract required parameters
    destination = query_parameters.get("destination")[0]
    amount = query_parameters.get("amount")[0]
    asset_code = query_parameters.get("asset_code")[0]
    asset_issuer = query_parameters.get("asset_issuer")[0]

    # Extract optional memo
    memo = query_parameters.get("memo")
    if memo:
        memo = memo[0]

    return {
        'destination': destination,
        'amount': amount,
        'asset_code': asset_code,
        'asset_issuer': asset_issuer,
        'memo': memo
    }


def get_good_asset_list() -> List[Balance]:
    return [
        Balance.from_dict(
            {"asset_code": 'AUMTL', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'EURMTL', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'BTCMTL', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'SATSMTL', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'LABR', "asset_issuer": 'GA7I6SGUHQ26ARNCD376WXV5WSE7VJRX6OEFNFCEGRLFGZWQIV73LABR'}),
        Balance.from_dict(
            {"asset_code": 'MTL', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'MTLRECT', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'MTLand', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'MTLCITY', "asset_issuer": 'GDUI7JVKWZV4KJVY4EJYBXMGXC2J3ZC67Z6O5QFP4ZMVQM2U5JXK2OK3'}),
        Balance.from_dict(
            {"asset_code": 'MTLDVL', "asset_issuer": 'GAMU3C7Q7CUUC77BAN5JLZWE7VUEI4VZF3KMCMM3YCXLZPBYK5Q2IXTA'}),
        Balance.from_dict(
            {"asset_code": 'FCM', "asset_issuer": 'GDIE253MSIYMFUS3VHRGEQPIBG7VAIPSMATWLTBF73UPOLBUH5RV2FCM'}),
        Balance.from_dict(
            {"asset_code": 'USDC', "asset_issuer": 'GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN'}),
        Balance.from_dict(
            {"asset_code": 'MMWB', "asset_issuer": 'GBSNN2SPYZB2A5RPDTO3BLX4TP5KNYI7UMUABUS3TYWWEWAAM2D7CMMW'}),
        Balance.from_dict(
            {"asset_code": 'USDM', "asset_issuer": 'GDHDC4GBNPMENZAOBB4NCQ25TGZPDRK6ZGWUGSI22TVFATOLRPSUUSDM'}),
        Balance.from_dict(
            {"asset_code": 'MTLFEST', "asset_issuer": 'GCGWAPG6PKBMHEEAHRLTWHFCAGZTQZDOXDMWBUBCXHLQBSBNWFRYFEST'}),
        Balance.from_dict(
            {"asset_code": 'MTLAP', "asset_issuer": 'GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA'}),
    ]


def stellar_get_transaction_builder(xdr: str) -> TransactionBuilder:
    # Преобразуем XDR обратно в TransactionEnvelope
    transaction_envelope = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)

    # Извлекаем существующую транзакцию из TransactionEnvelope
    existing_transaction = transaction_envelope.transaction

    # Загружаем исходную учетную запись
    source_account = Account(account=existing_transaction.source.account_id,
                             sequence=existing_transaction.sequence - 1)
    # await server.load_account(account_id=existing_transaction.source.account_id)

    # Создаем новый TransactionBuilder с той же исходной информацией
    transaction_builder = TransactionBuilder(
        source_account=source_account,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        base_fee=existing_transaction.fee  # Сохраняем исходную базовую комиссию
    )

    # Устанавливаем временные границы, если они были заданы
    if existing_transaction.preconditions.time_bounds:
        transaction_builder.set_timeout(existing_transaction.preconditions.time_bounds.max_time)
    else:
        # Если временные границы не заданы, задаем неограниченное время
        transaction_builder.set_timeout(0)

    # Добавляем все существующие операции из старой транзакции
    for op in existing_transaction.operations:
        transaction_builder.append_operation(op)

    # Возвращаем объект TransactionBuilder для дальнейших модификаций
    return transaction_builder


async def stellar_add_trust(user_key: str, asset: Asset, xdr: str = None, delete: bool = False):
    if xdr:
        transaction = stellar_get_transaction_builder(xdr)
        # TransactionBuilder.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    else:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(user_key)
            transaction = TransactionBuilder(source_account=source_account,
                                             network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
            transaction.set_timeout(60 * 60)

    if delete:
        transaction.append_change_trust_op(asset, limit='0', source=user_key)
    else:
        transaction.append_change_trust_op(asset, source=user_key)

    transaction = transaction.build()

    xdr = transaction.to_xdr()
    logger.info(f"new xdr: {xdr}")
    return xdr


async def stellar_close_asset(user_key: str, asset: Asset, amount, xdr: str = None):
    if xdr:
        transaction = stellar_get_transaction_builder(xdr)
    else:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(user_key)
            transaction = TransactionBuilder(source_account=source_account,
                                             network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
            transaction.set_timeout(60 * 60)

    amount_value = None
    if isinstance(amount, str) and amount == 'unlimited':
        amount_value = None
    else:
        try:
            amount_value = my_float(amount)
        except Exception:
            amount_value = None

    if amount_value is not None and amount_value > 0 and asset.issuer:
        transaction.append_payment_op(
            destination=asset.issuer,
            amount=float2str(amount_value),
            asset=asset,
            source=user_key
        )

    transaction.append_change_trust_op(asset, limit='0', source=user_key)
    transaction = transaction.build()

    xdr = transaction.to_xdr()
    logger.info(f"new xdr: {xdr}")
    return xdr


def stellar_sign(xdr: str, private_key: str):
    transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    transaction.sign(private_key)
    logger.info(f"new xdr sign : {transaction.to_xdr()}")
    return transaction.to_xdr()


async def get_eurmtl_xdr(url):
    try:
        url = 'https://eurmtl.me/remote/get_xdr/' + url.split('/')[-1]
        status, response_json = await get_web_request('GET', url=url)

        if 'xdr' in response_json:
            return response_json['xdr']
        else:
            return 'Invalid response format: missing "xdr" field.'

    except Exception as ex:
        logger.info(['get_eurmtl_xdr', ex])
        return 'An error occurred during the request.'


async def stellar_check_xdr(xdr: str, for_free_account=False):
    result = None
    allowed_operations = ["ManageData", "Payment", "ChangeTrust", "Clawback", "SetTrustLineFlags"]

    try:
        if xdr.find('eurmtl.me/sign_tools') > -1:
            xdr = await get_eurmtl_xdr(xdr)

        envelope = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)

        if for_free_account:
            all_operations_allowed = True

            for operation in envelope.transaction.operations:
                type_name = type(operation).__name__
                if type_name not in allowed_operations:
                    all_operations_allowed = False
                    break
                if type_name == "Payment" and operation.asset.code == "XLM":
                    all_operations_allowed = False
                    break

            if not all_operations_allowed and for_free_account:
                raise ValueError("Not all operations are allowed for free accounts.")

        result = envelope.to_xdr()

    except Exception as ex:
        logger.info(['stellar_check_xdr', xdr, ex])

    return result


async def stellar_user_sign(session: Session, xdr: str, user_id: int, user_password: str):
    user_key_pair = await stellar_get_user_keypair(session, user_id, user_password)
    return stellar_sign(xdr, user_key_pair.secret)


def is_base64(s):
    try:
        if base64.b64encode(base64.b64decode(s)) == s.encode():
            return True
    except Exception:
        return False


async def stellar_user_sign_message(session: Session, msg: str, user_id: int, user_password: str) -> str:
    user_key_pair = await stellar_get_user_keypair(session, user_id, user_password)
    return base64.b64encode(user_key_pair.sign(msg.encode())).decode()


async def async_stellar_send(xdr: str):
    async with ServerAsync(
            horizon_url=config.horizon_url_rw, client=AiohttpClient()
    ) as server:
        transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        transaction_resp = await server.submit_transaction(transaction)
        return transaction_resp


async def async_stellar_check_fee() -> str:
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        fee = (await server.fee_stats().call())["fee_charged"]
        return fee['min'] + '-' + fee['max']


# Deleted stellar_save_new, stellar_save_ro, stellar_create_new as they are unused or refactored to Use Cases.


async def stellar_pay(from_account: str, for_account: str, asset: Asset, amount: float, create: bool = False,
                      memo: str = None, xdr: str = None, fee=base_fee, cancel_offers=False):
    if xdr:
        transaction = TransactionBuilder.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    else:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(from_account)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=fee)
        transaction.set_timeout(60 * 60)

    # If 'cancel offers' option is checked, add to transaction operations of deleting all related offers 
    if cancel_offers:
        await stellar_del_selling_offers(transaction, source_account.account.account_id, asset)

    if create:
        transaction.append_create_account_op(destination=for_account, starting_balance=float2str(amount))
        transaction.add_text_memo('New account MyMTLWalletbot')
    else:
        if xdr:
            transaction.append_payment_op(destination=for_account, amount=float2str(amount), asset=asset,
                                          source=from_account)
        else:
            transaction.append_payment_op(destination=for_account, amount=float2str(amount), asset=asset)
        if memo:
            transaction.add_text_memo(memo)
    full_transaction = transaction.build()
    logger.info(full_transaction.to_xdr())
    return full_transaction.to_xdr()


async def stellar_get_selling_offers_sum(session: Session, user_id: int, sell_asset_filter: Asset):
    """
        Returns sum, blocked by Sell offers, filtered by selling asset
    """
    blocked_token_sum = 0.0
    offers = await stellar_get_offers(session, user_id)
    for offer in offers:
        if offer.selling.asset_code == sell_asset_filter.asset_code:
            blocked_token_sum += float(offer.amount)
    return blocked_token_sum


async def stellar_del_selling_offers(transaction: TransactionBuilder, account_id: str, sell_asset_filter: Asset):
    """
        Gets list of all offers of 'account' filtered by selling asset
        and add the delete operation to transaction for each or them.
    """

    # Get list of offers to delete
    async with ServerAsync(horizon_url=config.horizon_url, client=AiohttpClient()) as server:
        offers = MyOffers.from_dict(
            await server.offers().for_seller(account_id).for_selling(sell_asset_filter).limit(90).call()
        )

    # Add 'delete offer' operations to transaction
    for offer in offers.embedded.records:
        transaction.append_manage_sell_offer_op(
            selling=Asset(offer.selling.asset_code, offer.selling.asset_issuer),
            buying=Asset(offer.buying.asset_code, offer.buying.asset_issuer),
            amount='0',
            price='99999999',
            offer_id=offer.id
        )


async def stellar_swap(from_account: str, send_asset: Asset, send_amount: str, receive_asset: Asset,
                       receive_amount: str, xdr: str = None, cancel_offers: bool = False,
                       use_strict_receive: bool = False,
                       ):
    """
    Swap operation. If strict_receive_amount is provided, use path_payment_strict_receive (guaranteed receive amount).
    Otherwise, use path_payment_strict_send (guaranteed send amount).
    """
    if xdr:
        transaction = TransactionBuilder.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    else:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(from_account)

        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
        transaction.set_timeout(60 * 60)

    # If 'cancel offers' option is checked, add to transaction operations of deleting all related offers
    if cancel_offers:
        await stellar_del_selling_offers(transaction, source_account.account.account_id, send_asset)

    path = await stellar_get_receive_path(send_asset, send_amount, receive_asset)
    if use_strict_receive:
        # Use path_payment_strict_receive (guaranteed receive)
        transaction.append_path_payment_strict_receive_op(
            destination=from_account,
            send_asset=send_asset,
            send_max=send_amount,
            dest_asset=receive_asset,
            dest_amount=receive_amount,
            path=path
        )
    else:
        # Use path_payment_strict_send (guaranteed send)
        transaction.append_path_payment_strict_send_op(
            destination=from_account,
            send_asset=send_asset,
            send_amount=send_amount,
            dest_asset=receive_asset,
            dest_min=receive_amount,
            path=path
        )
    full_transaction = transaction.build()
    logger.info(full_transaction.to_xdr())
    return full_transaction.to_xdr()


async def stellar_sale(from_account: str, send_asset: Asset, send_amount: str, receive_asset: Asset,
                       receive_amount: str, offer_id: int = 0):
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        source_account = await server.load_account(from_account)

    transaction = TransactionBuilder(source_account=source_account,
                                     network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
    if (my_float(receive_amount) == 0.0) or (float(send_amount) == 0.0):
        price = '99999999'
    else:
        price = str(round(float(receive_amount) / float(send_amount), 7))

    transaction.append_manage_sell_offer_op(selling=send_asset, buying=receive_asset, amount=str(send_amount),
                                            price=Price.from_raw_price(price),
                                            offer_id=offer_id)
    transaction.set_timeout(60 * 60)
    full_transaction = transaction.build()
    logger.info(full_transaction.to_xdr())
    return full_transaction.to_xdr()


async def stellar_get_user_keypair(session: Session, user_id: int, user_password: str) -> Keypair:
    repo = SqlAlchemyWalletRepository(session)
    wallet = await repo.get_default_wallet(user_id) # Using async repo
    result = wallet.secret_key
    return Keypair.from_secret(decrypt(result, user_password))


async def stellar_get_user_seed_phrase(session: Session, user_id: int, user_password: str) -> str:
    """
    Получает сид-фразу пользователя из базы данных и расшифровывает её приватным ключом.
    
    :param session: Сессия базы данных
    :param user_id: ID пользователя
    :param user_password: Пароль пользователя
    :return: Расшифрованная сид-фраза или None, если её нет или не удалось расшифровать
    """
    repo = SqlAlchemyWalletRepository(session)
    wallet = await repo.get_default_wallet(user_id)
    if not wallet or not wallet.seed_key:
        return None

    try:
        # Получаем keypair с помощью пароля пользователя
        keypair = await stellar_get_user_keypair(session, user_id, user_password)
        # Расшифровываем сид-фразу с помощью приватного ключа
        decrypted_seed = decrypt(wallet.seed_key, keypair.secret)
        return decrypted_seed
    except Exception:
        return None


async def stellar_get_user_account(session: Session, user_id: int, public_key=None) -> Account:
    if public_key:
        result = public_key
    else:
        repo = SqlAlchemyWalletRepository(session)
        wallet = await repo.get_default_wallet(user_id)
        result = wallet.public_key
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        return await server.load_account(result)


async def stellar_get_master(session: Session) -> Keypair:
    return await stellar_get_user_keypair(session, 0, '0')


async def stellar_delete_account(master_account: Keypair, delete_account: Keypair):
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        logger.info(['delete_account', delete_account.public_key])
        source_account = await server.load_account(master_account)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
        account = await server.accounts().account_id(delete_account.public_key).call()
        master_account_details = await server.accounts().account_id(master_account.public_key).call()
        master_account_trustlines = {(balance['asset_code'], balance['asset_issuer']): balance
                                     for balance in master_account_details['balances'] if
                                     balance['asset_type'] != "native"}

        for balance in account['balances']:
            if balance['asset_type'] != "native":
                asset = Asset(balance['asset_code'], balance['asset_issuer'])
                if float(balance['balance']) > 0.0:
                    if (balance['asset_code'], balance['asset_issuer']) not in master_account_trustlines:
                        transaction.append_change_trust_op(asset=asset, source=master_account.public_key)

                    transaction.append_payment_op(destination=master_account.public_key, amount=balance['balance'],
                                                  asset=asset,
                                                  source=delete_account.public_key)
                transaction.append_change_trust_op(asset=asset, limit='0', source=delete_account.public_key)

        data_entries = account.get('data', {})
        for data_key in data_entries.keys():
            transaction.append_manage_data_op(data_name=data_key, data_value=None, source=delete_account.public_key)

        transaction.append_account_merge_op(master_account.public_key, delete_account.public_key)
        transaction.add_text_memo('Eat MyMTLWalletbot')
        transaction.set_timeout(60 * 60)
        full_transaction = transaction.build()
        xdr = full_transaction.to_xdr()
        if delete_account.signing_key:
            await async_stellar_send(stellar_sign(stellar_sign(xdr, master_account.secret), delete_account.secret))
        else:
            return xdr


async def stellar_delete_all_deleted(session: Session):
    master = await stellar_get_master(session)
    repo = SqlAlchemyWalletRepository(session)
    wallets = await repo.get_all_deleted()
    
    for wallet in wallets:
        if wallet.secret_key != 'TON':
            try:
                # check free_wallet property? Wallet entity has is_free boolean.
                # Legacy: if wallet.free_wallet == 1:
                # Entity: wallet.is_free
                if wallet.is_free:
                    with suppress(NotFoundError):
                        await stellar_delete_account(master,
                                                     Keypair.from_secret(
                                                         decrypt(wallet.secret_key, str(wallet.user_id))))
                
                # Delete hard
                # Checking Repo.delete signature: delete(user_id, public_key, erase=False, wallet_id=None)
                await repo.delete(wallet.user_id, wallet.public_key, erase=True)
            except Exception as e:
                print("\n---!!! ОБНАРУЖЕНА ОШИБКА !!!---")
                print(f"Не удалось обработать кошелек. Ошибка: {e}")
                # print("ДАННЫЕ ПРОБЛЕМНОГО КОШЕЛЬКА:")
                # import json
                # try:
                #     wallet_dict = wallet.__dict__
                #     print(json.dumps(wallet_dict, indent=4, default=str))
                # except:
                #     print(vars(wallet))
                # print("---!!! КОНЕЦ ИНФОРМАЦИИ ОБ ОШИБКЕ !!!---\\n")
                continue


async def stellar_get_balance_str(session: Session, user_id: int, public_key=None, state=None) -> str:
    # Use Use Case to get balances
    repo = SqlAlchemyWalletRepository(session)
    service = StellarService(config.horizon_url)
    use_case = GetWalletBalance(repo, service)
    
    # Logic for asset filter using state (ported from legacy)
    # legacy: only_eurmtl logic if state and !show_more -> asset_filter='EURMTL'
    # Use Case returns ALL balances. We filter here for string construction.
    
    balances = await use_case.execute(user_id, public_key)
    
    # Legacy: db_get_default_wallet used to check visibility.
    # Note: Use Case returns Balance objects.
    # We need to filter based on visibility string.
    # We need wallet entity to get visibility string.
    # If public_key provided, use case fetched it using service, but might not returned wallet entity (it returns List[Balance]).
    # But for visibility we need wallet settings!
    # If public_key is NOT None, we might check THEIR wallet settings if in DB?
    # Legacy line 708: wallet = db_get_default_wallet(session, user_id).
    # So it ALWAYS used MY default wallet settings? Even if checking another public key?
    # Yes, legacy line 708.
    
    wallet = await repo.get_default_wallet(user_id)
    vis_str = wallet.assets_visibility if wallet else None
    
    # Filter VISIBLE assets
    balances = [b for b in balances if get_asset_visibility(vis_str, b.asset_code) == ASSET_VISIBLE]
    
    # Filter EURMTL only if needed (legacy logic)
    if public_key is None and state and (await state.get_data()).get('show_more', False) == False:
         balances = [b for b in balances if b.asset_code == 'EURMTL']

    result = ''
    for balance in balances:
        # balance is core.domain.value_objects.Balance.
        # Legacy used dict-like object or specific class? 
        # Legacy: balance.selling_liabilities.
        # Domain Balance has selling_liabilities (str).
        
        if balance.selling_liabilities and float(balance.selling_liabilities) > 0:
            lock = float2str(balance.selling_liabilities, short=True)
            full = float2str(balance.balance, short=True)
            free = float2str(float(balance.balance) - float(balance.selling_liabilities), short=True)
            result += f"{balance.asset_code} : {free} (+{lock}={full})\n"
        else:
            result += f"{balance.asset_code} : {float2str(balance.balance, short=True)}\n"
            
    if wallet and wallet.is_free:
        result += 'XLM : <a href="https://telegra.ph/XLM-05-28">?</a>\n'
    return result


async def stellar_is_free_wallet(session: Session, user_id: int):
    repo = SqlAlchemyWalletRepository(session)
    wallet = await repo.get_default_wallet(user_id)
    return wallet.is_free if wallet else False


async def stellar_unfree_wallet(session: Session, user_id: int):
    try:
        # DB: db_unfree_wallet(session, user_id, user_account.account.account_id)
        # Usage: update wallet set free_wallet=0 where public_key matches.
        # Repo does not have explicit unfree_wallet.
        # But we can get wallet, update is_free=False, and save.
        repo = SqlAlchemyWalletRepository(session)
        wallet = await repo.get_default_wallet(user_id)
        if wallet and wallet.is_free:
            wallet.is_free = False
            await repo.update(wallet)
    except:
        return


async def stellar_get_balances(session, user_id: int, public_key=None,
                               asset_filter: str = None, state=None) -> List[Balance]:
    try:
        repo = SqlAlchemyWalletRepository(session)
        service = StellarService()
        use_case = GetWalletBalance(repo, service)

        # Get domain balances
        domain_balances = await use_case.execute(user_id, public_key)

        # Convert to legacy Balance
        result = []
        for db in domain_balances:
            # Map fields. Note: mytypes.Balance has many optional fields.
            lb = Balance(
                balance=db.balance,
                asset_code=db.asset_code,
                asset_issuer=db.asset_issuer,
                asset_type=db.asset_type,
                buying_liabilities=db.buying_liabilities,
                selling_liabilities=db.selling_liabilities
            )
            result.append(lb)

        # Apply asset filter if specified
        if asset_filter and result:
            result = [balance for balance in result if balance.asset_code == asset_filter]

        # Update state with MTLAP status if needed
        if state and result:
            mtlap_value = any(balance.asset_code == 'MTLAP' for balance in result)
            await state.update_data(mtlap=mtlap_value)

        return result

    except Exception as e:
        logger.error(f"Unexpected error in stellar_get_balances: {e}")
        return []


def get_first_balance_from_list(balance_list):
    if balance_list:
        return float(balance_list[0].balance)
    return 0.0


async def stellar_get_data(session: Session, user_id: int, public_key=None) -> dict:
    user_account = await stellar_get_user_account(session, user_id, public_key)
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        data = MyAccount.from_dict(await server.accounts().account_id(
            user_account.account.account_id).call()).data

    for data_name in list(data):
        data[data_name] = decode_data_value(data[data_name])

    return data


async def stellar_get_offers(session: Session, user_id: int, public_key=None) -> List[MyOffer]:
    user_account = await stellar_get_user_account(session, user_id, public_key)
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        offers = MyOffers.from_dict(await server.offers().for_seller(
            user_account.account.account_id).limit(90).call())

        for offer in offers.embedded.records:
            if offer.selling.asset_type == "native":
                offer.selling.asset_code = "XLM"
            if offer.buying.asset_type == "native":
                offer.buying.asset_code = "XLM"

        return offers.embedded.records


async def stellar_has_asset_offers(session: Session, user_id: int, asset: Asset) -> bool:
    offers = await stellar_get_offers(session, user_id)
    for offer in offers:
        if offer.selling and offer.selling.asset_code == asset.code and offer.selling.asset_issuer == asset.issuer:
            return True
        if offer.buying and offer.buying.asset_code == asset.code and offer.buying.asset_issuer == asset.issuer:
            return True
    return False


def stellar_change_password(session: Session, user_id: int, old_password: str, new_password: str,
                            password_type: int):
    account = Keypair.from_secret(decrypt(db_get_default_wallet(session, user_id).secret_key, old_password))
    db_update_secret_key(session, user_id, encrypt(account.secret, new_password), password_type)
    return account.public_key


class AccountAndMemo:
    def __init__(
            self,
            account: Account,
            memo: Optional[str] = None,
            account_id: Optional[str] = None
    ) -> None:
        self.account = account
        self.memo = memo
        self.account_id = account_id


async def stellar_check_account(public_key: str) -> AccountAndMemo:
    try:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:

            if public_key.find('*') > 0:
                record = resolve_stellar_address(public_key)
                public_key = record.account_id
                account = AccountAndMemo(await server.load_account(public_key))
                if record.memo:
                    account.memo = record.memo
                account.account_id = public_key
            else:
                account = AccountAndMemo(await server.load_account(public_key))
                account.account_id = public_key
            return account
    except Exception as ex:
        logger.info(["stellar_check_account", public_key, ex])
        # return None


async def stellar_check_receive_sum_one(send_asset: Asset, send_sum: str, receive_asset: Asset) -> str:
    try:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:
            call_result = await server.strict_send_paths(send_asset, send_sum, [receive_asset]).call()
            if len(call_result['_embedded']['records']) > 0:
                return float2str(float(call_result['_embedded']['records'][0]['destination_amount']))
            else:
                return '0'
    except Exception as ex:
        logger.info(["stellar_check_receive_sum", send_asset.code + ' ' + send_sum + ' ' + receive_asset.code, ex])
        return '0'


async def stellar_check_receive_sum(send_asset: Asset, send_sum: str, receive_asset: Asset) -> (str, bool):
    check_sum = float2str(float(send_sum) / 100)

    expected_receive = await stellar_check_receive_sum_one(send_asset, check_sum, receive_asset)
    expected_receive = float2str(float(expected_receive) * 100)
    actual_receive = await stellar_check_receive_sum_one(send_asset, send_sum, receive_asset)

    # Считаем, на сколько процентов цена отличается при разных объемах сделки
    difference_percentage = abs((float(actual_receive) - float(expected_receive)) / float(expected_receive) * 100)

    # Если разница больше 10%, возвращаем предупреждение
    if difference_percentage > 10:
        return actual_receive, True

    return actual_receive, False


async def stellar_check_send_sum(send_asset: Asset, receive_sum: str, receive_asset: Asset) -> (str, bool):
    """
    Calculate the required send amount to receive a given amount of receive_asset.
    Returns (send_amount, need_alert)
    """
    # Use Stellar pathfinding to get the best path and required send amount
    # For simplicity, use the same logic as in stellar_check_receive_sum_one, but for strict receive
    from other.config_reader import config
    from stellar_sdk import ServerAsync, AiohttpClient

    async with ServerAsync(horizon_url=config.horizon_url, client=AiohttpClient()) as server:
        paths = await server.strict_receive_paths(
            source=[send_asset],
            destination_asset=receive_asset,
            destination_amount=receive_sum
        ).call()
        if not paths or not paths.get('_embedded') or not paths['_embedded'].get('records'):
            return "0", True
        best_path = paths['_embedded']['records'][0]
        send_amount = best_path['source_amount']
        # Optionally, add alert if path is too long or liquidity is low
        return send_amount, False


async def stellar_get_receive_path(send_asset: Asset, send_sum: str, receive_asset: Asset) -> list:
    try:
        async with ServerAsync(
                horizon_url=config.horizon_url, client=AiohttpClient()
        ) as server:
            call_result = await server.strict_send_paths(send_asset, send_sum, [receive_asset]).call()
            if len(call_result['_embedded']['records']) > 0:
                # [{'asset_type': 'credit_alphanum12', 'asset_code': 'EURMTL',
                #  'asset_issuer': 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'},
                # {'asset_type': 'credit_alphanum12', 'asset_code': 'BTCMTL',
                #  'asset_issuer': 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}]
                if len(call_result['_embedded']['records'][0]['path']) == 0:
                    return []
                else:
                    result = []
                    for record in call_result['_embedded']['records'][0]['path']:
                        if record['asset_type'] == 'native':
                            result.append(xlm_asset)
                        else:
                            result.append(Asset(record['asset_code'],
                                                record['asset_issuer']))
                    return result
            else:
                return []
    except Exception as ex:
        logger.info(["stellar_check_receive_sum", send_asset.code + ' ' + send_sum + ' ' + receive_asset.code, ex])
        return []


async def stellar_check_receive_asset(send_asset: Asset, send_sum: str, receive_assets: List[Asset]) -> List[str]:
    """
    Check possible exchange paths for assets in Stellar network.
    """
    BATCH_SIZE = 3
    try:
        async with ServerAsync(horizon_url=config.horizon_url, client=AiohttpClient()) as server:
            records = []
            while receive_assets:
                current_batch = receive_assets[:BATCH_SIZE]
                call_result = await server.strict_send_paths(send_asset, send_sum, current_batch).call()
                records.extend(call_result['_embedded']['records'])
                receive_assets = receive_assets[BATCH_SIZE:]

            result = set()
            for record in records:
                asset_code = ''
                if record['destination_asset_type'] == "native":
                    asset_code = "XLM"
                elif record['destination_asset_type'].startswith("credit_alphanum"):
                    asset_code = record['destination_asset_code']

                if asset_code:
                    result.add(asset_code)

            return list(result)

    except BadRequestError as ex:
        logger.error(
            "Bad request error in stellar_check_receive_sum",
            extra={
                "send_asset": send_asset.code,
                "send_sum": send_sum,
                "receive_assets": str(receive_assets)[:15],
                "error": ex.message
            }
        )
        return []
    except Exception as ex:
        logger.error(
            "Unexpected error in stellar_check_receive_sum",
            extra={
                "send_asset": send_asset.code,
                "send_sum": send_sum,
                "receive_assets": str(receive_assets)[:15],
                "error": str(ex)
            }
        )
        return []


# def save_xdr_to_send(user_id, xdr):
#    fb.execsql('insert into mymtlwalletbot_transactions (user_id, user_transaction) values (?,?)',
#               (user_id, xdr))


def decode_data_value(data_value: str):
    try:
        base64_message = data_value
        base64_bytes = base64_message.encode('utf-8')
        message_bytes = base64.b64decode(base64_bytes)
        message = message_bytes.decode('utf-8')
        return message
    except Exception as ex:
        logger.info(f"decode_data_value error: {ex}")
        return 'decode error'


async def cmd_gen_data_xdr(from_account: str, name: str, value):
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        source_account = await server.load_account(from_account)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
        transaction.append_manage_data_op(data_name=name, data_value=value)
        transaction.set_timeout(60 * 60)
        full_transaction = transaction.build()
        logger.info(full_transaction.to_xdr())
        return full_transaction.to_xdr()


def gen_new(last_name):
    new_account = Keypair.random()
    i = 0
    while new_account.public_key[-len(last_name):] != last_name:
        new_account = Keypair.random()
        i += 1
    print(i, new_account.public_key, new_account.secret)
    return [i, new_account.public_key, new_account.secret]


# def run_async():
#    print(asyncio.run(stellar_delete_account(stellar_get_master(session), Keypair.from_secret(''))))


def stellar_get_market_link(sale_asset: Asset, buy_asset: Asset):
    sale_asset = sale_asset.code if sale_asset.is_native() else f'{sale_asset.code}-{sale_asset.issuer}'
    buy_asset = buy_asset.code if buy_asset.is_native() else f'{buy_asset.code}-{buy_asset.issuer}'
    # market_link = f'https://stellar.expert/explorer/public/market/{sale_asset}/{buy_asset}'
    market_link = f'https://eurmtl.me/cup/orderbook/{sale_asset}/{buy_asset}'
    market_link = html_decoration.link(value='expert', link=market_link)
    return market_link


def my_float(s) -> float:
    if isinstance(s, float):
        return s
    if s == 'unlimited':
        return float(9999999999)
    return float(str(s).replace(',', '.'))


# async def stellar_update_credit(credit_list):
#     # m.user_id, m.public_key, m.credit
#     i = 0
#     xdr = None
#     master = stellar_get_master(session)
#     for record in credit_list:
#         i = i + 1
#         if await stellar_check_account(record[1]):
#             fb.execsql(f"update mymtlwalletbot set credit = 5 where user_id = ? and public_key = ?",
#                        (record[0], record[1]))
#             xdr = await stellar_pay(master.public_key, record[1], xlm_asset, 2, xdr=xdr)
#             if i > 90:
#                 xdr = stellar_sign(xdr, master.secret)
#                 logger.info(xdr)
#                 resp = await async_stellar_send(xdr)
#                 logger.info(resp)
#                 return
#         else:
#             fb.execsql(f"update mymtlwalletbot set user_id = -1 * user_id where user_id = ? and public_key = ?",
#                        (record[0], record[1]))
#     xdr = stellar_sign(xdr, master.secret)
#     logger.info(xdr)
#     resp = await async_stellar_send(xdr)
#     logger.info(resp)


def my_round(x: float, base=2):
    return int(x * 10 ** base) / 10 ** base


def float2str(f, short: bool = False) -> str:
    if isinstance(f, str):
        if f == 'unlimited':
            return f
        f = float(f)
    if short and f > 0.01:
        s = "%.2f" % f
    else:
        s = "%.8f" % f
        s = s[:-1]
    while len(s) > 1 and s[-1] in ('0', '.'):
        l = s[-1]
        s = s[0:-1]
        if l == '.':
            break
    return s


def find_stellar_addresses(text):
    # Паттерн для обычных Stellar публичных ключей (начинаются с 'G' и содержат 56 символов)
    stellar_public_key_pattern = r'G[A-Za-z0-9]{55}'

    # Паттерн для Muxed адресов (начинаются с 'M' и содержат 69 символов)
    muxed_address_pattern = r'M[A-Za-z0-9]{68}'

    # Объединяем паттерны
    combined_pattern = f'({stellar_public_key_pattern}|{muxed_address_pattern})'

    # Находим все совпадения
    matches = re.findall(combined_pattern, text)

    # Проверяем каждое совпадение на валидность
    valid_addresses = []
    for match in matches:
        if is_valid_stellar_address(match):
            valid_addresses.append(match)

    return valid_addresses


def find_stellar_federation_address(text):
    # Stellar федеральные адреса имеют формат 'username*domain.com'
    stellar_federation_address_pattern = r'[a-z0-9]+[\._]?[a-z0-9]+[*][a-z0-9\-]+[\.][a-z0-9\.]+'
    match = re.search(stellar_federation_address_pattern, text)
    return match.group(0) if match else None


import re


def extract_url(msg, surl='eurmtl.me'):
    try:
        if surl:
            pattern = rf"https?://{re.escape(surl)}[^\s]+"
        else:
            pattern = r"https?://[^\s]+"

        search_result = re.search(pattern, msg)

        return search_result.group(0) if search_result else None
    except Exception as e:
        print(f"Error extracting URL: {e}")
        return None


def xdr_to_uri(xdr: str) -> str:
    transaction_envelope = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    t = stellar_uri.TransactionStellarUri(transaction_envelope=transaction_envelope)
    # t.sign(config_reader.config.signing_key.get_secret_value())
    return t.to_uri()


async def have_free_xlm(session, user_id: int, state=None):
    data = await state.get_data()
    if float(data.get('free_xlm', 0.0)) > 0.5:
        return True
    return False


async def stellar_get_multi_sign_xdr(public_key) -> str:
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        public_issuer_signers = MyAccount.from_dict(await server.accounts().account_id(public_issuer).call()).signers
        public_issuer_signers = sorted(
            public_issuer_signers,
            key=lambda x: (x.weight, x.key),
            reverse=True
        )
        public_issuer_signers = [signer for signer in public_issuer_signers if signer.key != public_issuer]

        account = MyAccount.from_dict(await server.accounts().account_id(public_key).call())
        data = account.data
        signers = account.signers

    for data_name in list(data):
        data[data_name] = decode_data_value(data[data_name])

    new_signers = {}
    for key, value in data.items():
        # Проверяем, начинается ли ключ с 'master_key_' и содержит ли он два подчеркивания
        if key.startswith('master_key_') and key.count('_') == 3:
            # Извлекаем число из ключа (оно находится между вторым и третьим подчеркиванием)
            number = key.split('_')[2]
            new_signers[value] = int(number)

    if public_key not in new_signers:
        new_signers[public_key] = 15

    # Проходим по public_issuer_signers и добавляем записи в new_signers
    for signer in public_issuer_signers:
        # Проверяем, достигнут ли предел в 21 запись, учитывая исходный словарь данных
        if len(new_signers) < 21:
            # Проверяем, есть ли уже ключ в new_signers
            if signer.key not in new_signers:
                new_signers[signer.key] = 1

    current_signers = {signer.key: signer.weight for signer in signers}

    # Создаем список для обновленных подписантов
    updated_signers = []

    # Шаг 1: Добавляем подписантов для удаления (вес 0)
    for signer in current_signers:
        if signer not in new_signers:
            updated_signers.append({'key': signer, 'weight': 0})

    # Шаг 2: Обновляем вес для существующих подписантов
    for signer, weight in current_signers.items():
        if signer in new_signers and new_signers[signer] != weight:
            updated_signers.append({'key': signer, 'weight': new_signers[signer]})

    # Шаг 3: Добавляем новых подписантов
    for signer, weight in new_signers.items():
        if signer not in current_signers:
            updated_signers.append({'key': signer, 'weight': weight})

    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        source_account = await server.load_account(public_key)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
        transaction.set_timeout(60 * 60 * 24)
        for signer in updated_signers:
            if signer['key'] == public_key:
                transaction.append_set_options_op(master_weight=signer['weight'])
            else:
                transaction.append_ed25519_public_key_signer(signer['key'], signer['weight'])

        if account.thresholds.med_threshold != 15:
            transaction.append_set_options_op(med_threshold=15, low_threshold=15, high_threshold=15)

        return transaction.build().to_xdr()


def cut_text_to_28_bytes(text: str) -> str:
    encoded_text = text.encode("utf-8")
    if len(encoded_text) <= 28:
        return text

    trimmed_text = encoded_text[:28]

    try:
        return trimmed_text.decode("utf-8")
    except UnicodeDecodeError:
        return trimmed_text[:27].decode("utf-8")


def is_valid_stellar_address(address):
    try:
        if address.startswith('G'):
            StrKey.decode_ed25519_public_key(address)
        elif address.startswith('M'):
            MuxedAccount.from_account(address)
        else:
            return False
        return True
    except Exception:
        return False


async def test():
    # Тестируем парсинг Stellar URI
    # xdr = await parse_transaction_stellar_uri(
    #    'web+stellar:tx?xdr=AAAAAgAAAAAEqbejBk1rxsHVls854RnAyfpJaZacvgwmQ0jxNDBvqgAAAMgAAAAAAAAAZQAAAAEAAAAAAAAAAAAAAABn7gE7AAAAAAAAAAIAAAAAAAAACgAAAA5ldXJtdGwubWUgYXV0aAAAAAAAAQAAAApwbXBobTU5bW1lAAAAAAABAAAAAC6F6mrl0kGQk%2FbzZ60mRWIoAqzhhMgX7hjAF9yaZNIGAAAACgAAAA73ZWJfYXV0aF9kb21haW4AAAAAAQAAAAlldXJtdGwubWUAAAAAAAAAAAAAAA%3D%3D&callback=url%3Ahttps%3A%2F%2Feurmtl.me%2Fremote%2Fsep07%2Fauth%2Fcallback&replace=sourceAccount%3AX%3BX%3Aaccount%20to%20authenticate&origin_domain=eurmtl.me&signature=c5i8LYqq9Ryf5GVcZ2nbUnBLNuSNFQvuuabqfM%2BFuIcYexatf09MGef2gYPxiK73vqNLEcjeMdcFxVbXwsulBQ%3D%3D&return_url=https%3A%2F%2Fbsn.mtla.me')
    # print(f"Parsed URI result: {xdr}")

    # Тестируем работу с адресом GAOLWUW52RYQDJCH2WLHY6BAYWFPRBM57JIORLVI7UPGW2EP7BHKKRUS
    test_address = "GAOLWUW52RYQDJCH2WLHY6BAYWFPRBM57JIORLVI7UPGW2EP7BHKKRUS"

    print(f"--- Testing with address: {test_address} ---")

    # 1. Проверяем валидность адреса
    is_valid = is_valid_stellar_address(test_address)
    print(f"Address is valid: {is_valid}")

    # 2. Получаем данные аккаунта и тестируем их декодирование
    print("\n--- Fetching and decoding account data ---")
    try:
        async with ServerAsync(horizon_url=config.horizon_url, client=AiohttpClient()) as server:
            account_details = await server.accounts().account_id(test_address).call()
            account_data = account_details.get('data', {})

        if not account_data:
            print("No 'data' entries found for this account.")
        else:
            print(f"Found {len(account_data)} data entries. Decoding...")
            decoded_count = 0
            error_count = 0
            for name, value in account_data.items():
                try:
                    decoded_value = decode_data_value(value)
                    print(f"  ✅ Decoded '{name}': {decoded_value}")
                    decoded_count += 1
                except Exception as e:
                    print(f"  ❌ FAILED to decode '{name}'. Value: {value}, Error: {e}")
                    error_count += 1

            if error_count == 0:
                print("\n✅ All account data decoded successfully!")
            else:
                print(f"\n❌ Finished with {error_count} decoding errors.")

    except Exception as e:
        print(f"❌ An error occurred while fetching account data: {e}")

    print("\n=== Test completed ===")


if __name__ == "__main__":
    # print(is_valid_stellar_address('MAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCAAAAAAAAAAAARXWI'))
    # print(is_valid_stellar_address('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI'))
    a = asyncio.run(test())
    print(a)
    pass
    # a = asyncio.run(stellar_get_multi_sign_xdr('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI'))
    # print(a)
    # from db.quik_pool import quik_pool
    # print(asyncio.run(stellar_delete_all_deleted(quik_pool())))
