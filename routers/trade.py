import jsonpickle  # type: ignore
from typing import List, Union

from infrastructure.services.app_context import AppContext
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.ext.asyncio import AsyncSession
from stellar_sdk import Asset

from infrastructure.utils.telegram_utils import my_gettext, send_message
from keyboards.common_keyboards import get_kb_return, get_kb_yesno_send_xdr, get_return_button
from other.mytypes import Balance, MyOffer
from infrastructure.utils.stellar_utils import my_float, stellar_get_market_link
from infrastructure.utils.common_utils import float2str
from other.asset_visibility_tools import get_asset_visibility, ASSET_VISIBLE, ASSET_EXCHANGE_ONLY
from core.domain.value_objects import Asset as DomainAsset
from loguru import logger


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
router.message.filter(F.chat.type == "private")


@router.callback_query(F.data == "Market")
async def cmd_market(callback: types.CallbackQuery, session: AsyncSession, app_context: AppContext):
    if callback.message is None or callback.message.chat is None:
        await callback.answer()
        return
    await send_message(session, callback.message.chat.id, my_gettext(callback, 'kb_market', app_context=app_context),
                       reply_markup=get_kb_market(callback.message.chat.id, app_context=app_context), app_context=app_context)

    await callback.answer()


def get_kb_market(user_id: int, *, app_context: AppContext) -> types.InlineKeyboardMarkup:
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_new_order', app_context=app_context),
                                    callback_data="NewOrder")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_show_order', app_context=app_context),
                                    callback_data="ShowOrders")],
        get_return_button(user_id, app_context=app_context)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data == "NewOrder")
async def cmd_sale_new_order(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    # Use DI from app_context
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    use_case_factory = app_context.use_case_factory
    if use_case_factory is None:
        return
    use_case = use_case_factory.create_get_wallet_balance(session)
    asset_list = await use_case.execute(user_id=callback.from_user.id)
    
    # Check free XLM
    xlm = next((a for a in asset_list if a.asset_code == 'XLM'), None)
    if not xlm or xlm.balance is None or float(xlm.balance) <= 0.5:
        await callback.answer(my_gettext(callback, 'low_xlm', app_context=app_context), show_alert=True)
        return

    msg = my_gettext(callback, 'choose_token_sale', app_context=app_context)
    
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    vis_str = wallet.assets_visibility if wallet else None
    asset_list = [a for a in asset_list if get_asset_visibility(vis_str, a.asset_code) in (ASSET_VISIBLE, ASSET_EXCHANGE_ONLY)]

    kb_tmp = []
    for token in asset_list:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                  callback_data=SaleAssetCallbackData(
                                                      answer=token.asset_code).pack()
                                                  )])
    kb_tmp.append(get_return_button(callback, app_context=app_context))
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp), app_context=app_context)
    await state.update_data(assets=jsonpickle.encode(asset_list))
    await callback.answer()


@router.callback_query(SaleAssetCallbackData.filter())
async def cq_trade_choose_token_sell(callback: types.CallbackQuery, callback_data: SaleAssetCallbackData, state: FSMContext,
                               session: AsyncSession, app_context: AppContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])
    for asset in asset_list:
        if asset.asset_code == answer:
            if my_float(asset.balance) == 0.0:
                await callback.answer(my_gettext(callback, "zero_sum", app_context=app_context), show_alert=True)
            else:
                if asset.asset_code is None:
                    continue
                await state.update_data(send_asset_code=asset.asset_code,
                                        send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance)
                kb_tmp = []
                for token in asset_list:
                    kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                              callback_data=BuyAssetCallbackData(
                                                                  answer=token.asset_code).pack()
                                                              )])
                kb_tmp.append(get_return_button(callback, app_context=app_context))
                msg = my_gettext(callback, 'choose_token_swap2', (asset.asset_code,), app_context=app_context)
                await send_message(session, callback, msg,
                                   reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp), app_context=app_context)

    await callback.answer()


