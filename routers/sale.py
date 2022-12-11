from typing import List

from aiogram import Router, types
from aiogram.filters import Text
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from stellar_sdk import Asset

from utils.aiogram_utils import my_gettext, send_message, logger
from keyboards.common_keyboards import get_kb_return, get_kb_yesno_send_xdr, get_return_button
from mytypes import Balance, MyOffer
from utils.stellar_utils import stellar_get_balances, stellar_get_user_account, stellar_sale, stellar_get_offers


class StateSaleToken(StatesGroup):
    selling_sum = State()
    selling_receive_sum = State()
    editing_amount = State()
    editing_price = State()


class SaleAssetCallbackData(CallbackData, prefix="SaleAssetCallbackData"):
    answer: str


class BuyAssetCallbackData(CallbackData, prefix="BuyAssetCallbackData"):
    answer: str


class EditOrderCallbackData(CallbackData, prefix="EditOrderCallbackData"):
    answer: int


router = Router()


@router.callback_query(Text(text=["Market"]))
async def cmd_market(callback: types.CallbackQuery, state: FSMContext):
    await send_message(callback.message.chat.id, my_gettext(callback, 'kb_market'),
                       reply_markup=get_kb_market(callback.message.chat.id))

    await callback.answer()


def get_kb_market(user_id: int) -> types.InlineKeyboardMarkup:
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_new_order'),
                                    callback_data="NewOrder")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_show_order'),
                                    callback_data="ShowOrders")],
        get_return_button(user_id)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(Text(text=["NewOrder"]))
async def cmd_sale_new_order(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'choose_token_sale')
    asset_list = stellar_get_balances(callback.from_user.id)

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({token.balance})",
                                                  callback_data=SaleAssetCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))
    await state.update_data(assets=asset_list)
    await callback.answer()


@router.callback_query(SaleAssetCallbackData.filter())
async def cq_send_choose_token(callback: types.CallbackQuery, callback_data: SaleAssetCallbackData, state: FSMContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = data['assets']
    for asset in asset_list:
        if asset.asset_code == answer:
            if float(asset.balance) == 0.0:
                await callback.answer(my_gettext(callback, "zero_sum"), show_alert=True)
            else:
                await state.update_data(send_asset_code=asset.asset_code,
                                        send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance)
                kb_tmp = []
                for token in asset_list:
                    kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({token.balance})",
                                                              callback_data=BuyAssetCallbackData(
                                                                  answer=token.asset_code).pack()
                                                              )])
                kb_tmp.append(get_return_button(callback))
                msg = my_gettext(callback, 'choose_token_swap2').format(asset.asset_code)
                await send_message(callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))

    await callback.answer()


@router.callback_query(BuyAssetCallbackData.filter())
async def cq_send_choose_token(callback: types.CallbackQuery, callback_data: BuyAssetCallbackData, state: FSMContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = data['assets']
    for asset in asset_list:
        if asset.asset_code == answer:
            msg = my_gettext(callback, 'send_sum_swap').format(data.get('send_asset_code'),
                                                               data.get('send_asset_max_sum', 0.0),
                                                               asset.asset_code)
            await state.update_data(receive_asset_code=asset.asset_code,
                                    receive_asset_issuer=asset.asset_issuer,
                                    receive_asset_min_sum=asset.balance,
                                    msg=msg)
            await state.set_state(StateSaleToken.selling_sum)
            await send_message(callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateSaleToken.selling_sum)
async def cmd_send_sale_sum(message: types.Message, state: FSMContext):
    try:
        send_sum = float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await state.set_state(StateSaleToken.selling_receive_sum)
        msg = my_gettext(message, 'send_cost_sale').format(data.get('receive_asset_code'),
                                                           send_sum,
                                                           data.get('send_asset_code'))
        await state.update_data(msg=msg)
        await send_message(message, msg, reply_markup=get_kb_return(message))
    else:
        await send_message(message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.message(StateSaleToken.selling_receive_sum)
async def cmd_send_sale_cost(message: types.Message, state: FSMContext):
    try:
        receive_sum = float(message.text)
    except:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.update_data(receive_sum=receive_sum)
        await state.set_state(None)

        await cmd_xdr_order(message, state)
    else:
        await send_message(message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


async def cmd_xdr_order(message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get('send_sum')
    receive_sum = data.get('receive_sum')
    send_asset = data.get('send_asset_code')
    send_asset_code = data.get('send_asset_issuer')
    receive_asset = data.get('receive_asset_code')
    receive_asset_code = data.get('receive_asset_issuer')
    offer_id = int(data.get('edit_offer_id', 0))
    xdr = stellar_sale(stellar_get_user_account(message.from_user.id).account.account_id,
                       Asset(send_asset, send_asset_code),
                       str(send_sum), Asset(receive_asset, receive_asset_code), str(receive_sum), offer_id)
    msg = my_gettext(message, 'confirm_sale').format(send_sum, send_asset, receive_sum, receive_asset)
    await state.update_data(xdr=xdr)
    await send_message(message, msg, reply_markup=get_kb_yesno_send_xdr(message))


# **************************************************************************
# **************************************************************************
# **************************************************************************
# edit

@router.callback_query(Text(text=["ShowOrders"]))
async def cmd_show_orders(callback: types.CallbackQuery, state: FSMContext):
    offers = stellar_get_offers(callback.from_user.id)
    await state.update_data(offers=offers)

    kb_tmp = []
    for offer in offers:
        kb_tmp.append([types.InlineKeyboardButton(
            text=f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) "
                 f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}",
            callback_data=EditOrderCallbackData(
                answer=offer.id).pack()
        )])
    kb_tmp.append(get_return_button(callback))
    await send_message(callback, 'Choose order', reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))


@router.callback_query(EditOrderCallbackData.filter())
async def cb_edit_order(callback: types.CallbackQuery, callback_data: EditOrderCallbackData, state: FSMContext):
    answer = callback_data.answer
    await state.update_data(edit_offer_id=answer)

    data = await state.get_data()
    offers = data.get('offers')
    offer_id = int(answer)

    offer = list(filter(lambda x: x.id == offer_id, offers))
    if offer:
        offer = offer[0]
        msg = f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) " \
              f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}"

        await send_message(callback, msg, reply_markup=get_kb_edir_order(callback.from_user.id))

    await callback.answer()


