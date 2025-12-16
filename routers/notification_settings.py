import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session
from db.requests import db_get_operation
from keyboards.common_keyboards import get_return_button, HideNotificationCallbackData
from other.aiogram_tools import send_message
from db.models import NotificationFilter, TOperations, MyMtlWalletBot
from other.lang_tools import my_gettext

router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(HideNotificationCallbackData.filter())
async def hide_notification_callback(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = HideNotificationCallbackData.unpack(callback.data)

    wallet = session.query(MyMtlWalletBot).filter(MyMtlWalletBot.id == data.wallet_id).first()
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("Wallet not found.", show_alert=True)
        return

    public_key = wallet.public_key

    operation = await asyncio.to_thread(db_get_operation, session, data.operation_id)
    if not operation:
        await callback.answer("Operation details not found.", show_alert=True)
        return

    await state.update_data(operation_id=data.operation_id, public_key=public_key,
                            asset_code=operation.code1, min_amount=float(operation.amount1),
                            operation_type=operation.operation, for_all_wallets=False)

    await send_notification_settings_menu(callback, state, session)


async def send_notification_settings_menu(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_data = await state.get_data()
    user_id = callback.from_user.id

    text = my_gettext(user_id, 'notification_settings_menu')

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'toggle_token_button',
                                                    (user_data.get('asset_code', my_gettext(user_id, 'any_token')),)),
                                    callback_data="toggle_token")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'change_amount_button', (user_data.get('min_amount', 0),)),
                                    callback_data="change_amount")],
        [types.InlineKeyboardButton(
            text=my_gettext(user_id, 'toggle_wallets_button',
                            (my_gettext(user_id, 'yes') if user_data.get('for_all_wallets') else my_gettext(user_id,
                                                                                                            'no'),)),
            callback_data="toggle_wallets")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'save_button'), callback_data="save_filter")],
        get_return_button(user_id)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "toggle_token")
async def toggle_token_callback(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_data = await state.get_data()

    # Toggle between specific token and any token
    if user_data.get('asset_code'):
        await state.update_data(asset_code=None)
    else:
        operation = await asyncio.to_thread(db_get_operation, session, user_data.get('operation_id'))
        await state.update_data(asset_code=operation.code1)

    await send_notification_settings_menu(callback, state, session)


amounts = [0, 1, 10, 100, 1000, 10000]


@router.callback_query(F.data == "change_amount")
async def change_amount_callback(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_data = await state.get_data()
    current_amount = user_data.get('min_amount', 0)

    try:
        current_index = amounts.index(current_amount)
        new_index = (current_index + 1) % len(amounts)
        new_amount = amounts[new_index]
    except ValueError:
        new_amount = amounts[0]

    await state.update_data(min_amount=new_amount)
    await send_notification_settings_menu(callback, state, session)


@router.callback_query(F.data == "toggle_wallets")
async def toggle_wallets_callback(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_data = await state.get_data()
    await state.update_data(for_all_wallets=not user_data.get('for_all_wallets'))
    await send_notification_settings_menu(callback, state, session)


@router.callback_query(F.data == "save_filter")
async def save_filter_callback(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_data = await state.get_data()
    user_id = callback.from_user.id

    existing_filter = session.query(NotificationFilter).filter(
        NotificationFilter.user_id == user_id,
        NotificationFilter.public_key == (None if user_data.get('for_all_wallets') else user_data.get('public_key')),
        NotificationFilter.asset_code == user_data.get('asset_code'),
        NotificationFilter.min_amount == user_data.get('min_amount'),
        NotificationFilter.operation_type == user_data.get('operation_type')
    ).first()

    if existing_filter:
        await send_message(session, callback, my_gettext(user_id, 'filter_already_exists'),
                           reply_markup=get_return_button(user_id))
        await callback.answer()
        return

    new_filter = NotificationFilter(
        user_id=user_id,
        public_key=None if user_data.get('for_all_wallets') else user_data.get('public_key'),
        asset_code=user_data.get('asset_code'),
        min_amount=user_data.get('min_amount'),
        operation_type=user_data.get('operation_type')
    )

    session.add(new_filter)
    session.commit()

    await state.clear()
    await send_message(session, callback, my_gettext(user_id, 'filter_saved'),
                       reply_markup=get_return_button(user_id))
    await callback.answer()


@router.callback_query(F.data == "NotificationSettings")
async def notification_settings_callback(callback: types.CallbackQuery, session: Session):
    user_id = callback.from_user.id
    filters_count = session.query(NotificationFilter).filter(NotificationFilter.user_id == user_id).count()

    text = my_gettext(user_id, 'notification_settings_info', (filters_count,))
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete_all_filters'),
                                    callback_data="delete_all_filters")],
        get_return_button(user_id)
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await send_message(session, callback, text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "delete_all_filters")
async def delete_all_filters_callback(callback: types.CallbackQuery, session: Session):
    user_id = callback.from_user.id
    session.query(NotificationFilter).filter(NotificationFilter.user_id == user_id).delete()
    session.commit()

    await send_message(session, callback, my_gettext(user_id, 'all_filters_deleted'),
                       reply_markup=get_return_button(user_id))
    await callback.answer()
