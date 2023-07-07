import asyncio
import base64
from contextlib import suppress

import jsonpickle
from aiogram.utils.text_decorations import html_decoration
import requests
from cryptocode import encrypt, decrypt
from stellar_sdk import Network, TransactionBuilder, Asset, Account, Keypair, Price, TransactionEnvelope
from stellar_sdk.exceptions import BadRequestError, NotFoundError
from stellar_sdk.sep.federation import resolve_stellar_address
from loguru import logger
from config_reader import config
from db.requests import *
from mytypes import MyOffers, MyAccount, Balance, MyOffer
from stellar_sdk import AiohttpClient, ServerAsync

base_fee = config.base_fee

# https://stellar-sdk.readthedocs.io/en/latest/

public_issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
public_mmwb = "GBSNN2SPYZB2A5RPDTO3BLX4TP5KNYI7UMUABUS3TYWWEWAAM2D7CMMW"

xlm_asset = Asset("XLM")
mtl_asset = Asset("MTL", public_issuer)
eurmtl_asset = Asset("EURMTL", public_issuer)
btcmtl_asset = Asset("BTCMTL", public_issuer)
satsmtl_asset = Asset("SATSMTL", public_issuer)
usdc_asset = Asset("USDC", 'GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN')


# eurdebt_asset = Asset("EURDEBT", public_issuer)


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
            {"asset_code": 'EURDEBT', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
        Balance.from_dict(
            {"asset_code": 'MTL', "asset_issuer": 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'}),
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
    ]


async def stellar_add_trust(user_key: str, asset: Asset, xdr: str = None, delete: bool = False):
    if xdr:
        transaction = TransactionBuilder.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    else:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
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
    # logger.info(f"xdr: {xdr}")
    return xdr


def stellar_sign(xdr: str, private_key: str):
    transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    transaction.sign(private_key)
    return transaction.to_xdr()


def get_url_xdr(url):
    rq = requests.get(url).text
    rq = rq[rq.find('<span class="tx-body">') + 22:]
    # logger.info(rq)
    rq = rq[:rq.find('</span>')]
    rq = rq.replace("&#x3D;", "=")
    # logger.info(rq)
    return rq


def stellar_check_xdr(xdr: str):
    result = None
    # "https://mtl.ergvein.net/view?tid=7ec5e397140fadf0d384860a35d19cf9f60e00a49b3b2cc250b832076fab7e7f"
    try:
        if xdr.find('mtl.ergvein.net/view') > -1 or xdr.find('eurmtl.me/sign_tools') > -1:
            xdr = get_url_xdr(xdr)
            result = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE).to_xdr()
        else:
            result = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE).to_xdr()

    except Exception as ex:
        logger.info(['stellar_check_xdr', xdr, ex])
    return result


def stellar_user_sign(session: Session, xdr: str, user_id: int, user_password: str):
    user_key_pair = stellar_get_user_keypair(session, user_id, user_password)
    return stellar_sign(xdr, user_key_pair.secret)


def stellar_user_sign_message(session: Session, msg: str, user_id: int, user_password: str) -> str:
    user_key_pair = stellar_get_user_keypair(session, user_id, user_password)
    return base64.b64encode(user_key_pair.sign(msg.encode())).decode()


async def async_stellar_send(xdr: str):
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        transaction_resp = await server.submit_transaction(transaction)
        return transaction_resp


async def async_stellar_check_fee() -> str:
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        fee = (await server.fee_stats().call())["fee_charged"]
        return fee['min'] + '-' + fee['max']


def stellar_save_new(session: Session, user_id: int, user_name: str, secret_key: str, free_wallet: bool,
                     address: str = None):
    if user_name:
        user_name = user_name.lower()

    if address:
        new_account = Keypair.from_secret(secret_key)
        public_key = address
    else:
        new_account = Keypair.from_secret(secret_key)
        public_key = new_account.public_key
    i_free_wallet = 1 if free_wallet else 0
    db_add_user_if_not_exists(session, user_id, user_name)

    db_add_user(session, user_id, public_key, encrypt(new_account.secret, str(user_id)), i_free_wallet)

    return public_key


