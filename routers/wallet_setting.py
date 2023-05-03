from typing import List

import jsonpickle
from aiogram import Router, types
from aiogram.filters import Text
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from stellar_sdk import Asset

from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return
from mytypes import Balance
from routers.add_wallet import cmd_show_add_wallet_choose_pin
from routers.sign import cmd_ask_pin, PinState
from utils.aiogram_utils import send_message, my_gettext
from loguru import logger
from utils.stellar_utils import stellar_get_balances, stellar_add_trust, stellar_get_user_account, \
    stellar_is_free_wallet, public_issuer, get_good_asset_list, stellar_get_pin_type, stellar_pay, eurmtl_asset, \
    float2str


class DelAssetCallbackData(CallbackData, prefix="DelAssetCallbackData"):
    answer: str


class AddAssetCallbackData(CallbackData, prefix="AddAssetCallbackData"):
    answer: str


class StateAddAsset(StatesGroup):
    sending_code = State()
    sending_issuer = State()


router = Router()


@router.callback_query(Text(text=["WalletSetting"]))
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'wallet_setting_msg')
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_asset'), callback_data="AddAssetMenu")],
        # [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_buy'), callback_data="BuyAddress")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_key'), callback_data="GetPrivateKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_password'), callback_data="SetPassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_remove_password'), callback_data="RemovePassword")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'change_lang'), callback_data="ChangeLang")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_donate'), callback_data="Donate")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_set_default'), callback_data="SetDefault")],
        get_return_button(callback)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(callback, msg, reply_markup=keyboard)


@router.callback_query(Text(text=["AddAssetMenu"]))
async def cmd_add_asset(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'delete_asset')
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_delete_one'), callback_data="DeleteAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_list'), callback_data="AddAsset")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_expert'), callback_data="AddAssetExpert")],
        get_return_button(callback)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(callback, msg, reply_markup=keyboard)


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["DeleteAsset"]))
async def cmd_add_asset_del(callback: types.CallbackQuery, state: FSMContext):
    asset_list = await stellar_get_balances(callback.from_user.id)

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                  callback_data=DelAssetCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    msg = my_gettext(callback, 'delete_asset2')
    await send_message(callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))
    await state.update_data(assets=jsonpickle.encode(asset_list))
    await callback.answer()


