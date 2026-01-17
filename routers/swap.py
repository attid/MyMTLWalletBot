from typing import List

import jsonpickle
from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session
from stellar_sdk import Asset
from loguru import logger


from infrastructure.utils.telegram_utils import my_gettext, send_message
from keyboards.common_keyboards import get_kb_yesno_send_xdr, get_return_button, get_kb_offers_cancel, get_kb_return
from other.mytypes import Balance
from other.asset_visibility_tools import get_asset_visibility, ASSET_VISIBLE, ASSET_EXCHANGE_ONLY
from infrastructure.utils.common_utils import float2str
from other.stellar_tools import stellar_check_receive_asset, \
    stellar_check_receive_sum, stellar_get_market_link, my_float, \
    my_round, stellar_check_send_sum

from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.services.stellar_service import StellarService
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.use_cases.trade.swap_assets import SwapAssets
from core.domain.value_objects import Asset as DomainAsset
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from other.config_reader import config


class StateSwapToken(StatesGroup):
    swap_sum = State()
    swap_receive_sum = State()  # State for entering strict receive amount


class SwapAssetFromCallbackData(CallbackData, prefix="SwapAssetFromCallbackData"):
    answer: str


def build_swap_confirm_message(
    obj,  # message or callback
    send_sum,
    send_asset,
    receive_sum,
    receive_asset,
    scenario="send",  # "send" или "receive"
    need_alert=False,
    cancel_offers=False
):
    """
    Builds swap confirmation message for both scenarios.
    scenario: "send" — guaranteed send amount, "receive" — guaranteed receive amount.
    """
    # Always use confirm_swap, but mark receive_sum as approximate in "send" scenario
    if scenario == "send":
        receive_sum = f"{receive_sum}*"
    elif scenario == "receive":
        send_sum = f"{send_sum}*"
    msg = my_gettext(
        obj,
        "confirm_swap",
        (send_sum, send_asset, receive_sum, receive_asset)
    )
    if need_alert:
        msg = my_gettext(obj, 'swap_alert') + msg
    if cancel_offers:
        msg = msg + my_gettext(obj, 'confirm_cancel_offers', (send_asset,))
    return msg



class SwapAssetForCallbackData(CallbackData, prefix="SwapAssetForCallbackData"):
    answer: str


router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(F.data == "Swap")
async def cmd_swap_01(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'choose_token_swap')
    
    # Refactored to use GetWalletBalance Use Case
    repo = SqlAlchemyWalletRepository(session)
    service = StellarService(horizon_url=config.horizon_url)
    use_case = GetWalletBalance(repo, service)
    asset_list = await use_case.execute(user_id=callback.from_user.id)
    
    wallet = await repo.get_default_wallet(callback.from_user.id)
    vis_str = wallet.assets_visibility if wallet else None
    asset_list = [a for a in asset_list if get_asset_visibility(vis_str, a.asset_code) in (ASSET_VISIBLE, ASSET_EXCHANGE_ONLY)]

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

                # Get summ of tokens, blocked by Sell offers 
                repo = SqlAlchemyWalletRepository(session)
                wallet = await repo.get_default_wallet(callback.from_user.id)
                service = StellarService(horizon_url=config.horizon_url)
                offers = await service.get_selling_offers(wallet.public_key)
                blocked_token_sum = 0.0
                for offer in offers:
                    selling = offer.get('selling', {})
                    s_code = selling.get('asset_code')
                    s_issuer = selling.get('asset_issuer')
                    if s_code == asset.asset_code and s_issuer == asset.asset_issuer:
                        blocked_token_sum += float(offer.get('amount', 0))

                await state.update_data(send_asset_code=asset.asset_code, send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance, send_asset_blocked_sum=blocked_token_sum)

                msg = my_gettext(callback, 'choose_token_swap2', (asset.asset_code,))

                kb_tmp = []
                asset_list2 = []
                
                # Initialize repository for wallet lookup
                # Imports moved to top
                
                repo = SqlAlchemyWalletRepository(session)
                wallet = await repo.get_default_wallet(callback.from_user.id)
                vis_str = wallet.assets_visibility if wallet else None

                service = StellarService(horizon_url=config.horizon_url)
                balance_use_case = GetWalletBalance(repo, service)
                for token in await balance_use_case.execute(user_id=callback.from_user.id):
                    if get_asset_visibility(vis_str, token.asset_code) in (ASSET_VISIBLE, ASSET_EXCHANGE_ONLY):
                        asset_list2.append(Asset(token.asset_code, token.asset_issuer))
                swap_possible_sum = '1' if my_float(asset.balance) > 0 else asset.balance # try dont lose path for nfts
                receive_assets = await stellar_check_receive_asset(Asset(asset.asset_code, asset.asset_issuer), swap_possible_sum,
                                                                    asset_list2)
                receive_assets = sorted(receive_assets, key=lambda x: str(x))  # Sort by token name

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

            # If user has some assets that are blocked by offers, remind him\her about it.
            blocked_sum = data.get('send_asset_blocked_sum')
            if blocked_sum > 0:
                msg += '\n\n' + my_gettext(
                    callback,
                    'swap_summ_blocked_by_offers',
                    (blocked_sum, data.get('send_asset_code'))
                )

            # Change state and show message
            await state.set_state(StateSwapToken.swap_sum)
            await state.update_data(msg=msg)

            # Use swap confirm keyboard with strict receive button
            from keyboards.common_keyboards import get_kb_swap_confirm
            keyboard = get_kb_swap_confirm(callback.from_user.id, data)
            await send_message(session, callback, msg, reply_markup=keyboard)
    await callback.answer()