def stellar_save_ro(session: Session, user_id: int, user_name: str, public_key: str):
    if user_name:
        user_name = user_name.lower()

    Keypair.from_public_key(public_key)

    i_free_wallet = 0
    db_add_user_if_not_exists(session, user_id, user_name)

    db_add_user(session, user_id, public_key, public_key, i_free_wallet)

    return public_key


async def stellar_create_new(session: Session, user_id: int, username: str):
    new_account = Keypair.random()
    stellar_save_new(session, user_id, username, new_account.secret, True)

    master = stellar_get_master(session)
    xdr = await stellar_pay(master.public_key, new_account.public_key, xlm_asset, 5, create=True, fee=1001001)
    # stellar_send(stellar_sign(xdr, master.secret))

    xdr = await stellar_add_trust(new_account.public_key, mtl_asset, xdr=xdr)
    xdr = await stellar_add_trust(new_account.public_key, eurmtl_asset, xdr=xdr)
    xdr = await stellar_add_trust(new_account.public_key, satsmtl_asset, xdr=xdr)
    xdr = await stellar_add_trust(new_account.public_key, usdc_asset, xdr=xdr)
    xdr = stellar_sign(xdr, new_account.secret)
    return stellar_sign(xdr, master.secret)


async def stellar_pay(from_account: str, for_account: str, asset: Asset, amount: float, create: bool = False,
                      memo: str = None, xdr: str = None, fee=base_fee):
    if xdr:
        transaction = TransactionBuilder.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    else:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(from_account)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=fee)
        transaction.set_timeout(60 * 60)

    if create:
        transaction.append_create_account_op(destination=for_account, starting_balance=float2str(round(amount, 7)))
        transaction.add_text_memo('New account MyMTLWalletbot')
    else:
        if xdr:
            transaction.append_payment_op(destination=for_account, amount=float2str(round(amount, 7)), asset=asset,
                                          source=from_account)
        else:
            transaction.append_payment_op(destination=for_account, amount=float2str(round(amount, 7)), asset=asset)
        if memo:
            transaction.add_text_memo(memo)
    full_transaction = transaction.build()
    logger.info(full_transaction.to_xdr())
    return full_transaction.to_xdr()


async def stellar_swap(from_account: str, send_asset: Asset, send_amount: str, receive_asset: Asset,
                       receive_amount: str, xdr: str = None):
    if xdr:
        transaction = TransactionBuilder.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    else:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(from_account)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
        transaction.set_timeout(60 * 60)
    transaction.append_path_payment_strict_send_op(from_account, send_asset, send_amount, receive_asset,
                                                   receive_amount,
                                                   await stellar_get_receive_path(send_asset, send_amount,
                                                                                  receive_asset))
    full_transaction = transaction.build()
    logger.info(full_transaction.to_xdr())
    return full_transaction.to_xdr()


async def stellar_sale(from_account: str, send_asset: Asset, send_amount: str, receive_asset: Asset,
                       receive_amount: str, offer_id: int = 0):
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
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


def stellar_get_user_keypair(session: Session, user_id: int, user_password: str) -> Keypair:
    result = db_get_default_wallet(session, user_id).secret_key
    return Keypair.from_secret(decrypt(result, user_password))


async def stellar_get_user_account(session: Session, user_id: int, public_key=None) -> Account:
    if public_key:
        result = public_key
    else:
        result = db_get_default_wallet(session, user_id).public_key
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        return await server.load_account(result)


def stellar_get_master(session: Session) -> Keypair:
    return stellar_get_user_keypair(session, 0, '0')


