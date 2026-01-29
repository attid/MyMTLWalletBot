from aiogram import Router, types, F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from keyboards.common_keyboards import get_return_button, get_kb_return
from infrastructure.utils.telegram_utils import send_message
from other.lang_tools import my_gettext
from infrastructure.services.app_context import AppContext
from infrastructure.utils.common_utils import float2str

router = Router()
router.message.filter(F.chat.type == "private")


class NotificationFilterAction(CallbackData, prefix="notif_filter"):
    action: str  # 'info', 'delete'
    filter_id: int


class NotificationMenuAction(CallbackData, prefix="notif_menu"):
    action: str  # 'list', 'delete_all'
    page: int = 0


async def send_notification_settings_menu(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    user_data = await state.get_data()
    user_id = callback.from_user.id

    is_token_notify = user_data.get('asset_code') is not None
    is_wallets_notify = user_data.get('for_all_wallets')

    text = my_gettext(user_id, 'notification_settings_menu', app_context=app_context)

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'toggle_token_button',
                                                   (('✅' if is_token_notify else '❌'),), app_context=app_context),
                                   callback_data="toggle_token_notify")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'change_amount_button', (float2str(user_data.get('min_amount', 0)),), app_context=app_context),
                                    callback_data="change_amount")],
        [types.InlineKeyboardButton(
            text=my_gettext(user_id, 'toggle_wallets_button',
                            (('✅' if is_wallets_notify else '❌'),), app_context=app_context),
            callback_data="toggle_wallets_notify")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'save_button', app_context=app_context), callback_data="save_filter")],
        get_return_button(user_id, app_context=app_context)
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, text, reply_markup=keyboard, app_context=app_context)
    await callback.answer()


@router.callback_query(F.data == "toggle_token_notify")
async def toggle_token_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    user_data = await state.get_data()

    # Toggle between specific token and any token
    if user_data.get('asset_code'):
        await state.update_data(asset_code=None)
    else:
        op_repo = app_context.repository_factory.get_operation_repository(session)
        operation_id = user_data.get('operation_id')
        if operation_id:
            operation = await op_repo.get_by_id(str(operation_id))
            if operation:
                await state.update_data(asset_code=operation.code1)

    await send_notification_settings_menu(callback, state, session, app_context=app_context)


amounts = [0, 1, 10, 100, 1000, 10000]


@router.callback_query(F.data == "change_amount")
async def change_amount_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
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
async def toggle_wallets_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    user_data = await state.get_data()
    await state.update_data(for_all_wallets=not user_data.get('for_all_wallets'))
    await send_notification_settings_menu(callback, state, session, app_context=app_context)