# Handle "Specify exact amount to receive" button
@router.callback_query(StateSwapToken.swap_sum, F.data == "SwapStrictReceive")
async def cq_swap_strict_receive(callback: types.CallbackQuery, state: FSMContext, session: Session):
    """
    Switch FSM to strict receive state and ask user to enter amount to receive.
    """
    await state.set_state(StateSwapToken.swap_receive_sum)
    await callback.answer()
    data = await state.get_data()
    msg = my_gettext(callback, "enter_strict_receive_sum", (
        data.get('receive_asset_code', ''),
    ))
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))


@router.callback_query(StateSwapToken.swap_sum, F.data == "CancelOffers")
async def cq_swap_cancel_offers_click(callback: types.CallbackQuery, state: FSMContext, session: Session):
    """
        Handle callback event 'CancelOffers_swap' in state 'swap_sum'.
        Invert state of 'cancel offers' flag by clicking on button.
    """
    data = await state.get_data()
    data['cancel_offers'] = not data.get('cancel_offers', False)  # Invert checkbox state
    await state.update_data(cancel_offers=data['cancel_offers'])

    # Update message with the same text and changed button checkbox state
    msg = data['msg']
    keyboard = get_kb_offers_cancel(callback.from_user.id, data)
    await send_message(session, callback, msg, reply_markup=keyboard)