@router.callback_query(DelAssetCallbackData.filter())
async def cq_swap_choose_token_from(callback: types.CallbackQuery, callback_data: DelAssetCallbackData,
                                    state: FSMContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        # todo send last coins
        xdr = await stellar_add_trust((await stellar_get_user_account(callback.from_user.id)).account.account_id,
                                Asset(asset[0].asset_code, asset[0].asset_issuer),
                                delete=True)

        msg = my_gettext(callback, 'confirm_close_asset', (asset[0].asset_code, asset[0].asset_issuer))
        await state.update_data(xdr=xdr)

        await send_message(callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    else:
        await callback.answer(my_gettext(callback, "bad_data"), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["AddAsset"]))
async def cmd_add_asset_add(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if await stellar_is_free_wallet(user_id) and (len(await stellar_get_balances(user_id)) > 5):
        await send_message(user_id, my_gettext(user_id, 'only_3'), reply_markup=get_kb_return(user_id))
        return False

    good_asset = get_good_asset_list()
    for item in await stellar_get_balances(user_id):
        found = list(filter(lambda x: x.asset_code == item.asset_code, good_asset))
        if len(found) > 0:
            good_asset.remove(found[0])

    if len(good_asset) == 0:
        await send_message(user_id, my_gettext(user_id, 'have_all'), reply_markup=get_kb_return(user_id))
        return False

    kb_tmp = []
    for key in good_asset:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{key.asset_code}",
                                                  callback_data=AddAssetCallbackData(
                                                      answer=key.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(callback, my_gettext(user_id, 'open_asset'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))

    await state.update_data(assets=jsonpickle.encode(good_asset))


@router.callback_query(AddAssetCallbackData.filter())
async def cq_add_asset(callback: types.CallbackQuery, callback_data: AddAssetCallbackData,
                       state: FSMContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    asset = list(filter(lambda x: x.asset_code == answer, asset_list))
    if asset:
        await state.update_data(send_asset_code=asset[0].asset_code,
                                send_asset_issuer=asset[0].asset_issuer)
        await cmd_add_asset_end(callback.message.chat.id, state)
    else:
        await callback.answer(my_gettext(callback, "bad_data"), show_alert=True)
        logger.info(f'error add asset {callback.from_user.id} {answer}')

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["AddAssetExpert"]))
async def cmd_add_asset_expert(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if await stellar_is_free_wallet(user_id) and (len(await stellar_get_balances(user_id)) > 5):
        await send_message(user_id, my_gettext(user_id, 'only_3'), reply_markup=get_kb_return(user_id))
        return False

    await state.set_state(StateAddAsset.sending_code)
    msg = my_gettext(user_id, 'send_code')
    await send_message(user_id, msg, reply_markup=get_kb_return(user_id))
    await callback.answer()


@router.message(StateAddAsset.sending_code)
async def cmd_swap_sum(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    asset_code = message.text
    await state.update_data(send_asset_code=asset_code)

    await state.set_state(StateAddAsset.sending_issuer)

    msg = my_gettext(user_id, 'send_issuer', (public_issuer,))
    await send_message(user_id, msg, reply_markup=get_kb_return(user_id))


@router.message(StateAddAsset.sending_issuer)
async def cmd_swap_sum(message: types.Message, state: FSMContext):
    await state.update_data(send_asset_issuer=message.text)
    await cmd_add_asset_end(message.chat.id, state)


########################################################################################################################
########################################################################################################################
########################################################################################################################


async def cmd_add_asset_end(chat_id: int, state: FSMContext):
    data = await state.get_data()
    asset_code = data.get('send_asset_code', 'XLM')
    asset_issuer = data.get('send_asset_issuer', '')

    xdr = await stellar_add_trust((await stellar_get_user_account(chat_id)).account.account_id, Asset(asset_code, asset_issuer))

    msg = my_gettext(chat_id, 'confirm_asset', (asset_code, asset_issuer))

    await state.update_data(xdr=xdr)
    await send_message(chat_id, msg, reply_markup=get_kb_yesno_send_xdr(chat_id))


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["RemovePassword"]))
async def cmd_remove_password(callback: types.CallbackQuery, state: FSMContext):
    pin_type = stellar_get_pin_type(callback.from_user.id)
    if pin_type in (1, 2):
        await state.update_data(remove_password=True)
        await state.set_state(PinState.sign)
        await cmd_ask_pin(callback.from_user.id, state)
        await callback.answer()
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        await callback.answer('You dont have password or pin', show_alert=True)


@router.callback_query(Text(text=["SetPassword"]))
async def cmd_set_password(callback: types.CallbackQuery, state: FSMContext):
    pin_type = stellar_get_pin_type(callback.from_user.id)
    if pin_type in (1, 2):
        await callback.answer('You have password. Remove it first', show_alert=True)
    elif pin_type == 10:
        await callback.answer('You have read only account', show_alert=True)
    elif pin_type == 0:
        if await stellar_is_free_wallet(callback.from_user.id):
            await callback.answer('You have free account. Please buy it first.', show_alert=True)
        else:
            public_key = (await stellar_get_user_account(callback.from_user.id)).account.account_id
            await state.update_data(public_key=public_key)
            await cmd_show_add_wallet_choose_pin(callback.from_user.id, state,
                                                 my_gettext(callback, 'for_address', (public_key,)))
            await callback.answer()


@router.callback_query(Text(text=["GetPrivateKey"]))
async def cmd_get_private_key(callback: types.CallbackQuery, state: FSMContext):
    if await stellar_is_free_wallet(callback.from_user.id):
        await cmd_buy_private_key(callback, state)
        # await callback.answer('You have free account. Please buy it first.')
    else:
        pin_type = stellar_get_pin_type(callback.from_user.id)

        if pin_type == 10:
            await callback.answer('You have read only account', show_alert=True)
        else:
            await state.update_data(send_private_key=True)
            await state.set_state(PinState.sign)
            await cmd_ask_pin(callback.from_user.id, state)
            await callback.answer()


@router.callback_query(Text(text=["BuyAddress"]))
async def cmd_buy_private_key(callback: types.CallbackQuery, state: FSMContext):
    if await stellar_is_free_wallet(callback.from_user.id):
        public_key = (await stellar_get_user_account(callback.from_user.id)).account.account_id
        father_key = (await stellar_get_user_account(0)).account.account_id
        await state.update_data(buy_address=public_key)
        balances = await stellar_get_balances(callback.from_user.id)
        eurmtl_balance = 0
        for balance in balances:
            if balance.asset_code == 'EURMTL':
                eurmtl_balance = float(balance.balance)
                break
        if eurmtl_balance < 1:
            await callback.answer("You have free account. Please buy it first. You don't have enough money. Need 1 EURMTL", show_alert=True)
        else:
            await callback.answer("You have free account. Please buy it first", show_alert=True)
            memo = f"{callback.from_user.id}*{public_key[len(public_key) - 4:]}"
            xdr = await stellar_pay(public_key, father_key, eurmtl_asset, 1, memo=memo)
            await state.update_data(xdr=xdr)
            msg = my_gettext(callback, 'confirm_send', (1, eurmtl_asset.code, father_key, memo))
            msg = f"For buy {public_key}\n{msg}"

            await send_message(callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    else:
        await callback.answer('You can`t buy. You have you oun account. But you can donate /donate', show_alert=True)
