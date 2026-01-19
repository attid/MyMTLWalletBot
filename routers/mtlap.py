from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return
from infrastructure.utils.telegram_utils import my_gettext, send_message
from infrastructure.services.app_context import AppContext



RECOMMEND_PREFIX = "RecommendToMTLA"


def _collect_recommendations(data):
    recommendations = []
    max_index = None
    for key, value in data.items():
        if key.startswith(RECOMMEND_PREFIX):
            suffix = key[len(RECOMMEND_PREFIX):]
            if not suffix:
                index = 0
            elif suffix.isdigit():
                index = int(suffix)
            else:
                continue
            recommendations.append((index, key, value))
            if max_index is None or index > max_index:
                max_index = index
    recommendations.sort(key=lambda item: item[0])
    return recommendations, max_index


class MTLAPStateTools(StatesGroup):
    delegate_for_a = State()
    delegate_for_c = State()
    recommend_for = State()


router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(F.data == "MTLAPTools")
async def cmd_mtlap_tools(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    user_id = callback.from_user.id
    msg = my_gettext(user_id, 'mtlap_tools_text', app_context=app_context)

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_mtlap_assembly', app_context=app_context),
                                    callback_data="MTLAPToolsDelegateA")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_mtlap_council', app_context=app_context),
                                    callback_data="MTLAPToolsDelegateC")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_mtlap_recommend', app_context=app_context),
                                    callback_data="MTLAPToolsRecommend")],
        get_return_button(user_id, app_context=app_context)
    ]
    await send_message(
        session,
        user_id,
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        app_context=app_context,
    )
    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################


@router.callback_query(F.data == "MTLAPToolsRecommend")
async def cmd_mtlap_tools_recommend(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Get wallet and account data via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    account_details = await app_context.stellar_service.get_account_details(wallet.public_key)
    data = account_details.get('data', {}) if account_details else {}
    recommendations, _ = _collect_recommendations(data)

    if recommendations:
        existing = my_gettext(callback, 'recommend_count', (len(recommendations),), app_context=app_context)
    else:
        existing = my_gettext(callback, 'recommend_none', app_context=app_context)

    msg = my_gettext(callback, 'recommend_prompt', (existing,), app_context=app_context)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )
    await state.set_state(MTLAPStateTools.recommend_for)
    await callback.answer()


@router.message(MTLAPStateTools.recommend_for)
async def cmd_mtlap_send_recommend(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    public_key = message.text.strip()
    # Get wallet and account data via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(message.from_user.id)
    account_details = await app_context.stellar_service.get_account_details(wallet.public_key)
    user_data = account_details.get('data', {}) if account_details else {}
    recommendations, max_index = _collect_recommendations(user_data)

    if recommendations:
        existing = my_gettext(message, 'recommend_count', (len(recommendations),), app_context=app_context)
    else:
        existing = my_gettext(message, 'recommend_none', app_context=app_context)

    # Check if account exists via DI
    delegate_exists = await app_context.stellar_service.check_account_exists(public_key)
    
    if not delegate_exists:
        msg = my_gettext(message, 'send_error2', app_context=app_context) + '\n' + my_gettext(message, 'recommend_prompt', (existing,), app_context=app_context)
        await send_message(
            session,
            message,
            msg,
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )
        await message.delete()
        return

    if max_index is None:
        new_key = RECOMMEND_PREFIX
    else:
        new_key = f"{RECOMMEND_PREFIX}{max_index + 1}"

    # Get user's wallet public key via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(message.from_user.id)
    source_account = wallet.public_key
    
    # Generate XDR for manage data operation via DI
    xdr = await app_context.stellar_service.build_manage_data_transaction(
        source_account_id=source_account,
        data_name=new_key,
        data_value=public_key
    )
    await state.update_data(xdr=xdr)
    confirm_msg = my_gettext(message, 'recommend_confirm', (public_key, new_key), app_context=app_context)
    await send_message(
        session,
        message,
        confirm_msg,
        reply_markup=get_kb_yesno_send_xdr(message, app_context=app_context),
        app_context=app_context,
    )
    await message.delete()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "MTLAPToolsDelegateA")
