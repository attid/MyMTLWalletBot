from aiogram import Router, types
from aiogram.filters import Text
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from keyboards.common_keyboards import get_return_button, get_kb_yesno_send_xdr, get_kb_return
from utils.aiogram_utils import my_gettext, send_message
from utils.stellar_utils import stellar_get_data, cmd_gen_data_xdr, stellar_get_user_account, stellar_check_account


class StateTools(StatesGroup):
    delegate_for = State()
    donate_address = State()
    donate_name = State()
    donate_persent = State()
    bim_name = State()
    bim_address = State()


class SendAssetCallbackData(CallbackData, prefix="sale"):
    answer: str


class DonateCallbackData(CallbackData, prefix="DonateCallbackData"):
    action: str
    idx: str


class BIMCallbackData(CallbackData, prefix="BIMCallbackData"):
    action: str
    idx: str


router = Router()


@router.callback_query(Text(text=["MTLTools"]))
async def cmd_tools(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    msg = my_gettext(user_id, 'mtl_tools_msg')

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_tools_veche'), callback_data="MTLToolsVeche")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_tools_donate'), callback_data="MTLToolsDonate")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_tools_delegate'), callback_data="MTLToolsDelegate")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_tools_add_bim'), callback_data="MTLToolsAddBIM")],
        get_return_button(user_id)
    ]
    await send_message(user_id, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["MTLToolsDelegate"]))
async def cmd_tools_delegate(callback: types.CallbackQuery, state: FSMContext):
    data = stellar_get_data(callback.from_user.id)
    delegate = None
    for name in data:
        if name == "mtl_delegate":
            delegate = data[name]
            break
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_add_delegate'),
                                    callback_data="MTLToolsAddDelegate")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_tools_del_delegate'),
                                    callback_data="MTLToolsDelDelegate")],
        get_return_button(callback)
    ]

    msg = my_gettext(callback, 'delegate_start',(delegate,))

    await send_message(callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(Text(text=["MTLToolsDelDelegate"]))
async def cmd_tools_del_delegate(callback: types.CallbackQuery, state: FSMContext):
    data = stellar_get_data(callback.from_user.id)
    delegate = None
    for name in data:
        if name in ("mtl_delegate", "delegate"):
            delegate = name
            break
    if delegate:
        xdr = cmd_gen_data_xdr(stellar_get_user_account(callback.from_user.id).account.account_id,
                               delegate, None)
        await state.update_data(xdr=xdr)
        await send_message(callback, my_gettext(callback, 'delegate_delete',(delegate,)),
                           reply_markup=get_kb_yesno_send_xdr(callback))

        await callback.answer()
    else:
        await callback.answer('Nothing to delete')


@router.callback_query(Text(text=["MTLToolsAddDelegate"]))
async def cmd_tools_add_delegate(callback: types.CallbackQuery, state: FSMContext):
    await send_message(callback, my_gettext(callback, 'delegate_send_address'), reply_markup=get_kb_return(callback))
    await state.set_state(StateTools.delegate_for)
    await callback.answer()


@router.message(StateTools.delegate_for)
async def cmd_send_add_delegate_for(message: types.Message, state: FSMContext):
    public_key = message.text
    my_account = stellar_check_account(public_key)
    if my_account:
        delegate = my_account.account.account.account_id
        xdr = cmd_gen_data_xdr(stellar_get_user_account(message.from_user.id).account.account_id,
                               "mtl_delegate", delegate)
        await state.update_data(xdr=xdr)
        await send_message(message, my_gettext(message, 'delegate_add',(delegate,)),
                           reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'delegate_send_address')
        await send_message(message, msg)
        await message.delete()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["MTLToolsDonate"]))
async def cmd_tools_delegate(callback: types.CallbackQuery, state: FSMContext):
    data = stellar_get_data(callback.from_user.id)
    donates = {}
    idx = 0
    for name in data:
        if str(name).startswith("mtl_donate"):
            donates[f'idx{idx}'] = [name, name[11:str(name).find('=')], name[str(name).find('=') + 1], data[name]]
            idx += 1

    buttons = []

    for donate_idx in donates:
        buttons.append(
            [
                types.InlineKeyboardButton(text=donates[donate_idx][1],
                                           callback_data=DonateCallbackData(
                                               action='Show', idx=donate_idx).pack()
                                           ),
                types.InlineKeyboardButton(text=donates[donate_idx][2],
                                           callback_data=DonateCallbackData(
                                               action='Show', idx=donate_idx).pack()
                                           ),
                types.InlineKeyboardButton(text=my_gettext(callback, 'kb_delete'),
                                           callback_data=DonateCallbackData(
                                               action='Delete', idx=donate_idx).pack()
                                           )
            ]
        )
    buttons.append([types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_donate'),
                                               callback_data='AddDonate'
                                               )])
    buttons.append(get_return_button(callback))

    await state.update_data(donates=donates)
    await send_message(callback, my_gettext(callback, 'donate_show'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(Text(text=["AddDonate"]))
async def cmd_tools_add_delegate(callback: types.CallbackQuery, state: FSMContext):
    await send_message(callback, my_gettext(callback, 'donate_send'), reply_markup=get_kb_return(callback))
    await state.set_state(StateTools.donate_address)
    await callback.answer()


@router.message(StateTools.donate_address)
async def cmd_send_add_donate_address(message: types.Message, state: FSMContext):
    public_key = message.text
    my_account = stellar_check_account(public_key)
    if my_account:
        await state.update_data(address=my_account.account.account.account_id)
        await send_message(message, my_gettext(message, 'donate_name'),
                           reply_markup=get_kb_return(message))
        await state.set_state(StateTools.donate_name)
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'donate_send')
        await send_message(message, msg)
        await message.delete()


@router.message(StateTools.donate_name)
async def cmd_send_add_donate_address(message: types.Message, state: FSMContext):
    name = message.text
    if name:
        name = name.replace('=', '_').replace(':', '_')
        await state.update_data(name=name)
        await send_message(message, my_gettext(message, 'donate_persent'),
                           reply_markup=get_kb_return(message))
        await state.set_state(StateTools.donate_persent)
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'donate_send')
        await send_message(message, msg)
        await message.delete()


