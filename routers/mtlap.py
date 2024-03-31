from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return
from utils.aiogram_utils import my_gettext, send_message
from utils.stellar_utils import stellar_get_data, cmd_gen_data_xdr, stellar_get_user_account, stellar_check_account, \
    have_free_xlm


class MTLAPStateTools(StatesGroup):
    delegate_for_a = State()
    delegate_for_c = State()


router = Router()


@router.callback_query(F.data == "MTLAPTools")
async def cmd_mtlap_tools(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_id = callback.from_user.id
    msg = my_gettext(user_id, 'mtlap_tools_text')

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_mtlap_assembly'),
                                    callback_data="MTLAPToolsDelegateA")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_mtlap_council'),
                                    callback_data="MTLAPToolsDelegateC")],
        get_return_button(user_id)
    ]
    await send_message(session, user_id, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(F.data == "MTLAPToolsDelegateA")
async def cmd_mtlap_tools_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await stellar_get_data(session, callback.from_user.id)
    delegate = None
    for name in data:
        if name == "mtla_a_delegate":
            delegate = data[name]
            break
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_add_delegate'),
                                    callback_data="MTLAPToolsAddDelegateA")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_del_delegate'),
                                    callback_data="MTLAPToolsDelDelegateA")],
        get_return_button(callback)
    ]

    msg = my_gettext(callback, 'delegate_start', (delegate,))

    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "MTLAPToolsDelDelegateA")
async def cmd_mtlap_tools_del_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await stellar_get_data(session, callback.from_user.id)
    delegate = None
    for name in data:
        if name in ("mtlap_delegate", "mtla_delegate", "mtla_a_delegate"):
            delegate = name
            break
    if delegate:
        xdr = await cmd_gen_data_xdr(
            (await stellar_get_user_account(session, callback.from_user.id)).account.account_id,
            delegate, None)
        await state.update_data(xdr=xdr)
        await send_message(session, callback, my_gettext(callback, 'delegate_delete', (delegate,)),
                           reply_markup=get_kb_yesno_send_xdr(callback))

        await callback.answer()
    else:
        await callback.answer('Nothing to delete')


@router.callback_query(F.data == "MTLAPToolsAddDelegateA")
async def cmd_mtlap_tools_add_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if not await have_free_xlm(session=session, state=state, user_id=callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return
    await send_message(session, callback, my_gettext(callback, 'delegate_send_address'),
                       reply_markup=get_kb_return(callback))
    await state.set_state(MTLAPStateTools.delegate_for_a)
    await callback.answer()


@router.message(MTLAPStateTools.delegate_for_a)
async def cmd_mtlap_send_add_delegate_for(message: types.Message, state: FSMContext, session: Session):
    public_key = message.text
    my_account = await stellar_check_account(public_key)
    if my_account:
        delegate = my_account.account.account.account_id
        xdr = await cmd_gen_data_xdr((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                                     "mtla_a_delegate", delegate)
        await state.update_data(xdr=xdr)
        await send_message(session, message, my_gettext(message, 'delegate_add', (delegate,)),
                           reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'delegate_send_address')
        await send_message(session, message, msg)
        await message.delete()


########################################################################################################################
##################################  mtla_c_delegate ####################################################################
########################################################################################################################

@router.callback_query(F.data == "MTLAPToolsDelegateC")
async def cmd_mtlap_tools_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await stellar_get_data(session, callback.from_user.id)
    delegate = None
    for name in data:
        if name == "mtla_c_delegate":
            delegate = data[name]
            break
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_add_delegate'),
                                    callback_data="MTLAPToolsAddDelegateC")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_del_delegate'),
                                    callback_data="MTLAPToolsDelDelegateC")],
        get_return_button(callback)
    ]

    msg = my_gettext(callback, 'delegate_start', (delegate,))

    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "MTLAPToolsDelDelegateC")
async def cmd_mtlap_tools_del_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await stellar_get_data(session, callback.from_user.id)
    delegate = None
    for name in data:
        if name in ("mtla_c_delegate",):
            delegate = name
            break
    if delegate:
        xdr = await cmd_gen_data_xdr(
            (await stellar_get_user_account(session, callback.from_user.id)).account.account_id,
            delegate, None)
        await state.update_data(xdr=xdr)
        await send_message(session, callback, my_gettext(callback, 'delegate_delete', (delegate,)),
                           reply_markup=get_kb_yesno_send_xdr(callback))

        await callback.answer()
    else:
        await callback.answer('Nothing to delete')


@router.callback_query(F.data == "MTLAPToolsAddDelegateC")
async def cmd_mtlap_tools_add_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    if not await have_free_xlm(session=session, state=state, user_id=callback.from_user.id):
        await callback.answer(my_gettext(callback, 'low_xlm'), show_alert=True)
        return
    await send_message(session, callback, reply_markup=get_kb_return(callback),
                       msg=my_gettext(callback, 'delegate_send_address') +
                           my_gettext(callback, 'delegate_ready'),
                       )
    await state.set_state(MTLAPStateTools.delegate_for_c)
    await callback.answer()


@router.message(MTLAPStateTools.delegate_for_c)
async def cmd_mtlap_send_add_delegate_for(message: types.Message, state: FSMContext, session: Session):
    public_key = message.text
    delegate = 'ready' if message.text.lower() == 'ready' else None
    my_account = await stellar_check_account(public_key)
    if my_account or delegate:
        if my_account:
            delegate = my_account.account.account.account_id
        xdr = await cmd_gen_data_xdr((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                                     "mtla_c_delegate", delegate)
        await state.update_data(xdr=xdr)
        await send_message(session, message, my_gettext(message, 'delegate_add', (delegate,)),
                           reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'delegate_send_address')
        await send_message(session, message, msg)
        await message.delete()

########################################################################################################################
########################################################################################################################
########################################################################################################################
