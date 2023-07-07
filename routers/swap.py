from typing import List

import jsonpickle
from aiogram import Router, types
from aiogram.filters import Text
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session
from stellar_sdk import Asset

from utils.aiogram_utils import my_gettext, send_message
from keyboards.common_keyboards import get_kb_return, get_kb_yesno_send_xdr, get_return_button
from mytypes import Balance
from utils.stellar_utils import stellar_get_balances, stellar_get_user_account, stellar_check_receive_asset, \
    stellar_check_receive_sum, stellar_swap, stellar_get_market_link, my_float, float2str


class StateSwapToken(StatesGroup):
    swap_sum = State()


class SwapAssetFromCallbackData(CallbackData, prefix="SwapAssetFromCallbackData"):
    answer: str


class SwapAssetForCallbackData(CallbackData, prefix="SwapAssetForCallbackData"):
    answer: str


router = Router()


@router.callback_query(Text(text=["Swap"]))
async def cmd_swap_01(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'choose_token_swap')
    asset_list = await stellar_get_balances(session, callback.from_user.id)

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                  callback_data=SwapAssetFromCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))
    await state.update_data(assets=jsonpickle.encode(asset_list))
    await callback.answer()


@router.callback_query(SwapAssetFromCallbackData.filter())
async def cq_swap_choose_token_from(callback: types.CallbackQuery, callback_data: SwapAssetFromCallbackData,
                                    state: FSMContext, session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    for asset in asset_list:
        if asset.asset_code == answer:
            if my_float(asset.balance) == 0.0:
                await callback.answer(my_gettext(callback, "zero_sum"), show_alert=True)
            else:
                await state.update_data(send_asset_code=asset.asset_code, send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance)

                msg = my_gettext(callback, 'choose_token_swap2', (asset.asset_code,))

                kb_tmp = []
                asset_list2 = []
                for token in await stellar_get_balances(session, callback.from_user.id):
                    asset_list2.append(Asset(token.asset_code, token.asset_issuer))
                receive_assets = await stellar_check_receive_asset(Asset(asset.asset_code, asset.asset_issuer), '10',
                                                                   asset_list2)

                for receive_asset in receive_assets:
                    kb_tmp.append([types.InlineKeyboardButton(text=f"{receive_asset}",
                                                              callback_data=SwapAssetForCallbackData(
                                                                  answer=receive_asset).pack()
                                                              )])
                kb_tmp.append(get_return_button(callback))
                await send_message(session, callback, msg,
                                   reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))


@router.callback_query(SwapAssetForCallbackData.filter())
async def cq_swap_choose_token_for(callback: types.CallbackQuery, callback_data: SwapAssetForCallbackData,
                                   state: FSMContext, session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    for asset in asset_list:
        if asset.asset_code == answer:
            await state.update_data(receive_asset_code=asset.asset_code,
                                    receive_asset_issuer=asset.asset_issuer,
                                    receive_asset_min_sum=asset.balance)
            data = await state.get_data()
            msg = my_gettext(callback, 'send_sum_swap', (data.get('send_asset_code'),
                                                         data.get('send_asset_max_sum', 0.0),
                                                         data.get('receive_asset_code'),
                                                         stellar_get_market_link(Asset(data.get("send_asset_code"),
                                                                                       data.get("send_asset_issuer")),
                                                                                 Asset(data.get('receive_asset_code'),
                                                                                       data.get(
                                                                                           'receive_asset_issuer')))
                                                         ))
            await state.set_state(StateSwapToken.swap_sum)
            await state.update_data(msg=msg)
            await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
    await callback.answer()


@router.message(StateSwapToken.swap_sum)
async def cmd_swap_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        await state.set_state(None)
        send_asset = data.get('send_asset_code')
        send_asset_code = data.get('send_asset_issuer')
        receive_asset = data.get('receive_asset_code')
        receive_asset_code = data.get('receive_asset_issuer')
        xdr = data.get('xdr')

        receive_sum = await stellar_check_receive_sum(Asset(send_asset, send_asset_code), float2str(send_sum),
                                                      Asset(receive_asset, receive_asset_code))
        xdr = await stellar_swap((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                                 Asset(send_asset, send_asset_code),
                                 float2str(send_sum), Asset(receive_asset, receive_asset_code), receive_sum, xdr=xdr)

        msg = my_gettext(message, 'confirm_swap', (float2str(send_sum), send_asset, receive_sum, receive_asset))

        await state.update_data(xdr=xdr, operation='swap')
        await send_message(session, message, msg, reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))