@router.callback_query(BuyAssetCallbackData.filter())
async def cq_trade_choose_token_buy(callback: types.CallbackQuery, callback_data: BuyAssetCallbackData, state: FSMContext,
                               session: AsyncSession, app_context: AppContext):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])
    for asset in asset_list:
        if asset.asset_code == answer:
            send_asset_code = data.get("send_asset_code")
            send_asset_issuer = data.get("send_asset_issuer")
            if send_asset_code is None or asset.asset_code is None:
                continue
                
            market_link = stellar_get_market_link(Asset(send_asset_code, send_asset_issuer),
                                                  Asset(asset.asset_code, asset.asset_issuer))
            msg = my_gettext(callback, 'send_sum_swap', (send_asset_code,
                                                         data.get('send_asset_max_sum', 0.0),
                                                         asset.asset_code,
                                                         market_link),
                                                         app_context=app_context
                             )
            await state.update_data(receive_asset_code=asset.asset_code,
                                    receive_asset_issuer=asset.asset_issuer,
                                    receive_asset_min_sum=asset.balance,
                                    msg=msg,
                                    market_link=market_link)
            await state.set_state(StateSaleToken.selling_sum)
            await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)


@router.message(StateSaleToken.selling_sum)
async def cmd_send_sale_sum(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    try:
        send_sum = my_float(message.text)
    except Exception:
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
                                                     ),
                                                     app_context=app_context
                         )
        await state.update_data(msg=msg)
        await send_message(session, message, msg, reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum', app_context=app_context) + '\n' + (data.get('msg') or ""),
                           reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        await message.delete()


@router.message(StateSaleToken.selling_receive_sum)
async def cmd_send_sale_cost(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    try:
        receive_sum = my_float(message.text)
    except Exception:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.update_data(receive_sum=receive_sum, msg=None)
        await state.set_state(None)

        await cmd_xdr_order(session, message, state, app_context=app_context)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum', app_context=app_context) + '\n' + (data.get('msg') or ""),
                           reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        await message.delete()


async def cmd_xdr_order(session: AsyncSession, message: Union[types.Message, types.CallbackQuery], state: FSMContext, *, app_context: AppContext):
    if message.from_user is None:
        return
    data = await state.get_data()

    send_sum = data.get('send_sum')
    receive_sum = data.get('receive_sum')
    send_asset = data.get('send_asset_code')
    send_asset_issuer = data.get('send_asset_issuer')
    receive_asset = data.get('receive_asset_code')
    receive_asset_issuer = data.get('receive_asset_issuer')
    offer_id = int(data.get('edit_offer_id', 0))
    delete_order = data.get('delete_order', False)

    if any(v is None for v in [send_sum, receive_sum, send_asset, receive_asset]):
         return

    assert send_sum is not None, "send_sum must not be None"
    assert receive_sum is not None, "receive_sum must not be None"
    assert send_asset is not None, "send_asset must not be None"
    assert receive_asset is not None, "receive_asset must not be None"
         
    price = 0.0
    amount = 0.0
    if delete_order:
        amount = 0.0
        price = 1.0 # Price 1 means nothing when amount is 0, but required by op
    else:
        if float(send_sum) > 0:
            price = float(receive_sum) / float(send_sum)
        else:
            price = 0 # Should not happen unless delete
            
        amount = float(send_sum)

    # Use DI from app_context
    use_case_factory = app_context.use_case_factory
    if use_case_factory is None:
        return
    use_case = use_case_factory.create_manage_offer(session)

    result = await use_case.execute(
        user_id=message.from_user.id,
        selling=DomainAsset(code=str(send_asset), issuer=send_asset_issuer),
        buying=DomainAsset(code=str(receive_asset), issuer=receive_asset_issuer),
        amount=amount,
        price=price,
        offer_id=offer_id
    )
    
    if result.success:
        xdr = result.xdr
    else:
        logger.error(f"ManageOffer failed: {result.error_message}")
        await send_message(session, message, f"Error: {result.error_message}", reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        return

    # if delete_order:
    #     xdr = await stellar_sale((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
    #                              Asset(send_asset, send_asset_code),
    #                              '0', Asset(receive_asset, receive_asset_code), str(receive_sum), offer_id)
    # else:
    #     xdr = await stellar_sale((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
    #                              Asset(send_asset, send_asset_code),
    #                              str(send_sum), Asset(receive_asset, receive_asset_code), str(receive_sum), offer_id)

    if delete_order:
        msg = my_gettext(message, 'delete_sale', (send_sum, send_asset, receive_sum, receive_asset), app_context=app_context)
    else:
        msg = my_gettext(message, 'confirm_sale', (send_sum, send_asset, receive_sum, receive_asset), app_context=app_context)
    await state.update_data(xdr=xdr, operation='trade', msg=None)
    await send_message(session, message, msg, reply_markup=get_kb_yesno_send_xdr(message, app_context=app_context), app_context=app_context)


# **************************************************************************
# **************************************************************************
# **************************************************************************
# edit

@router.callback_query(F.data == "ShowOrders")
async def cmd_show_orders(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    # Use DI from app_context
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    if not wallet:
        await callback.answer("Wallet not found")
        return
    offers_dicts = await app_context.stellar_service.get_selling_offers(wallet.public_key)
    offers = [MyOffer.from_dict(o) for o in offers_dicts]
    
    await state.update_data(offers=jsonpickle.encode(offers))

    kb_tmp = []
    for offer in offers:
        selling_code = offer.selling.asset_code if offer.selling else "Unknown"
        buying_code = offer.buying.asset_code if offer.buying else "Unknown"
        amount = float(offer.amount or 0)
        price = float(offer.price or 0)
        kb_tmp.append([types.InlineKeyboardButton(
            text=f"{amount} {selling_code} -> ({price}) "
                 f"-> {amount * price} {buying_code}",
            callback_data=EditOrderCallbackData(
                answer=offer.id or 0).pack()
        )])
    kb_tmp.append(get_return_button(callback, app_context=app_context))
    await send_message(session, callback, 'Choose order',
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp), app_context=app_context)
    await callback.answer()


@router.callback_query(EditOrderCallbackData.filter())
async def cb_edit_order(callback: types.CallbackQuery, callback_data: EditOrderCallbackData, state: FSMContext,
                        session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    answer = callback_data.answer
    await state.update_data(edit_offer_id=answer)

    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
    offer_id = int(answer)

    offer = list(filter(lambda x: x.id == offer_id, offers))
    if offer:
        o: MyOffer = offer[0]
        selling_code = o.selling.asset_code if o.selling else "Unknown"
        buying_code = o.buying.asset_code if o.buying else "Unknown"
        amount = float(o.amount or 0)
        price = float(o.price or 0)
        msg = f"{amount} {selling_code} -> ({price}) " \
              f"-> {amount * price} {buying_code}"

        await send_message(session, callback, msg, reply_markup=get_kb_edit_order(callback.from_user.id, app_context=app_context), app_context=app_context)

    await callback.answer()


def get_kb_edit_order(user_id: int, *, app_context: AppContext) -> types.InlineKeyboardMarkup:
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_edit_sum', app_context=app_context),
                                    callback_data="EditOrderAmount")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_edit_price', app_context=app_context),
                                    callback_data="EditOrderCost")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete', app_context=app_context),
                                    callback_data="DeleteOrder")],
        get_return_button(user_id, app_context=app_context)
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data == "EditOrderAmount")
async def cmd_edit_order_amount(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
    offer_id = int(data.get('edit_offer_id', 0))

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        o: MyOffer = tmp[0]
        selling_code = o.selling.asset_code if o.selling else "Unknown"
        buying_code = o.buying.asset_code if o.buying else "Unknown"
        amount = float(o.amount or 0)
        price = float(o.price or 0)
        msg = f"{amount} {selling_code} -> ({price}) " \
              f"-> {amount * price} {buying_code}\n"

        await state.set_state(StateSaleToken.editing_amount)
        await state.update_data(send_sum=o.amount,
                                receive_sum=amount * price,
                                send_asset_code=selling_code,
                                send_asset_issuer=o.selling.asset_issuer if o.selling else None,
                                receive_asset_code=buying_code,
                                receive_asset_issuer=o.buying.asset_issuer if o.buying else None)
        try:
            # Use DI from app_context
            use_case_factory = app_context.use_case_factory
            if use_case_factory:
                balance_use_case = use_case_factory.create_get_wallet_balance(session)
                balances = await balance_use_case.execute(callback.from_user.id)
                target_obj = next((b for b in balances if b.asset_code == selling_code), None)
                max_balance = target_obj.balance if target_obj else "not found =("
            else:
                max_balance = '"not found =("'
        except Exception:
            max_balance = '"not found =("'

        data = await state.get_data()
        send_asset_code = data.get('send_asset_code')
        send_asset_issuer = data.get('send_asset_issuer')
        receive_asset_code = data.get('receive_asset_code')
        receive_asset_issuer = data.get('receive_asset_issuer')
        
        if send_asset_code and receive_asset_code:
            msg = msg + my_gettext(callback, 'send_sum_swap', (send_asset_code,
                                                               max_balance,
                                                               receive_asset_code,
                                                               stellar_get_market_link(Asset(send_asset_code,
                                                                                             send_asset_issuer),
                                                                                       Asset(receive_asset_code,
                                                                                             receive_asset_issuer))
                                                               ),
                                                               app_context=app_context
                                                               )

        await state.update_data(msg=msg)
        await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)
        await callback.answer()
    else:
        await callback.answer('EditOrder for amount not found =(')