async def cmd_mtlap_tools_delegate_a(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Get wallet and account data via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    account_details = await app_context.stellar_service.get_account_details(wallet.public_key)
    data = account_details.get('data', {}) if account_details else {}
    delegate = None
    for name in data:
        if name == "mtla_a_delegate":
            delegate = data[name]
            break
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_add_delegate', app_context=app_context),
                                    callback_data="MTLAPToolsAddDelegateA")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_del_delegate', app_context=app_context),
                                    callback_data="MTLAPToolsDelDelegateA")],
        get_return_button(callback, app_context=app_context)
    ]

    msg = my_gettext(callback, 'delegate_start', (delegate,), app_context=app_context)

    await send_message(
        session,
        callback,
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        app_context=app_context,
    )
    await callback.answer()


@router.callback_query(F.data == "MTLAPToolsDelDelegateA")
async def cmd_mtlap_tools_del_delegate_a(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Get wallet and account data via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    account_details = await app_context.stellar_service.get_account_details(wallet.public_key)
    data = account_details.get('data', {}) if account_details else {}
    delegate = None
    for name in data:
        if name in ("mtlap_delegate", "mtla_delegate", "mtla_a_delegate"):
            delegate = name
            break
    if delegate:
        # Get user's wallet public key via DI
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
        source_account = wallet.public_key
        
        # Generate XDR for manage data operation (delete) via DI
        xdr = await app_context.stellar_service.build_manage_data_transaction(
            source_account_id=source_account,
            data_name=delegate,
            data_value=None
        )
        await state.update_data(xdr=xdr)
        await send_message(
            session,
            callback,
            my_gettext(callback, 'delegate_delete', (delegate,), app_context=app_context),
            reply_markup=get_kb_yesno_send_xdr(callback, app_context=app_context),
            app_context=app_context,
        )

        await callback.answer()
    else:
        await callback.answer('Nothing to delete')


@router.callback_query(F.data == "MTLAPToolsAddDelegateA")
async def cmd_mtlap_tools_add_delegate_a(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Check free XLM via state data
    data = await state.get_data()
    free_xlm = data.get("free_xlm", 0.0)
    if free_xlm < 0.5:
        await callback.answer(my_gettext(callback, 'low_xlm', app_context=app_context), show_alert=True)
        return
    await send_message(
        session,
        callback,
        my_gettext(callback, 'delegate_send_address', app_context=app_context),
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )
    await state.set_state(MTLAPStateTools.delegate_for_a)
    await callback.answer()


@router.message(MTLAPStateTools.delegate_for_a)
async def cmd_mtlap_send_add_delegate_for_a(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    public_key = message.text
    # Check if account exists via DI
    account_exists = await app_context.stellar_service.check_account_exists(public_key)
    
    if account_exists:
        # Get user's wallet public key via DI
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(message.from_user.id)
        source_account = wallet.public_key
        
        # Generate XDR for manage data operation via DI
        xdr = await app_context.stellar_service.build_manage_data_transaction(
            source_account_id=source_account,
            data_name="mtla_a_delegate",
            data_value=public_key
        )
        await state.update_data(xdr=xdr)
        await send_message(
            session,
            message,
            my_gettext(message, 'delegate_add', (public_key,), app_context=app_context),
            reply_markup=get_kb_yesno_send_xdr(message, app_context=app_context),
            app_context=app_context,
        )
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2', app_context=app_context) + '\n' + my_gettext(message, 'delegate_send_address', app_context=app_context)
        await send_message(session, message, msg, app_context=app_context)
        await message.delete()


########################################################################################################################
##################################  mtla_c_delegate ####################################################################
########################################################################################################################

@router.callback_query(F.data == "MTLAPToolsDelegateC")
async def cmd_mtlap_tools_delegate_c(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Get wallet and account data via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    account_details = await app_context.stellar_service.get_account_details(wallet.public_key)
    data = account_details.get('data', {}) if account_details else {}
    delegate = None
    for name in data:
        if name == "mtla_c_delegate":
            delegate = data[name]
            break
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_add_delegate', app_context=app_context),
                                    callback_data="MTLAPToolsAddDelegateC")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_del_delegate', app_context=app_context),
                                    callback_data="MTLAPToolsDelDelegateC")],
        get_return_button(callback, app_context=app_context)
    ]

    msg = my_gettext(callback, 'delegate_start', (delegate,), app_context=app_context)

    await send_message(
        session,
        callback,
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        app_context=app_context,
    )
    await callback.answer()


