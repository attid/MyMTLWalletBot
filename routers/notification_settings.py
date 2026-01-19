import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session
from loguru import logger
from keyboards.common_keyboards import get_return_button, get_kb_return, HideNotificationCallbackData
from infrastructure.utils.telegram_utils import send_message
from other.lang_tools import my_gettext
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.persistence.sqlalchemy_notification_repository import SqlAlchemyNotificationRepository
from infrastructure.persistence.sqlalchemy_operation_repository import SqlAlchemyOperationRepository
from infrastructure.services.app_context import AppContext

router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(HideNotificationCallbackData.filter())
async def hide_notification_callback(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    data = HideNotificationCallbackData.unpack(callback.data)

    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    op_repo = app_context.repository_factory.get_operation_repository(session)

    
    wallet = await wallet_repo.get_by_id(data.wallet_id)
    operation = await op_repo.get_by_id(data.operation_id)

    if wallet and operation:
        await state.update_data(
            public_key=wallet.public_key,
            operation_id=operation.id,
            asset_code=operation.code1,
            min_amount=float(operation.amount1 or 0),
            operation_type=operation.operation, 
            for_all_wallets=False
        )
        await send_notification_settings_menu(callback, state, session, app_context=app_context)
    else:
        await callback.answer(my_gettext(callback.from_user.id, "error", app_context=app_context), show_alert=True)

# I need to add get_by_id to IWalletRepository first.
# Cancelling this tool call to add method first.


async def send_notification_settings_menu(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    user_data = await state.get_data()
    user_id = callback.from_user.id

    is_token_notify = user_data.get('asset_code') is not None
    is_wallets_notify = user_data.get('for_all_wallets')

    text = my_gettext(user_id, 'notification_settings_menu', app_context=app_context)

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'toggle_token_button',
                                                   ('✅' if is_token_notify else '❌'), app_context=app_context),
                                   callback_data="toggle_token_notify")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'change_amount_button', (user_data.get('min_amount', 0),), app_context=app_context),
                                    callback_data="change_amount")],
        [types.InlineKeyboardButton(
            text=my_gettext(user_id, 'toggle_wallets_button',
                            ('✅' if is_wallets_notify else '❌'), app_context=app_context),
            callback_data="toggle_wallets_notify")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'save_button', app_context=app_context), callback_data="save_filter")],
        get_return_button(user_id, app_context=app_context)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, text, reply_markup=keyboard, app_context=app_context)
    await callback.answer()


@router.callback_query(F.data == "toggle_token_notify")
async def toggle_token_callback(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    user_data = await state.get_data()

    # Toggle between specific token and any token
    if user_data.get('asset_code'):
        await state.update_data(asset_code=None)
    else:
        op_repo = app_context.repository_factory.get_operation_repository(session)
        operation = await op_repo.get_by_id(user_data.get('operation_id'))
        await state.update_data(asset_code=operation.code1)

    await send_notification_settings_menu(callback, state, session, app_context=app_context)


amounts = [0, 1, 10, 100, 1000, 10000]


@router.callback_query(F.data == "change_amount")
async def change_amount_callback(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    user_data = await state.get_data()
    current_amount = user_data.get('min_amount', 0)

    try:
        current_index = amounts.index(current_amount)
        new_index = (current_index + 1) % len(amounts)
        new_amount = amounts[new_index]
    except ValueError:
        new_amount = amounts[0]

    await state.update_data(min_amount=new_amount)
    await send_notification_settings_menu(callback, state, session, app_context=app_context)


@router.callback_query(F.data == "toggle_wallets_notify")
async def toggle_wallets_callback(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    user_data = await state.get_data()
    await state.update_data(for_all_wallets=not user_data.get('for_all_wallets'))
    await send_notification_settings_menu(callback, state, session, app_context=app_context)


@router.callback_query(F.data == "save_filter")
async def save_filter_callback(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    user_data = await state.get_data()
    user_id = callback.from_user.id
    public_key = None if user_data.get('for_all_wallets') else user_data.get('public_key')

    logger.info(
        "save_filter attempt user_id={} public_key={} asset_code={} min_amount={} operation_type={} raw_data={}",
        user_id,
        public_key,
        user_data.get('asset_code'),
        user_data.get('min_amount'),
        user_data.get('operation_type'),
        user_data,
    )

    repo = app_context.repository_factory.get_notification_repository(session)
    
    existing_filter = await repo.find_duplicate(
        user_id=user_id,
        public_key=public_key,
        asset_code=user_data.get('asset_code'),
        min_amount=user_data.get('min_amount'),
        operation_type=user_data.get('operation_type')
    )

    if existing_filter:
        logger.info(
            "save_filter duplicate user_id={} filter_id={} public_key={} asset_code={} min_amount={} operation_type={}",
            user_id,
            existing_filter.id,
            existing_filter.public_key,
            existing_filter.asset_code,
            existing_filter.min_amount,
            existing_filter.operation_type,
        )
        await send_message(session, callback, my_gettext(user_id, 'filter_already_exists', app_context=app_context),
                           reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        await callback.answer()
        return

    await repo.create(
        user_id=user_id,
        public_key=public_key,
        asset_code=user_data.get('asset_code'),
        min_amount=user_data.get('min_amount'),
        operation_type=user_data.get('operation_type')
    )

    await state.clear()
    await send_message(session, callback, my_gettext(user_id, 'filter_saved', app_context=app_context),
                       reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
    await callback.answer()


@router.callback_query(F.data == "NotificationSettings")
async def notification_settings_callback(callback: types.CallbackQuery, session: Session, app_context: AppContext):
    user_id = callback.from_user.id
    repo = app_context.repository_factory.get_notification_repository(session)
    filters = await repo.get_by_user_id(user_id)
    filters_count = len(filters)

    text = my_gettext(user_id, 'notification_settings_info', (filters_count,), app_context=app_context)
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_delete_all_filters', app_context=app_context),
                                    callback_data="delete_all_filters")],
        get_return_button(user_id, app_context=app_context)
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await send_message(session, callback, text, reply_markup=keyboard, app_context=app_context)
    await callback.answer()


@router.callback_query(F.data == "delete_all_filters")
async def delete_all_filters_callback(callback: types.CallbackQuery, session: Session, app_context: AppContext):
    user_id = callback.from_user.id
    repo = app_context.repository_factory.get_notification_repository(session)
    await repo.delete_all_by_user(user_id)

    await send_message(session, callback, my_gettext(user_id, 'all_filters_deleted', app_context=app_context),
                       reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
    await callback.answer()