def get_kb_edir_order(user_id: int) -> types.InlineKeyboardMarkup:
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_edit_sum'),
                                    callback_data="EditOrderAmount")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_edit_price'),
                                    callback_data="EditOrderCost")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete'),
                                    callback_data="DeleteOrder")],
        get_return_button(user_id)
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(Text(text=["EditOrderAmount"]))
async def cmd_edit_order_amount(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offers = data.get('offers')
    offer_id = int(data.get('edit_offer_id', 0))

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        offer: MyOffer = tmp[0]
        msg = f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) " \
              f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}\n"

        await state.set_state(StateSaleToken.editing_amount)
        await state.update_data(send_sum=offer.amount,
                                receive_sum=float(offer.amount) * float(offer.price),
                                send_asset_code=offer.selling.asset_code,
                                send_asset_issuer=offer.selling.asset_issuer,
                                receive_asset_code=offer.buying.asset_code,
                                receive_asset_issuer=offer.buying.asset_issuer)
        data = await state.get_data()
        msg = msg + my_gettext(callback, 'send_sum_swap').format(data.get('send_asset_code'),
                                                                 data.get('send_asset_max_sum', 0.0),
                                                                 data.get('receive_asset_code'))

        await state.update_data(msg=msg)
        await send_message(callback, msg, reply_markup=get_kb_return(callback))
        await callback.answer()
    else:
        await callback.answer('EditOrder for amount not found =(')


@router.message(StateSaleToken.editing_amount)
async def cmd_edit_sale_sum(message: types.Message, state: FSMContext):
    try:
        send_sum = float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        receive_sum = data.get('receive_sum', 1)
        old_sum = data.get('send_sum', 1)
        await state.update_data(send_sum=send_sum, receive_sum=float(receive_sum) * float(send_sum) / float(old_sum))

        await state.set_state(None)

        await cmd_xdr_order(message, state)
    else:
        await send_message(message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(Text(text=["EditOrderCost"]))
async def cmd_edit_order_price(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offers = data.get('offers')
    offer_id = int(data.get('edit_offer_id', 0))

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        offer: MyOffer = tmp[0]
        msg = f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) " \
              f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}\n"

        await state.set_state(StateSaleToken.editing_price)
        await state.update_data(send_sum=offer.amount,
                                receive_sum=float(offer.amount) * float(offer.price),
                                send_asset_code=offer.selling.asset_code,
                                send_asset_issuer=offer.selling.asset_issuer,
                                receive_asset_code=offer.buying.asset_code,
                                receive_asset_issuer=offer.buying.asset_issuer)
        data = await state.get_data()
        msg = msg + my_gettext(callback, 'send_cost_sale').format(data.get('receive_asset_code'),
                                                                  data.get('send_sum', 0.0),
                                                                  data.get('send_asset_code'))

        await state.update_data(msg=msg)
        await send_message(callback, msg, reply_markup=get_kb_return(callback))
        await callback.answer()
    else:
        await callback.answer('EditOrder for amount not found =(')


@router.message(StateSaleToken.editing_amount)
async def cmd_edit_sale_cost(message: types.Message, state: FSMContext):
    try:
        receive_sum = float(message.text)
    except:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.update_data(receive_sum=receive_sum)

        await state.set_state(None)

        await cmd_xdr_order(message, state)
    else:
        await send_message(message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(Text(text=["DeleteOrder"]))
async def cmd_delete_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offers = data.get('offers')
    offer_id = int('edit_offer_id', 0)

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        offer: MyOffer = tmp[0]
        msg = f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) "
        f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}\n"

        await state.update_data(send_sum=0, receive_sum=0,
                                send_asset_code=offer.selling.asset_code,
                                send_asset_issuer=offer.selling.asset_issuer,
                                receive_asset_code=offer.buying.asset_code,
                                receive_asset_issuer=offer.buying.asset_issuer)

        await cmd_xdr_order(callback, state)
    else:
        await callback.answer('DeleteOrder not found =(')
    await callback.answer()