@router.callback_query(F.data == "MTLAPToolsDelDelegateC")
async def cmd_mtlap_tools_del_delegate_c(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Get wallet and account data via DI
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
    account_details = await app_context.stellar_service.get_account_details(wallet.public_key)
    data = account_details.get('data', {}) if account_details else {}
    delegate = None
    for name in data:
        if name in ("mtla_c_delegate",):
            delegate = name
            break
    if delegate:
        # Get user's wallet public key via DI
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
        source_account = wallet.public_key
        
        # Generate XDR for manage data operation (delete) via DI
        xdr = await app_context.stellar_service.build_manage_data_transaction(
            source_account_id=source_account,
            data_name=delegate,
            data_value=None
        )
        await state.update_data(xdr=xdr)
        await send_message(
            session,
            callback,
            my_gettext(callback, 'delegate_delete', (delegate,), app_context=app_context),
            reply_markup=get_kb_yesno_send_xdr(callback, app_context=app_context),
            app_context=app_context,
        )

        await callback.answer()
    else:
        await callback.answer('Nothing to delete')


@router.callback_query(F.data == "MTLAPToolsAddDelegateC")
async def cmd_mtlap_tools_add_delegate_c(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    # Check free XLM via state data
    data = await state.get_data()
    free_xlm = data.get("free_xlm", 0.0)
    if free_xlm < 0.5:
        await callback.answer(my_gettext(callback, 'low_xlm', app_context=app_context), show_alert=True)
        return
    await send_message(
        session,
        callback,
        msg=my_gettext(callback, 'delegate_send_address', app_context=app_context)
        + my_gettext(callback, 'delegate_ready', app_context=app_context),
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )
    await state.set_state(MTLAPStateTools.delegate_for_c)
    await callback.answer()


@router.message(MTLAPStateTools.delegate_for_c)
async def cmd_mtlap_send_add_delegate_for_c(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    public_key = message.text
    delegate = 'ready' if message.text.lower() == 'ready' else None
    # Check if account exists via DI
    account_exists = await app_context.stellar_service.check_account_exists(public_key) if not delegate else False
    
    if account_exists or delegate:
        if not delegate:
            delegate = public_key
        
        # Get user's wallet public key via DI
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(message.from_user.id)
        source_account = wallet.public_key
        
        # Generate XDR for manage data operation via DI
        xdr = await app_context.stellar_service.build_manage_data_transaction(
            source_account_id=source_account,
            data_name="mtla_c_delegate",
            data_value=delegate
        )
        await state.update_data(xdr=xdr)
        await send_message(
            session,
            message,
            my_gettext(message, 'delegate_add', (delegate,), app_context=app_context),
            reply_markup=get_kb_yesno_send_xdr(message, app_context=app_context),
            app_context=app_context,
        )
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2', app_context=app_context) + '\n' + my_gettext(message, 'delegate_send_address', app_context=app_context)
        await send_message(session, message, msg, app_context=app_context)
        await message.delete()

########################################################################################################################
########################################################################################################################
########################################################################################################################
