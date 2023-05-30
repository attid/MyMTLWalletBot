from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.filters import Command, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from fb import get_default_address, set_default_address, reset_balance
from keyboards.common_keyboards import get_return_button, get_kb_return, get_kb_yesno_send_xdr
from routers.common_setting import cmd_language
from routers.sign import cmd_check_xdr
from routers.start_msg import cmd_show_balance
from utils.aiogram_utils import send_message
from utils.lang_utils import set_last_message_id, my_gettext, check_user_id, check_user_lang
from utils.stellar_utils import stellar_get_balances, stellar_get_user_account, stellar_pay, eurmtl_asset, \
    stellar_delete_all

router = Router()


class SettingState(StatesGroup):
    send_donate_sum = State()
    send_default_address = State()


@router.message(Command(commands=["start"]), Text(contains="sign_"))
async def cmd_start(message: types.Message, state: FSMContext, command: Command):
    await state.clear()

    # check address
    set_last_message_id(message.from_user.id, 0)
    await send_message(message.from_user.id, 'Loading')

    # if user not exist
    if not check_user_id(message.from_user.id):
        await send_message(message.from_user.id, 'You dont have wallet. Please run /start')
        return

    # await cmd_login_to_veche(message.from_user.id, state, token=message.text.split(' ')[1][6:])
    await cmd_check_xdr('https://eurmtl.me/sign_tools/' + message.text.split(' ')[1][5:], message.from_user.id, state)


@router.message(Command(commands=["start"]))
async def cmd_start(message: types.Message, state: FSMContext, command: Command):
    # logger.info([message.from_user.id, ' cmd_start'])
    await state.clear()

    # check address
    set_last_message_id(message.from_user.id, 0)
    await send_message(message.from_user.id, 'Loading')

    if check_user_lang(message.from_user.id) is None:
        await cmd_language(message.from_user.id, state)
    else:
        await cmd_show_balance(message.from_user.id, state)


@router.callback_query(Text(text=["Return"]))
async def cb_return(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    try_sent_xdr = data.get('try_sent_xdr')
    if try_sent_xdr and datetime.strptime(try_sent_xdr, '%d.%m.%Y %H:%M:%S') > datetime.now():
        check_time = data.get("try_sent_xdr")
        remaining_seconds = int((datetime.strptime(check_time, '%d.%m.%Y %H:%M:%S') + timedelta(
            seconds=10) - datetime.now()).total_seconds())
        await callback.answer(f'Please wait {remaining_seconds} seconds', show_alert=True)
    else:
        await cmd_show_balance(callback.message.chat.id, state)
        await callback.answer()


@router.callback_query(Text(text=["DeleteReturn"]))
async def cb_delete_return(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.delete()
    except:
        await callback.message.edit_text('deleted')
        await callback.message.edit_reply_markup(None)

    await cmd_show_balance(callback.message.chat.id, state)
    await callback.answer()


@router.message(Command(commands=["about"]))
async def cmd_about(message: types.Message, state: FSMContext, command: Command):
    msg = f'Sorry not ready\n' \
          f'Тут будет что-то о кошельке, переводчиках и добрых людях\n' \
          f'стать добрым - /donate'
    await send_message(message.from_user.id, msg, reply_markup=get_kb_return(message))


def get_kb_donate(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons_list = [["1", "5", "10", "50"],
                    ["100", "300", "1000"]]

    kb_buttons = []

    for buttons in buttons_list:
        tmp_buttons = []
        for button in buttons:
            tmp_buttons.append(
                types.InlineKeyboardButton(text=button, callback_data=button))
        kb_buttons.append(tmp_buttons)
    kb_buttons.append(get_return_button(chat_id))

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    return keyboard


async def cmd_donate(user_id, state: FSMContext):
    balances = await stellar_get_balances(user_id, asset_filter='EURMTL')
    eurmtl_balance = 0
    if balances:
        eurmtl_balance = balances[0].balance

    msg = f'You have {eurmtl_balance} EURMTL\n' \
          f'Choose how much you want to send or send a sum\n' \
          f'Top 5 donators you can see at /about list'
    await state.set_state(SettingState.send_donate_sum)
    await state.update_data(max_sum=eurmtl_balance, msg=msg)
    await send_message(user_id, msg, reply_markup=get_kb_donate(user_id))


@router.callback_query(Text(text=["Donate"]))
async def cb_donate(callback: types.CallbackQuery, state: FSMContext):
    await cmd_donate(callback.from_user.id, state)
    await callback.answer()


@router.message(Command(commands=["donate"]))
async def cmd_donate_message(message: types.Message, state: FSMContext):
    await cmd_donate(message.from_user.id, state)


async def get_donate_sum(user_id, donate_sum, state: FSMContext):
    data = await state.get_data()
    max_sum = float(data['max_sum'])
    try:
        donate_sum = float(donate_sum)
        if donate_sum > max_sum:
            await send_message(user_id, my_gettext(user_id, 'bad_sum') + '\n' + data['msg'],
                               reply_markup=get_kb_return(user_id))
        else:
            public_key = (await stellar_get_user_account(user_id)).account.account_id
            father_key = (await stellar_get_user_account(0)).account.account_id
            memo = "donate"
            xdr = await stellar_pay(public_key, father_key, eurmtl_asset, donate_sum, memo=memo)
            await state.update_data(xdr=xdr, donate=donate_sum)
            msg = my_gettext(user_id, 'confirm_send', (donate_sum, eurmtl_asset.code, father_key, memo))
            msg = f"For donate\n{msg}"

            await send_message(user_id, msg, reply_markup=get_kb_yesno_send_xdr(user_id))
    except:
        await send_message(user_id, my_gettext(user_id, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(user_id))


@router.callback_query(SettingState.send_donate_sum)
async def cb_donate_sum(callback: types.CallbackQuery, state: FSMContext):
    await get_donate_sum(callback.from_user.id, callback.data, state)
    await callback.answer()


@router.message(SettingState.send_donate_sum)
async def cmd_donate_sum(message: types.Message, state: FSMContext):
    await get_donate_sum(message.from_user.id, message.text, state)
    await message.delete()


@router.message(Command(commands=["delete_all"]))
async def cmd_start(message: types.Message, state: FSMContext, command: Command):
    stellar_delete_all(message.from_user.id)
    await send_message(message.from_user.id, 'All was delete, restart please')
    await state.clear()


@router.callback_query(Text(text=["SetDefault"]))
async def cb_set_default(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SettingState.send_default_address)
    msg = my_gettext(callback, 'set_default', (get_default_address(callback.from_user.id),))
    await send_message(callback, msg, reply_markup=get_kb_return(callback))
    await callback.answer()


@router.message(SettingState.send_default_address)
async def cmd_set_default(message: types.Message, state: FSMContext):
    address = message.text
    try:
        await stellar_get_balances(message.from_user.id, public_key=address)
        set_default_address(message.from_user.id, address)
    except:
        set_default_address(message.from_user.id, '')
        # await state.set_state(None)
    msg = my_gettext(message, 'set_default', (get_default_address(message.from_user.id),))
    await send_message(message, msg, reply_markup=get_kb_return(message))

    await message.delete()


@router.callback_query(Text(text=["Refresh"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    reset_balance(callback.from_user.id)
    await cmd_show_balance(callback.from_user.id, state, refresh_callback=callback)
    await callback.answer()
