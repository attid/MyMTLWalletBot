import jsonpickle
from typing import List
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session
from stellar_sdk import Asset

from utils.aiogram_utils import my_gettext, send_message
from keyboards.common_keyboards import get_kb_return, get_kb_yesno_send_xdr, get_return_button
from utils.mytypes import Balance, MyOffer
from utils.stellar_utils import stellar_get_balances, stellar_get_user_account, stellar_sale, stellar_get_offers, \
    stellar_get_market_link, my_float, float2str, have_free_xlm


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


@router.callback_query(F.data == "Market")
async def cmd_market(callback: types.CallbackQuery, session: Session):
    await send_message(session, callback.message.chat.id, my_gettext(callback, 'kb_market'),
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


@router.callback_query(F.data == "NewOrder")
async def cmd_sale_new_order(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if not await have_free_xlm(session=session, state=state, user_id = callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return

    msg = my_gettext(callback, 'choose_token_sale')
    asset_list = await stellar_get_balances(session, callback.from_user.id)

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                  callback_data=SaleAssetCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))
    await state.update_data(assets=jsonpickle.encode(asset_list))
    await callback.answer()


@router.callback_query(SaleAssetCallbackData.filter())
async def cq_send_choose_token(callback: types.CallbackQuery, callback_data: SaleAssetCallbackData, state: FSMContext,
                               session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])
    for asset in asset_list:
        if asset.asset_code == answer:
            if my_float(asset.balance) == 0.0:
                await callback.answer(my_gettext(callback, "zero_sum"), show_alert=True)
            else:
                await state.update_data(send_asset_code=asset.asset_code,
                                        send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance)
                kb_tmp = []
                for token in asset_list:
                    kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                              callback_data=BuyAssetCallbackData(
                                                                  answer=token.asset_code).pack()
                                                              )])
                kb_tmp.append(get_return_button(callback))
                msg = my_gettext(callback, 'choose_token_swap2', (asset.asset_code,))
                await send_message(session, callback, msg,
                                   reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))

    await callback.answer()


@router.callback_query(BuyAssetCallbackData.filter())
async def cq_send_choose_token(callback: types.CallbackQuery, callback_data: BuyAssetCallbackData, state: FSMContext,
                               session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])
    for asset in asset_list:
        if asset.asset_code == answer:
            market_link = stellar_get_market_link(Asset(data.get("send_asset_code"), data.get("send_asset_issuer")),
                                                  Asset(asset.asset_code, asset.asset_issuer))
            msg = my_gettext(callback, 'send_sum_swap', (data.get('send_asset_code'),
                                                         data.get('send_asset_max_sum', 0.0),
                                                         asset.asset_code,
                                                         market_link)
                             )
            await state.update_data(receive_asset_code=asset.asset_code,
                                    receive_asset_issuer=asset.asset_issuer,
                                    receive_asset_min_sum=asset.balance,
                                    msg=msg,
                                    market_link=market_link)
            await state.set_state(StateSaleToken.selling_sum)
            await send_message(session, callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateSaleToken.selling_sum)
async def cmd_send_sale_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await state.set_state(StateSaleToken.selling_receive_sum)
        msg = my_gettext(message, 'send_cost_sale', (data.get('receive_asset_code'),
                                                     send_sum,
                                                     data.get('send_asset_code'),
                                                     data.get('market_link')
                                                     )
                         )
        await state.update_data(msg=msg)
        await send_message(session, message, msg, reply_markup=get_kb_return(message))
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))
        await message.delete()


@router.message(StateSaleToken.selling_receive_sum)
async def cmd_send_sale_cost(message: types.Message, state: FSMContext, session: Session):
    try:
        receive_sum = my_float(message.text)
    except:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.update_data(receive_sum=receive_sum, msg=None)
        await state.set_state(None)

        await cmd_xdr_order(session, message, state)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))
        await message.delete()


async def cmd_xdr_order(session: Session, message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get('send_sum')
    receive_sum = data.get('receive_sum')
    send_asset = data.get('send_asset_code')
    send_asset_code = data.get('send_asset_issuer')
    receive_asset = data.get('receive_asset_code')
    receive_asset_code = data.get('receive_asset_issuer')
    offer_id = int(data.get('edit_offer_id', 0))
    delete_order = data.get('delete_order', False)
    if delete_order:
        xdr = await stellar_sale((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                                 Asset(send_asset, send_asset_code),
                                 '0', Asset(receive_asset, receive_asset_code), str(receive_sum), offer_id)
    else:
        xdr = await stellar_sale((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                                 Asset(send_asset, send_asset_code),
                                 str(send_sum), Asset(receive_asset, receive_asset_code), str(receive_sum), offer_id)

    if delete_order:
        msg = my_gettext(message, 'delete_sale', (send_sum, send_asset, receive_sum, receive_asset))
    else:
        msg = my_gettext(message, 'confirm_sale', (send_sum, send_asset, receive_sum, receive_asset))
    await state.update_data(xdr=xdr, operation='trade', msg=None)
    await send_message(session, message, msg, reply_markup=get_kb_yesno_send_xdr(message))


# **************************************************************************
# **************************************************************************
# **************************************************************************
# edit

@router.callback_query(F.data == "ShowOrders")
async def cmd_show_orders(callback: types.CallbackQuery, state: FSMContext, session: Session):
    offers = await stellar_get_offers(session, callback.from_user.id)
    await state.update_data(offers=jsonpickle.encode(offers))

    kb_tmp = []
    for offer in offers:
        kb_tmp.append([types.InlineKeyboardButton(
            text=f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) "
                 f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}",
            callback_data=EditOrderCallbackData(
                answer=offer.id).pack()
        )])
    kb_tmp.append(get_return_button(callback))
    await send_message(session, callback, 'Choose order',
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp))