@router.message(StateTools.donate_persent)
async def cmd_send_add_donate_address(message: types.Message, state: FSMContext):
    if float(message.text):
        persent = float(message.text)
        data = await state.get_data()
        xdr = cmd_gen_data_xdr(stellar_get_user_account(message.from_user.id).account.account_id,
                               f"mtl_donate_{data['name']}={persent}", data['address'])
        await state.update_data(xdr=xdr)
        await send_message(message, my_gettext(message, 'donate_end',(data['name'], persent, data['address'])),
                           reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'donate_send')
        await send_message(message, msg)
        await message.delete()


@router.callback_query(DonateCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: DonateCallbackData,
                     state: FSMContext):
    answer = callback_data.action
    idx = callback_data.idx
    user_id = callback.from_user.id
    data = await state.get_data()
    donates = data['donates']
    if idx in donates:
        if answer == 'Show':
            msg = f"name = {donates[idx][1]} \n persent = {donates[idx][2]}\n address = {donates[idx][3]}"
            await callback.answer(msg[:200], show_alert=True)
        if answer == 'Delete':
            xdr = cmd_gen_data_xdr(stellar_get_user_account(user_id).account.account_id,
                                   donates[idx][0], None)
            await state.update_data(xdr=xdr)
            await send_message(callback, my_gettext(callback, 'donate_delete',(donates[idx][1],)),
                               reply_markup=get_kb_yesno_send_xdr(callback))
    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################

@router.callback_query(Text(text=["MTLToolsAddBIM"]))
async def cmd_tools_delegate(callback: types.CallbackQuery, state: FSMContext):
    data = stellar_get_data(callback.from_user.id)
    bod_dict = {}
    idx = 0
    for name in data:
        if str(name).startswith("bod_"):
            bod_dict[f'idx{idx}'] = [name, name[4:], data[name]]
            idx += 1

    buttons = []

    for donate_idx in bod_dict:
        buttons.append(
            [
                types.InlineKeyboardButton(text=bod_dict[donate_idx][1],
                                           callback_data=BIMCallbackData(
                                               action='Show', idx=donate_idx).pack()
                                           ),
                types.InlineKeyboardButton(text=my_gettext(callback, 'kb_delete'),
                                           callback_data=BIMCallbackData(
                                               action='Delete', idx=donate_idx).pack()
                                           )
            ]
        )
    buttons.append([types.InlineKeyboardButton(text=my_gettext(callback, 'kb_add_bim'),
                                               callback_data='AddBIM'
                                               )])
    buttons.append(get_return_button(callback))

    await state.update_data(donates=bod_dict)
    await send_message(callback, my_gettext(callback, 'show_bim'),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(Text(text=["AddBIM"]))
async def cmd_tools_add_delegate(callback: types.CallbackQuery, state: FSMContext):
    await send_message(callback, my_gettext(callback, 'send_bim_address'), reply_markup=get_kb_return(callback))
    await state.set_state(StateTools.bim_address)
    await callback.answer()


@router.message(StateTools.bim_address)
async def cmd_send_add_donate_address(message: types.Message, state: FSMContext):
    public_key = message.text
    my_account = stellar_check_account(public_key)
    if my_account:
        await state.update_data(address=my_account.account.account.account_id)
        await send_message(message, my_gettext(message, 'send_bim_name'),
                           reply_markup=get_kb_return(message))
        await state.set_state(StateTools.bim_name)
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'send_bim_address')
        await send_message(message, msg)
        await message.delete()


@router.message(StateTools.bim_name)
async def cmd_send_add_donate_address(message: types.Message, state: FSMContext):
    if message.text:
        name = message.text
        data = await state.get_data()
        xdr = cmd_gen_data_xdr(stellar_get_user_account(message.from_user.id).account.account_id,
                               f"bod_{name}", data['address'])
        await state.update_data(xdr=xdr)
        await send_message(message, my_gettext(message, 'add_bim_end',(name, data['address'],)),
                           reply_markup=get_kb_yesno_send_xdr(message))
        await message.delete()
    else:
        msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'send_bim_name')
        await send_message(message, msg)
        await message.delete()


@router.callback_query(BIMCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: BIMCallbackData,
                     state: FSMContext):
    answer = callback_data.action
    idx = callback_data.idx
    user_id = callback.from_user.id
    data = await state.get_data()
    donates = data['donates']
    if idx in donates:
        if answer == 'Show':
            msg = f"name = {donates[idx][1]} \n address = {donates[idx][2]}"
            await callback.answer(msg[:200], show_alert=True)
        if answer == 'Delete':
            xdr = cmd_gen_data_xdr(stellar_get_user_account(user_id).account.account_id,
                                   donates[idx][0], None)
            await state.update_data(xdr=xdr)
            await send_message(callback, my_gettext(callback, 'delete_bim',(donates[idx][1],)),
                               reply_markup=get_kb_yesno_send_xdr(callback))
    await callback.answer()

########################################################################################################################
########################################################################################################################
########################################################################################################################