@router.message(StateSwapToken.swap_sum)
async def cmd_swap_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
        from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
        user_repo = SqlAlchemyUserRepository(session)
        db_user = await user_repo.get_by_id(message.from_user.id)
        if db_user and db_user.can_5000 == 0 and send_sum > 5000:
            data = await state.get_data()
            msg0 = my_gettext(message, 'need_update_limits')
            await send_message(session, message, msg0 + data['msg'], reply_markup=get_kb_return(message))
            await message.delete()
            return
    except:
        send_sum = 0.0

    data = await state.get_data()
    if send_sum > 0.0:
        await state.set_state(None)
        send_asset = data.get('send_asset_code')
        send_asset_code = data.get('send_asset_issuer')
        receive_asset = data.get('receive_asset_code')
        receive_asset_code = data.get('receive_asset_issuer')
        cancel_offers = data.get('cancel_offers', False)
        xdr = data.get('xdr')

        receive_sum, need_alert = await stellar_check_receive_sum(Asset(send_asset, send_asset_code),
                                                                  float2str(send_sum),
                                                                  Asset(receive_asset, receive_asset_code))
        if float(receive_sum) > 10:
            receive_sum = float2str(my_round(float(receive_sum), 3))

        # Refactored to use Clean Architecture Use Case
        repo = SqlAlchemyWalletRepository(session)
        service = StellarService(horizon_url=config.horizon_url)
        use_case = SwapAssets(repo, service)

        result = await use_case.execute(
            user_id=message.from_user.id,
            send_asset=DomainAsset(code=send_asset, issuer=send_asset_code),
            send_amount=send_sum,
            receive_asset=DomainAsset(code=receive_asset, issuer=receive_asset_code),
            receive_amount=my_float(receive_sum),
            strict_receive=False,
            cancel_offers=cancel_offers
        )

        if result.success:
            xdr = result.xdr
        else:
             # Fallback
             logger.error(f"SwapAssets failed: {result.error_message}")
             keyboard = get_kb_offers_cancel(message.from_user.id, data)
             await send_message(session, message, my_gettext(message, 'bad_sum') + f"\n{result.error_message}", reply_markup=keyboard)
             await message.delete()
             return

        # xdr = await stellar_swap(
        #     from_account=(await stellar_get_user_account(session, message.from_user.id)).account.account_id,
        #     send_asset=Asset(send_asset, send_asset_code),
        #     send_amount=float2str(send_sum),
        #     receive_asset=Asset(receive_asset, receive_asset_code),
        #     receive_amount=receive_sum,
        #     xdr=xdr,
        #     cancel_offers=cancel_offers,
        #     use_strict_receive=False
        # )

        # Add msg about cancelling offers to the confirmation request
        msg = my_gettext(
            message,
            'confirm_swap',
            (float2str(send_sum), send_asset, receive_sum, receive_asset)
        )
        if need_alert:
            msg = my_gettext(message, 'swap_alert') + msg

        if cancel_offers:
            msg = msg + my_gettext(message, 'confirm_cancel_offers', (send_asset,))

        await state.update_data(xdr=xdr, operation='swap', msg=None)
        await send_message(session, message, msg, reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        keyboard = get_kb_offers_cancel(message.from_user.id, data)
        await send_message(session, message, my_gettext(message, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=keyboard)

# Handle input of amount to receive (strict receive)
@router.message(StateSwapToken.swap_receive_sum)
async def cmd_swap_receive_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        receive_sum = my_float(message.text)
        from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
        user_repo = SqlAlchemyUserRepository(session)
        db_user = await user_repo.get_by_id(message.from_user.id)
        if db_user and db_user.can_5000 == 0 and receive_sum > 5000:
            data = await state.get_data()
            msg0 = my_gettext(message, 'need_update_limits')
            await send_message(session, message, msg0, reply_markup=get_kb_return(message))
            await message.delete()
            return
    except:
        receive_sum = 0.0

    data = await state.get_data()
    if receive_sum > 0.0:
        await state.set_state(None)
        send_asset = data.get('send_asset_code')
        send_asset_code = data.get('send_asset_issuer')
        receive_asset = data.get('receive_asset_code')
        receive_asset_code = data.get('receive_asset_issuer')
        cancel_offers = data.get('cancel_offers', False)
        xdr = data.get('xdr')

         # Calculate required send_sum to get the desired receive_sum
        send_sum, need_alert = await stellar_check_send_sum(
            Asset(send_asset, send_asset_code),
            float2str(receive_sum),
            Asset(receive_asset, receive_asset_code)
        )
        max_send_amount = my_round(my_float(send_sum) * 1.001, 7)
        if my_float(max_send_amount) == 0.0:
            keyboard = get_kb_return(message)
            await send_message(session, message, my_gettext(message, 'bad_sum'), reply_markup=keyboard)
            await message.delete()
            return

        try:
            # Build XDR with strict receive, using max_send_amount as send_amount
            # Refactored to use Clean Architecture Use Case
            repo = SqlAlchemyWalletRepository(session)
            service = StellarService(horizon_url=config.horizon_url)
            use_case = SwapAssets(repo, service)

            result = await use_case.execute(
                user_id=message.from_user.id,
                send_asset=DomainAsset(code=send_asset, issuer=send_asset_code),
                send_amount=max_send_amount,
                receive_asset=DomainAsset(code=receive_asset, issuer=receive_asset_code),
                receive_amount=receive_sum,
                strict_receive=True,
                cancel_offers=cancel_offers
            )

            if result.success:
                xdr = result.xdr
            else:
                 raise Exception(result.error_message)

            # xdr = await stellar_swap(
            #     from_account=(await stellar_get_user_account(session, message.from_user.id)).account.account_id,
            #     send_asset=Asset(send_asset, send_asset_code),
            #     send_amount=float2str(max_send_amount),
            #     receive_asset=Asset(receive_asset, receive_asset_code),
            #     receive_amount=float2str(receive_sum),
            #     xdr=xdr,
            #     cancel_offers=cancel_offers,
            #     use_strict_receive=True
            # )
            scenario = "receive"
            need_alert = False
        except Exception as ex:
            keyboard = get_kb_return(message)
            await send_message(session, message, my_gettext(message, 'bad_sum') + f"\n{ex}", reply_markup=keyboard)
            await message.delete()
            return

        # Confirmation window for strict receive: show both estimated and max send amount
        msg = build_swap_confirm_message(
            message,
            send_sum=float2str(send_sum),
            send_asset=send_asset,
            receive_sum=float2str(receive_sum),
            receive_asset=receive_asset,
            scenario=scenario,
            need_alert=need_alert,
            cancel_offers=cancel_offers
        )

        await state.update_data(xdr=xdr, operation='swap', msg=None)
        await send_message(session, message, msg, reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        keyboard = get_kb_return(message)
        await send_message(session, message, my_gettext(message, 'bad_sum'), reply_markup=keyboard)
        await message.delete()