@router.callback_query(EditOrderCallbackData.filter())
async def cb_edit_order(callback: types.CallbackQuery, callback_data: EditOrderCallbackData, state: FSMContext,
                        session: Session):
    answer = callback_data.answer
    await state.update_data(edit_offer_id=answer)

    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
    offer_id = int(answer)

    offer = list(filter(lambda x: x.id == offer_id, offers))
    if offer:
        offer = offer[0]
        msg = f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) " \
              f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}"

        await send_message(session, callback, msg, reply_markup=get_kb_edir_order(callback.from_user.id))

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


@router.callback_query(F.data == "EditOrderAmount")
async def cmd_edit_order_amount(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
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
        try:
            max_balance = (await stellar_get_balances(session, callback.from_user.id,
                                                      asset_filter=data.get('send_asset_code')))[0].balance
        except:
            max_balance = '"not found =("'

        data = await state.get_data()
        msg = msg + my_gettext(callback, 'send_sum_swap', (data.get('send_asset_code'),
                                                           max_balance,
                                                           data.get('receive_asset_code'),
                                                           stellar_get_market_link(Asset(data.get("send_asset_code"),
                                                                                         data.get("send_asset_issuer")),
                                                                                   Asset(data.get('receive_asset_code'),
                                                                                         data.get(
                                                                                             'receive_asset_issuer')))
                                                           ))

        await state.update_data(msg=msg)
        await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
        await callback.answer()
    else:
        await callback.answer('EditOrder for amount not found =(')


@router.message(StateSaleToken.editing_amount)
async def cmd_edit_sale_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        receive_sum = data.get('receive_sum', 1)
        old_sum = data.get('send_sum', 1)
        await state.update_data(send_sum=send_sum, receive_sum=float(receive_sum) * float(send_sum) / float(old_sum),
                                msg=None)

        await state.set_state(None)

        await cmd_xdr_order(session, message, state)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))
        await message.delete()


@router.callback_query(F.data == "EditOrderCost")
async def cmd_edit_order_price(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
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
        msg = msg + my_gettext(callback, 'send_cost_sale', (data.get('receive_asset_code'),
                                                            data.get('send_sum', 0.0),
                                                            data.get('send_asset_code'),
                                                            stellar_get_market_link(Asset(data.get("send_asset_code"),
                                                                                          data.get(
                                                                                              "send_asset_issuer")),
                                                                                    Asset(
                                                                                        data.get('receive_asset_code'),
                                                                                        data.get(
                                                                                            'receive_asset_issuer')))
                                                            ))

        await state.update_data(msg=msg)
        await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
        await callback.answer()
    else:
        await callback.answer('EditOrder for amount not found =(')


@router.message(StateSaleToken.editing_price)
async def cmd_edit_sale_cost(message: types.Message, state: FSMContext, session: Session):
    try:
        receive_sum = my_float(message.text)
    except:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.update_data(receive_sum=receive_sum, msg=None)

        await state.set_state(None)

        await cmd_xdr_order(session, message, state)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))
        await message.delete()


@router.callback_query(F.data == "DeleteOrder")
async def cmd_delete_order(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
    offer_id = int(data.get('edit_offer_id', 0))

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        offer: MyOffer = tmp[0]
        msg = f"{float(offer.amount)} {offer.selling.asset_code} -> ({float(offer.price)}) "
        f"-> {float(offer.amount) * float(offer.price)} {offer.buying.asset_code}\n"

        await state.update_data(send_sum=offer.amount,
                                receive_sum=float(offer.amount) * float(offer.price),
                                send_asset_code=offer.selling.asset_code,
                                send_asset_issuer=offer.selling.asset_issuer,
                                receive_asset_code=offer.buying.asset_code,
                                receive_asset_issuer=offer.buying.asset_issuer,
                                delete_order=True)

        await cmd_xdr_order(session, callback, state)
    else:
        await callback.answer('DeleteOrder not found =(')
    await callback.answer()