async def stellar_delete_account(master_account: Keypair, delete_account: Keypair):
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        logger.info(['delete_account', delete_account.public_key])
        source_account = await server.load_account(master_account)
        transaction = TransactionBuilder(source_account=source_account,
                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=base_fee)
        account = await server.accounts().account_id(delete_account.public_key).call()
        for balance in account['balances']:
            if balance['asset_type'] != "native":
                if float(balance['balance']) > 0.0:
                    transaction.append_payment_op(destination=master_account.public_key, amount=balance['balance'],
                                                  asset=Asset(balance['asset_code'], balance['asset_issuer']),
                                                  source=delete_account.public_key)
                transaction.append_change_trust_op(asset=Asset(balance['asset_code'], balance['asset_issuer']),
                                                   limit='0',
                                                   source=delete_account.public_key)

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
    master = stellar_get_master(session)
    for wallet in db_get_deleted_wallets_list(session):
        print(vars(wallet))
        if wallet.free_wallet == 1:
            with suppress(NotFoundError):
                await stellar_delete_account(master,
                                             Keypair.from_secret(decrypt(wallet.secret_key, str(wallet.user_id))))
        db_delete_wallet(session, wallet.user_id, wallet.public_key, erase=True)


async def stellar_get_balance_str(session: Session, user_id: int, public_key=None) -> str:
    start_time = datetime.now()
    balances = await stellar_get_balances(session, user_id, public_key)
    result = ''
    for balance in balances:
        result += f"{balance.asset_code} : {float2str(balance.balance)}\n"
    return result


async def stellar_is_free_wallet(session: Session, user_id: int):
    return db_get_default_wallet(session, user_id).free_wallet == 1


async def stellar_unfree_wallet(session: Session, user_id: int):
    try:
        user_account = await stellar_get_user_account(session, user_id)
        db_unfree_wallet(session, user_id, user_account.account.account_id)
    except:
        return


async def stellar_get_balances(session, user_id: int, public_key=None, asset_filter: str = None) -> List[Balance]:
    user_account = await stellar_get_user_account(session, user_id, public_key)
    free_wallet = await stellar_is_free_wallet(session, user_id)
    wallet = db_get_default_wallet(session, user_id)
    result = []
    balances = None
    if public_key is None and user_id > 0 and wallet.balances_event_id == wallet.last_event_id:
        balances = wallet.balances
    if balances is None:
        # получаем балансы
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            balances = MyAccount.from_dict(await server.accounts().account_id(
                user_account.account.account_id).call()).balances

        for balance in balances:
            if (balance.asset_type == "native") and (free_wallet == 0):
                result.append(balance)
            elif balance.asset_type[:15] == "credit_alphanum":
                result.append(balance)
        # получаем токены эмитента
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            issuer = await server.assets().for_issuer(user_account.account.account_id).call()
        for record in issuer['_embedded']['records']:
            result.append(Balance(balance='unlimited', asset_code=record['asset_code'], asset_type=record['asset_type'],
                                  asset_issuer=user_account.account.account_id))
        # сохраняем полный список
        if public_key is None:
            db_update_mymtlwalletbot_balances(session, jsonpickle.encode(result), user_id)

    else:
        result = jsonpickle.decode(balances)

    if asset_filter:
        result = [balance for balance in result if balance.asset_code == asset_filter]

    return result


async def stellar_get_data(session: Session, user_id: int, public_key=None) -> dict:
    user_account = await stellar_get_user_account(session, user_id, public_key)
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        data = MyAccount.from_dict(await server.accounts().account_id(
            user_account.account.account_id).call()).data

    for data_name in list(data):
        data[data_name] = decode_data_value(data[data_name])

    return data


async def stellar_get_offers(session: Session, user_id: int, public_key=None) -> List[MyOffer]:
    user_account = await stellar_get_user_account(session, user_id, public_key)
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        offers = MyOffers.from_dict(await server.offers().for_seller(
            user_account.account.account_id).limit(90).call())

        return offers.embedded.records


def stellar_change_password(session: Session, user_id: int, old_password: str, new_password: str,
                            password_type: int):
    account = Keypair.from_secret(decrypt(db_get_default_wallet(session, user_id).secret_key, old_password))
    db_update_secret_key(session, user_id, encrypt(account.secret, new_password), password_type)
    return account.public_key