@router.message(StateSaleToken.editing_amount)
async def cmd_edit_sale_sum(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    try:
        send_sum = my_float(message.text)
    except Exception:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        receive_sum = data.get('receive_sum', 1)
        old_sum = data.get('send_sum', 1)
        await state.update_data(send_sum=send_sum, receive_sum=float(receive_sum) * float(send_sum) / float(old_sum),
                                msg=None)

        await state.set_state(None)

        await cmd_xdr_order(session, message, state, app_context=app_context)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum', app_context=app_context) + '\n' + data['msg'],
                           reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        await message.delete()


@router.callback_query(F.data == "EditOrderCost")
async def cmd_edit_order_price(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
    offer_id = int(data.get('edit_offer_id', 0))

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        o: MyOffer = tmp[0]
        selling_code = o.selling.asset_code if o.selling else "Unknown"
        buying_code = o.buying.asset_code if o.buying else "Unknown"
        amount = float(o.amount or 0)
        price = float(o.price or 0)
        msg = f"{amount} {selling_code} -> ({price}) " \
              f"-> {amount * price} {buying_code}\n"

        await state.set_state(StateSaleToken.editing_price)
        await state.update_data(send_sum=o.amount,
                                receive_sum=amount * price,
                                send_asset_code=selling_code,
                                send_asset_issuer=o.selling.asset_issuer if o.selling else None,
                                receive_asset_code=buying_code,
                                receive_asset_issuer=o.buying.asset_issuer if o.buying else None)
        data = await state.get_data()
        send_asset_code = data.get('send_asset_code')
        send_asset_issuer = data.get('send_asset_issuer')
        receive_asset_code = data.get('receive_asset_code')
        receive_asset_issuer = data.get('receive_asset_issuer')
        
        if send_asset_code and receive_asset_code:
            msg = msg + my_gettext(callback, 'send_cost_sale', (receive_asset_code,
                                                                data.get('send_sum', 0.0),
                                                                send_asset_code,
                                                                stellar_get_market_link(Asset(send_asset_code,
                                                                                              send_asset_issuer),
                                                                                        Asset(receive_asset_code,
                                                                                              receive_asset_issuer))
                                                                ),
                                                                app_context=app_context
                                                                )

        await state.update_data(msg=msg)
        await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)
        await callback.answer()
    else:
        await callback.answer('EditOrder for amount not found =(')


@router.message(StateSaleToken.editing_price)
async def cmd_edit_sale_cost(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    try:
        receive_sum = my_float(message.text)
    except Exception:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.update_data(receive_sum=receive_sum, msg=None)

        await state.set_state(None)

        await cmd_xdr_order(session, message, state, app_context=app_context)
        await message.delete()
    else:
        await send_message(session, message, my_gettext(message, 'bad_sum', app_context=app_context) + '\n' + (data.get('msg') or ""),
                           reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        await message.delete()


@router.callback_query(F.data == "DeleteOrder")
async def cmd_delete_order(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    offers = jsonpickle.decode(data['offers'])
    offer_id = int(data.get('edit_offer_id', 0))

    tmp = list(filter(lambda x: x.id == offer_id, offers))
    if tmp:
        o: MyOffer = tmp[0]
        selling_code = o.selling.asset_code if o.selling else "Unknown"
        buying_code = o.buying.asset_code if o.buying else "Unknown"
        amount = float(o.amount or 0)
        price = float(o.price or 0)

        await state.update_data(send_sum=o.amount,
                                receive_sum=amount * price,
                                send_asset_code=selling_code,
                                send_asset_issuer=o.selling.asset_issuer if o.selling else None,
                                receive_asset_code=buying_code,
                                receive_asset_issuer=o.buying.asset_issuer if o.buying else None,
                                delete_order=True)

        await cmd_xdr_order(session, callback, state, app_context=app_context)
    else:
        await callback.answer('DeleteOrder not found =(')
    await callback.answer()