@router.callback_query(F.data == "save_filter")
async def save_filter_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
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

    min_amount: float = float(user_data.get('min_amount', 0))
    operation_type: str = str(user_data.get('operation_type', ''))

    existing_filter = await repo.find_duplicate(
        user_id=user_id,
        public_key=public_key,
        asset_code=user_data.get('asset_code'),
        min_amount=min_amount,
        operation_type=operation_type
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
        min_amount=min_amount,
        operation_type=operation_type
    )

    await state.clear()
    await send_message(session, callback, my_gettext(user_id, 'filter_saved', app_context=app_context),
                       reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
    await callback.answer()


@router.callback_query(F.data == "NotificationSettings")
async def notification_settings_entry(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    # Redirect to the main handler with page 0 using the new logic
    await notification_settings_callback(callback, NotificationMenuAction(action="list", page=0), state, session, app_context)


@router.callback_query(NotificationMenuAction.filter())
async def notification_settings_callback(
        callback: types.CallbackQuery,
        callback_data: NotificationMenuAction,
        state: FSMContext,
        session: AsyncSession,
        app_context: AppContext
    ):
    """Show notification filters list with pagination."""
    user_id = callback.from_user.id
    repo = app_context.repository_factory.get_notification_repository(session)

    if callback_data.action == "delete_all":
        await repo.delete_all_by_user(user_id)
        await send_message(session, callback, my_gettext(user_id, 'all_filters_deleted', app_context=app_context),
                           reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        await callback.answer()
        return

    # List action
    filters = await repo.get_by_user_id(user_id)
    filters_count = len(filters)

    page = callback_data.page

    # Pagination: 10 filters per page
    items_per_page = 10
    total_pages = max(1, (filters_count + items_per_page - 1) // items_per_page)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_filters = filters[start_idx:end_idx]

    if filters_count == 0:
        text = my_gettext(user_id, 'no_filters', app_context=app_context)
    else:
        text = my_gettext(user_id, 'notification_filters_title', (filters_count,), app_context=app_context)

    buttons = []

    # Show filters with optimized info buttons
    for f in page_filters:
        asset_display = f.asset_code or "*"
        amount_display = float2str(f.min_amount) if f.min_amount else "0"
        op_display = f.operation_type[:10] if f.operation_type else "*"

        filter_text = my_gettext(user_id, 'notification_filter_item',
                                 (op_display, amount_display, asset_display), app_context=app_context)
        
        # Only one button per filter to show info/delete options
        buttons.append([
            types.InlineKeyboardButton(
                text=filter_text,
                callback_data=NotificationFilterAction(action="info", filter_id=f.id).pack()
            )
        ])

    # Pagination buttons
    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(types.InlineKeyboardButton(
                text="⬅️", 
                callback_data=NotificationMenuAction(action="list", page=page - 1).pack()
            ))
        pagination_row.append(types.InlineKeyboardButton(
            text=my_gettext(user_id, 'filters_page', (page + 1, total_pages), app_context=app_context),
            callback_data="noop"
        ))
        if page < total_pages - 1:
            pagination_row.append(types.InlineKeyboardButton(
                text="➡️", 
                callback_data=NotificationMenuAction(action="list", page=page + 1).pack()
            ))
        buttons.append(pagination_row)

    # Add filter button
    buttons.append([types.InlineKeyboardButton(
        text=my_gettext(user_id, 'kb_add_filter', app_context=app_context),
        callback_data="add_filter_menu"
    )])

    # Delete all button (only if there are filters)
    if filters_count > 0:
        buttons.append([types.InlineKeyboardButton(
            text=my_gettext(user_id, 'kb_delete_all_filters', app_context=app_context),
            callback_data=NotificationMenuAction(action="delete_all").pack()
        )])

    buttons.append(get_return_button(user_id, app_context=app_context))
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    # Use edit if possible to avoid flickering if called from within the same menu
    if callback.message.text == text: # Simple check, might need more robust way
         try:
             await callback.message.edit_reply_markup(reply_markup=keyboard)
             await callback.answer()
             return
         except Exception:
             pass

    await send_message(session, callback, text, reply_markup=keyboard, app_context=app_context)
    await callback.answer()


@router.callback_query(NotificationFilterAction.filter())
async def handle_filter_action(
    callback: types.CallbackQuery,
    callback_data: NotificationFilterAction,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext
):
    user_id = callback.from_user.id
    repo = app_context.repository_factory.get_notification_repository(session)
    filter_id = callback_data.filter_id

    if callback_data.action == "delete":
        success = await repo.delete_by_id(filter_id, user_id)
        if success:
            await callback.answer(my_gettext(user_id, 'filter_deleted', app_context=app_context))
            # Return to list
            await notification_settings_callback(callback, NotificationMenuAction(action="list"), state, session, app_context)
        else:
            await callback.answer(my_gettext(user_id, 'notification_settings_error', app_context=app_context), show_alert=True)
        return

    if callback_data.action == "info":
        notif_filter = await repo.get_by_id(filter_id)
        if not notif_filter or notif_filter.user_id != user_id:
             await callback.answer(my_gettext(user_id, 'notification_settings_error', app_context=app_context), show_alert=True)
             # Refresh list as it might be deleted
             await notification_settings_callback(callback, NotificationMenuAction(action="list"), state, session, app_context)
             return

        # Prepare detailed info
        asset_display = notif_filter.asset_code or "Any (*)"
        amount_display = float2str(notif_filter.min_amount) if notif_filter.min_amount else "0"
        op_display = notif_filter.operation_type or "Any (*)"
        wallet_display = str(notif_filter.public_key) if notif_filter.public_key else "All Wallets"

        info_text = (
            f"📋 <b>Filter Info</b>\n\n"
            f"<b>Operation:</b> {op_display}\n"
            f"<b>Asset:</b> {asset_display}\n"
            f"<b>Min Amount:</b> {amount_display}\n"
            f"<b>Wallet:</b> <code>{wallet_display}</code>\n"
        )
        
        buttons = [
            [types.InlineKeyboardButton(
                text=my_gettext(user_id, 'kb_delete_filter', app_context=app_context),
                callback_data=NotificationFilterAction(action="delete", filter_id=filter_id).pack()
            )],
            [types.InlineKeyboardButton(
                text="🔙 " + my_gettext(user_id, 'kb_back', app_context=app_context),
                callback_data=NotificationMenuAction(action="list").pack()
            )]
        ]
        
        await send_message(session, callback, info_text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons), app_context=app_context)
        await callback.answer()


@router.callback_query(F.data == "add_filter_menu")
async def add_filter_menu_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    """Show recent operations from history to create a filter from."""
    user_id = callback.from_user.id

    if not app_context.notification_history:
        await callback.answer(my_gettext(user_id, 'no_recent_operations', app_context=app_context), show_alert=True)
        return

    recent_ops = app_context.notification_history.get_recent(user_id, limit=10)

    if not recent_ops:
        text = my_gettext(user_id, 'no_recent_operations', app_context=app_context)
        buttons = [get_return_button(user_id, app_context=app_context)]
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        await send_message(session, callback, text, reply_markup=keyboard, app_context=app_context)
        await callback.answer()
        return

    text = my_gettext(user_id, 'select_operation_for_filter', app_context=app_context)
    buttons = []

    for op in recent_ops:
        op_display = op.operation_type[:10] if op.operation_type else "*"
        amount_display = float2str(float(op.amount)) if op.amount else "0"
        asset_display = op.asset_code or "XLM"

        btn_text = my_gettext(user_id, 'notification_filter_item',
                             (op_display, amount_display, asset_display), app_context=app_context)
        buttons.append([types.InlineKeyboardButton(
            text=btn_text,
            callback_data=f"create_filter_from:{op.id}"
        )])

    buttons.append(get_return_button(user_id, app_context=app_context))
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await send_message(session, callback, text, reply_markup=keyboard, app_context=app_context)
    await callback.answer()


@router.callback_query(F.data.startswith("create_filter_from:"))
async def create_filter_from_history_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    """Create a filter from a selected notification history record."""
    user_id = callback.from_user.id
    record_id = (callback.data or "").split(":")[1]

    if not app_context.notification_history:
        await callback.answer(my_gettext(user_id, 'notification_settings_error', app_context=app_context), show_alert=True)
        return

    record = app_context.notification_history.get_by_id(user_id, record_id)

    if not record:
        await callback.answer(my_gettext(user_id, 'notification_settings_error', app_context=app_context), show_alert=True)
        return

    # Set up state for filter configuration
    await state.update_data(
        public_key=record.public_key,
        asset_code=record.asset_code,
        min_amount=float(record.amount) if record.amount else 0,
        operation_type=record.operation_type,
        for_all_wallets=False
    )

    await send_notification_settings_menu(callback, state, session, app_context=app_context)