class AccountAndMemo:
    def __init__(
            self,
            account: Account,
            memo: Optional[str] = None
    ) -> None:
        self.account = account
        self.memo = memo


async def stellar_check_account(public_key: str) -> AccountAndMemo:
    try:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:

            if public_key.find('*') > 0:
                record = resolve_stellar_address(public_key)
                public_key = record.account_id
                account = AccountAndMemo(await server.load_account(public_key))
                if record.memo:
                    account.memo = record.memo
            else:
                account = AccountAndMemo(await server.load_account(public_key))
            return account
    except Exception as ex:
        logger.info(["stellar_check_account", public_key, ex])
        # return None


async def stellar_check_receive_sum(send_asset: Asset, send_sum: str, receive_asset: Asset) -> str:
    try:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            call_result = await server.strict_send_paths(send_asset, send_sum, [receive_asset]).call()
            if len(call_result['_embedded']['records']) > 0:
                return float2str(float(call_result['_embedded']['records'][0]['destination_amount']))
            else:
                return '0'
    except Exception as ex:
        logger.info(["stellar_check_receive_sum", send_asset.code + ' ' + send_sum + ' ' + receive_asset.code, ex])
        return '0'


async def stellar_get_receive_path(send_asset: Asset, send_sum: str, receive_asset: Asset) -> list:
    try:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
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


async def stellar_check_receive_asset(send_asset: Asset, send_sum: str, receive_assets: list) -> list:
    try:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            records = []
            while len(receive_assets) > 0:
                call_result = await server.strict_send_paths(send_asset, send_sum, receive_assets[:3]).call()
                records.extend(call_result['_embedded']['records'])
                if len(receive_assets) > 0:
                    receive_assets.pop(0)
                if len(receive_assets) > 0:
                    receive_assets.pop(0)
                if len(receive_assets) > 0:
                    receive_assets.pop(0)
            result = []
            for record in records:
                asset_code = ''
                if record['destination_asset_type'] == "native":
                    asset_code = "XLM"
                elif record['destination_asset_type'][:15] == "credit_alphanum":
                    asset_code = record['destination_asset_code']

                if (len(asset_code) > 0) and not (asset_code in result):
                    result.append(asset_code)

            return result
    except BadRequestError as ex:
        logger.info(
            ["stellar_check_receive_sum", send_asset.code + ' ' + send_sum + ' ' + str(receive_assets)[:15],
             ex.message])
    except Exception as ex:
        logger.info(
            ["stellar_check_receive_sum", send_asset.code + ' ' + send_sum + ' ' + str(receive_assets)[:15], ex])
        return []


# def save_xdr_to_send(user_id, xdr):
#    fb.execsql('insert into mymtlwalletbot_transactions (user_id, user_transaction) values (?,?)',
#               (user_id, xdr))


def decode_data_value(data_value: str):
    base64_message = data_value
    base64_bytes = base64_message.encode('ascii')
    message_bytes = base64.b64decode(base64_bytes)
    message = message_bytes.decode('ascii')
    return message


async def cmd_gen_data_xdr(from_account: str, name: str, value):
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
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
    market_link = f'https://stellar.expert/explorer/public/market/{sale_asset}/{buy_asset}'
    market_link = html_decoration.link(value='expert', link=market_link)
    return market_link


def my_float(s: str) -> float:
    if s == 'unlimited':
        return float(9999999999)
    return float(s.replace(',', '.'))


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


def float2str(f) -> str:
    if isinstance(f, str):
        if f == 'unlimited':
            return f
        f = float(f)
    s = "%.7f" % f
    while len(s) > 1 and s[-1] in ('0', '.'):
        l = s[-1]
        s = s[0:-1]
        if l == '.':
            break
    return s


if __name__ == "__main__":
    pass
    from db.quik_pool import quik_pool

    print(asyncio.run(stellar_delete_all_deleted(quik_pool())))
