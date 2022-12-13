from typing import List

from aiogram import Router, types, F
from aiogram.filters import Text
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from stellar_sdk import Asset
from stellar_sdk.sep.federation import resolve_stellar_address

import fb
from utils.aiogram_utils import my_gettext, send_message, logger, bot
from keyboards.common_keyboards import get_kb_return, get_return_button, get_kb_yesno_send_xdr
from mytypes import Balance
from utils.stellar_utils import stellar_check_account, stellar_is_free_wallet, stellar_get_balances, stellar_pay, \
    stellar_get_user_account


class StateSendToken(StatesGroup):
    sending_for = State()
    sending_sum = State()
    sending_memo = State()


class SendAssetCallbackData(CallbackData, prefix="send_asset_"):
    answer: str


router = Router()


@router.callback_query(Text(text=["Send"]))
async def cmd_send_start(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'send_address')

    await send_message(callback, msg, reply_markup=get_kb_return(callback))
    await state.set_state(StateSendToken.sending_for)
    await callback.answer()


@router.message(StateSendToken.sending_for, F.text)
async def cmd_send_for(message: Message, state: FSMContext):
    if '@' == message.text[0]:
        public_key = fb.execsql1(
            f"select w.public_key from MyMTLWalletBot w join MyMTLWalletBot_users u on u.user_id = w.user_id " +
            f"where u.user_name = ? and w.default_wallet = 1",
            (message.text.lower()[1:],))
        logger.info(f"{message.from_user.id}, {message.text}, {message.text[1:]}, {public_key}")
    else:
        public_key = message.text
    my_account = stellar_check_account(public_key)
    if my_account:
        await state.update_data(send_address=my_account.account.account.account_id)
        if my_account.memo:
            await state.update_data(memo=my_account.memo, federal_memo=True)

        await state.set_state(None)
        await cmd_send_choose_token(message, state)
    else:
        free_wallet = stellar_is_free_wallet(message.from_user.id)
        address = message.text
        if address.find('*') > 0:
            try:
                address = resolve_stellar_address(address).account_id
            except Exception as ex:
                logger.info(["StateSendFor", address, ex])
        if (not free_wallet) and (len(address) == 56) and (address[0] == 'G'):  # need activate
            await state.update_data(send_address=address)
            await state.set_state(state=None)
            await cmd_create_account(message, state)
        else:
            msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'send_address')
            await send_message(message, msg)


async def cmd_send_choose_token(message: types.Message, state: FSMContext):
    data = await state.get_data()
    address = data.get('send_address')

    msg = my_gettext(message, 'choose_token').format(address)
    asset_list = stellar_get_balances(message.from_user.id)
    sender_asset_list = stellar_get_balances(message.from_user.id, address)
    kb_tmp = []
    for token in asset_list:
        for sender_token in sender_asset_list:
            if token.asset_code == sender_token.asset_code or token.asset_issuer == address:
                kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({token.balance})",
                                                          callback_data=SendAssetCallbackData(
                                                              answer=token.asset_code).pack()
                                                          )])
    kb_tmp.append(get_return_button(message))
    await send_message(message, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp), need_new_msg=True)
    await state.update_data(assets=asset_list)


@router.callback_query(SendAssetCallbackData.filter())
async def cb_send_choose_token(callback: types.CallbackQuery, callback_data: SendAssetCallbackData, state: FSMContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = data['assets']

    for asset in asset_list:
        if asset.asset_code == answer:
            if float(asset.balance) == 0.0:
                await callback.answer(my_gettext(callback, "zero_sum"), show_alert=True)
            else:
                msg = my_gettext(callback, 'send_sum').format(asset.asset_code,
                                                              asset.balance)
                await state.update_data(send_asset_code=asset.asset_code, send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance, msg=msg)
                await state.set_state(StateSendToken.sending_sum)
                await send_message(callback, msg, reply_markup=get_kb_return(callback))
    return True


@router.message(StateSendToken.sending_sum)
async def cmd_send_get_sum(message: Message, state: FSMContext):
    try:
        send_sum = float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await cmd_send_04(message, state)
        await message.delete()
    else:
        await send_message(message, f"{my_gettext(message, 'bad_sum')}\n{data['msg']}")


async def cmd_send_04(message: types.Message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_asset = data.get("send_asset_code")
    send_address = data.get("send_address")
    send_memo = data.get("memo")
    federal_memo = data.get("federal_memo")

    msg = my_gettext(message, 'confirm_send').format(send_sum, send_asset, send_address, send_memo)

    send_asset_name = data["send_asset_code"]
    send_asset_code = data["send_asset_issuer"]

    xdr = stellar_pay(stellar_get_user_account(message.from_user.id).account.account_id,
                      send_address,
                      Asset(send_asset_name, send_asset_code), send_sum, memo=send_memo)

    await state.update_data(xdr=xdr)

    add_button_memo = federal_memo is None
    await send_message(message, msg, reply_markup=get_kb_yesno_send_xdr(message, add_button_memo=add_button_memo))


@router.callback_query(Text(text=["Memo"]))
async def cmd_get_memo(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'send_memo')
    await state.set_state(StateSendToken.sending_memo)
    await send_message(callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateSendToken.sending_memo)
async def cmd_send_to(message: Message, state: FSMContext):
    send_memo = message.text[:28]

    if len(send_memo) > 0:
        await state.update_data(memo=send_memo)
    await cmd_send_04(message, state)


async def cmd_create_account(message: types.Message, state: FSMContext):
    data = await state.get_data()

    send_sum = 3
    asset_list = stellar_get_balances(message.from_user.id, asset_filter='XLM')
    send_asset_code = asset_list[0].asset_code
    send_asset_issuer = asset_list[0].asset_issuer
    send_address = data.get('send_address', 'None 0_0')
    msg = my_gettext(message, 'confirm_activate').format(send_address, send_sum)

    xdr = stellar_pay(stellar_get_user_account(message.from_user.id).account.account_id,
                      send_address,
                      Asset(send_asset_code, send_asset_issuer), send_sum, create=True)

    await state.update_data(xdr=xdr, send_asset_code=send_asset_code, send_asset_issuer=send_asset_issuer,
                            send_sum=send_sum)

    await send_message(message, msg, reply_markup=get_kb_yesno_send_xdr(message))


@router.message(StateSendToken.sending_for, F.photo)
async def handle_docs_photo(message: types.Message, state: FSMContext):
    logger.info(f'{message.from_user.id}')
    if message.photo:
        await bot.download(message.photo[-1], destination=f'qr/{message.from_user.id}.jpg')
        from PIL import Image
        from pyzbar.pyzbar import decode
        data = decode(Image.open(f"qr/{message.from_user.id}.jpg"))
        if data:
            logger.info(str(data[0].data))
            message.text = data[0].data.decode()
            await cmd_send_for(message, state)
    await message.delete()
