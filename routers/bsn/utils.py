from typing import Union

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.requests import db_get_user_account_by_username
from other.config_reader import config
from stellar_sdk import ServerAsync, AiohttpClient, TransactionBuilder, Network

from routers.bsn.exceptions import EmptyTag, LengthError
from other.lang_tools import my_gettext
from other.mytypes import MyAccount
from other.stellar_tools import base_fee, decode_data_value, stellar_get_user_account

from routers.bsn.constants import DELETE_KEY, BACK_CALLBACK_DATA, SEND_CALLBACK_DATA
from routers.bsn.enums import ActionType
from routers.bsn.models import BSNData, BSNRow
from routers.bsn.value_objects import Key, Value, Address


def format_bsn_row(bsn_row: BSNRow) -> str:
    action_map = {
        ActionType.REMOVE: '[-]',
        ActionType.ADD: '[+]',
        ActionType.CHANGE: '[*]',
    }
    tag = bsn_row.tag
    value = bsn_row.value
    warn = '⚠️ ' if not tag.is_known_key else ''
    old_value = f" ({bsn_row.old_value})" if bsn_row.is_change() else ''
    return f"{action_map[bsn_row.action_type]} {warn}<code>{tag}</code>: {value}{old_value}\n"

def make_tag_message(bsn_data: BSNData, user_id: Union[CallbackQuery, Message, int, str]) -> str:
    help_text = my_gettext(user_id, 'bsn_help_text', (DELETE_KEY,))

    if bsn_data.is_empty():
        message = my_gettext(user_id, 'bsn_empty_message')
    else:
        message = my_gettext(user_id, 'bsn_address_part', (bsn_data.address,))
        flag = False
        for bsn_row in bsn_data.changed_items():
            if not bsn_row.tag.is_known_key:
                flag = True
            message += format_bsn_row(bsn_row)
        if flag:
            message += my_gettext(user_id, 'bsn_warning')
        message += my_gettext(user_id, 'bsn_last_part')
    message += help_text
    return message


def get_bsn_kb(user_id: Union[CallbackQuery, Message, int, str], send_enabled: bool = False) -> "InlineKeyboardMarkup":
    builder = InlineKeyboardBuilder()
    if send_enabled:
        builder.button(text=my_gettext(user_id, 'kb_send'), callback_data=SEND_CALLBACK_DATA)
    builder.button(text=my_gettext(user_id, 'kb_back'), callback_data=BACK_CALLBACK_DATA)
    builder.adjust(1, 1)
    return builder.as_markup()

async def parse_tag(*, tag: str, bsn_data: BSNData, message: "Message", session: "Session") -> None:
    if tag:
        tag_value = tag.split(' ', 1)
        if len(tag_value) == 2:
            try:
                if tag_value[1] == DELETE_KEY:
                    bsn_data.del_data_row(key=Key(tag_value[0]))
                else:
                    key, value = tag_value
                    if value.startswith('@'):
                        public_key, user_id = db_get_user_account_by_username(session, value)
                        if public_key:
                            value = public_key
                    bsn_data.add_new_data_row(key=Key(key), value=Value(value))
            except ValueError as e:
                await message.answer(my_gettext(message, 'bsn_error', (parse_exception(e, message),)))
        else:
            await message.answer(my_gettext(message, 'bsn_tag_value', (tag,)))

def parse_exception(exc: Exception, user_id: Union[CallbackQuery, Message, int, str]) -> str:
    if isinstance(exc, EmptyTag):
        return my_gettext(user_id, 'bsn_empty_tag_error', (exc.raw_tag,))
    if isinstance(exc, LengthError):
        return my_gettext(user_id, 'bsn_length_error', (len(exc.value), exc.value))


async def cmd_gen_data_xdr(bsn_data: BSNData) -> str:
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        source_account = await server.load_account(bsn_data.address)
        transaction = TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=base_fee,
        )
        for bsn_row in bsn_data.changed_items():
            if bsn_row.is_remove():
                value = None
            else:
                value = bsn_row.value
            transaction.append_manage_data_op(data_name=str(bsn_row.tag), data_value=value)
        transaction.set_timeout(60 * 60)
        full_transaction = transaction.build()
        return full_transaction.to_xdr()


async def bsn_stellar_get_data(session: "Session", user_id: int, public_key=None) -> BSNData:
    user_account = await stellar_get_user_account(session, user_id, public_key)
    async with ServerAsync(
            horizon_url=config.horizon_url, client=AiohttpClient()
    ) as server:
        data = MyAccount.from_dict(await server.accounts().account_id(
            user_account.account.account_id).call()).data

    for data_name in list(data):
        data[data_name] = decode_data_value(data[data_name])

    return BSNData(
        address=Address(user_account.account.account_id),
        data=[BSNRow.from_str(key, value) for key, value in data.items()]
    )