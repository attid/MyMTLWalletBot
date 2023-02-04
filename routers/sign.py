import requests
from aiogram import Router, types
from aiogram.filters import Text, Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from stellar_sdk.exceptions import BadRequestError, BaseHorizonError

from mytypes import MyResponse
from routers.start_msg import cmd_show_balance, cmd_info_message
from utils.aiogram_utils import my_gettext, send_message, set_last_message_id, cmd_show_sign, \
    StateSign, bot, admin_id
from keyboards.common_keyboards import get_kb_return, get_return_button, get_kb_del_return
from utils.lang_utils import check_user_id
from utils.stellar_utils import stellar_get_pin_type, stellar_change_password, stellar_user_sign_message, \
    stellar_user_sign, stellar_check_xdr, async_stellar_send, stellar_get_user_account, \
    stellar_get_user_keypair, stellar_unfree_wallet, stellar_add_donate


class PinState(StatesGroup):
    sign = State()
    sign_and_send = State()
    sign_veche = State()
    set_pin = State()
    set_pin2 = State()
    ask_password = State()
    ask_password_set = State()
    ask_password_set2 = State()


class PinCallbackData(CallbackData, prefix="pin_"):
    action: str


router = Router()


@router.callback_query(Text(text=["Yes_send_xdr"]))
async def cmd_yes_send(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PinState.sign_and_send)

    await cmd_ask_pin(callback.from_user.id, state)
    await callback.answer()


async def cmd_ask_pin(chat_id: int, state: FSMContext, msg=None):
    if msg is None:
        msg = my_gettext(chat_id, "enter_password")
    data = await state.get_data()
    pin_type = data.get("pin_type")
    pin = data.get("pin", '')

    if pin_type is None:
        pin_type = stellar_get_pin_type(chat_id)
        await state.update_data(pin_type=pin_type)

    if pin_type == 1:  # pin
        msg = msg + "\n" + ''.ljust(len(pin), '*')
        await send_message(chat_id, msg, reply_markup=get_kb_pin(chat_id))

    if pin_type == 2:  # password
        msg = my_gettext(chat_id, "send_password")
        await state.set_state(PinState.ask_password)
        await send_message(chat_id, msg, reply_markup=get_kb_return(chat_id))

    if pin_type == 0:  # no password
        await state.update_data(pin=chat_id)
        await send_message(chat_id, my_gettext(chat_id, 'confirm_send2'), reply_markup=get_kb_nopassword(chat_id))

    if pin_type == 10:  # ro
        await state.update_data(pin='ro')
        await cmd_show_sign(chat_id, state,
                            my_gettext(chat_id, "your_xdr", (data['xdr'],)),
                            use_send=False)


def get_kb_pin(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons_list = [["1", "2", "3", "A"],
                    ["4", "5", "6", "B"],
                    ["7", "8", "9", "C"],
                    ["0", "D", "E", "F"],
                    ['Del', 'Enter']]

    kb_buttons = []

    for buttons in buttons_list:
        tmp_buttons = []
        for button in buttons:
            tmp_buttons.append(
                types.InlineKeyboardButton(text=button, callback_data=PinCallbackData(action=button).pack()))
        kb_buttons.append(tmp_buttons)

    kb_buttons.append(get_return_button(chat_id))
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    return keyboard


@router.callback_query(PinCallbackData.filter())
async def cq_pin(query: types.CallbackQuery, callback_data: PinCallbackData, state: FSMContext):
    answer = callback_data.action
    user_id = query.from_user.id
    data = await state.get_data()
    pin = data.get('pin', '')

    if answer in '1234567890ABCDEF':
        pin += answer
        await state.update_data(pin=pin)
        await cmd_ask_pin(user_id, state)
        await query.answer(''.ljust(len(pin), '*'))

    if answer == 'Del':
        pin = pin[:len(pin) - 1]
        await state.update_data(pin=pin)
        await cmd_ask_pin(user_id, state)
        await query.answer(''.ljust(len(pin), '*'))

    if answer == 'Enter':
        current_state = await state.get_state()
        if current_state == PinState.set_pin:  # ask for save need pin2
            await state.update_data(pin2=pin, pin='')
            await state.set_state(PinState.set_pin2)
            await cmd_ask_pin(user_id, state, my_gettext(user_id, "resend_password"))
        if current_state == PinState.set_pin2:  # ask pin2 for save
            pin2 = data.get('pin2', '')
            public_key = data.get('public_key', '')
            await state.set_state(None)
            pin_type = data.get('pin_type', '')

            if pin == pin2:
                stellar_change_password(user_id, public_key, str(user_id), pin, pin_type)
                await cmd_show_balance(user_id, state)
            else:
                await state.update_data(pin2='', pin='')
                await state.set_state(PinState.set_pin)
                await query.answer(my_gettext(user_id, "bad_passwords"), show_alert=True)
        if current_state in (PinState.sign, PinState.sign_and_send):  # sign and send
            await sign_xdr(state, user_id)
        return True


async def sign_xdr(state, user_id):
    data = await state.get_data()
    current_state = await state.get_state()
    pin = data.get('pin', '')
    await state.update_data(pin='')
    await state.set_state(None)
    xdr = data.get('xdr')
    message = data.get('message')
    link = data.get('link')
    remove_password = data.get('remove_password')
    send_private_key = data.get('send_private_key')
    buy_address = data.get('buy_address')
    donate = data.get('donate')
    try:
        if user_id > 0:
            if message and link:
                msg = stellar_user_sign_message(message, user_id, str(pin))
                import urllib.parse
                link = link.replace('$$SIGN$$', urllib.parse.quote(msg))
                await state.update_data(link=link)
                await cmd_info_message(user_id,
                                       my_gettext(user_id, 'veche_go', (link,)), state)
                set_last_message_id(user_id, 0)
                await state.set_state(None)
            elif remove_password:
                user_account = stellar_get_user_account(user_id)
                stellar_change_password(user_id, user_account.account.account_id, pin, str(user_id), 0)
                await state.set_state(None)
                await cmd_info_message(user_id,
                                       'Password was unset',
                                       state)
            elif send_private_key:
                keypair = stellar_get_user_keypair(user_id, pin)
                await state.set_state(None)
                await send_message(user_id, f'Your private key is <code>{keypair.secret}</code>',
                                   reply_markup=get_kb_del_return(user_id))
            else:
                xdr = stellar_user_sign(xdr, user_id, str(pin))
                await state.set_state(None)
                await state.update_data(xdr=xdr)
                if current_state == PinState.sign_and_send:
                    await cmd_info_message(user_id,
                                           my_gettext(user_id, "try_send"),
                                           state)
                    # save_xdr_to_send(user_id, xdr)
                    resp = await async_stellar_send(xdr)
                    resp = MyResponse.from_dict(resp)
                    link_msg = ''
                    if resp.paging_token:
                        link_msg = f'\n(<a href="https://stellar.expert/explorer/public/tx/{resp.paging_token}">expert link</a>)'

                    await cmd_info_message(user_id,
                                           my_gettext(user_id, "send_good") + link_msg,
                                           state)
                    if buy_address:
                        await send_message(user_id=admin_id, msg=f'{user_id} buy {buy_address}', need_new_msg=True,
                                           reply_markup=get_kb_return(user_id))
                        stellar_unfree_wallet(user_id)

                    if donate:
                        await send_message(user_id=admin_id, msg=f'{user_id} donate {donate}', need_new_msg=True,
                                           reply_markup=get_kb_return(user_id))
                        stellar_add_donate(user_id, donate)

                if current_state == PinState.sign:
                    await cmd_show_sign(user_id, state,
                                        my_gettext(user_id, "your_xdr", (xdr,)),
                                        use_send=True)
    except BadRequestError as ex:
        # print(ex.extras.get("result_codes", '=( eror not found'))
        msg = f"{ex.title}, error {ex.status}, {ex.extras.get('result_codes', 'no extras')}"
        logger.info(['BadRequestError', msg, current_state])
        await cmd_info_message(user_id,
                               f"{my_gettext(user_id, 'send_error')}\n{msg}", state, resend_transaction=True)
    except BaseHorizonError as ex:
        msg = f"{ex.title}, error {ex.status}, {ex.extras.get('result_codes', 'no extras')}"
        logger.info(['BaseHorizonError', msg, current_state])
        await cmd_info_message(user_id,
                               f"{my_gettext(user_id, 'send_error')}\n{msg}", state, resend_transaction=True)
    except Exception as ex:
        logger.info(['ex', ex, current_state])
        await cmd_info_message(user_id, my_gettext(user_id, "bad_password"), state)


def get_kb_nopassword(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons = [[types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_yes_do'),
                                           callback_data=PinCallbackData(action="Enter").pack())],
               get_return_button(chat_id)]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(Text(text=["Sign"]))
async def cmd_sign(callback: types.CallbackQuery, state: FSMContext):
    await cmd_show_sign(callback.from_user.id, state, my_gettext(callback, 'send_xdr'))
    await state.set_state(StateSign.sending_xdr)
    await callback.answer()


@router.message(StateSign.sending_xdr)
async def cmd_send_xdr(message: types.Message, state: FSMContext):
    await cmd_check_xdr(message.text, message.from_user.id, state)
    await message.delete()


async def cmd_check_xdr(check_xdr: str, user_id, state: FSMContext):
    try:
        xdr = stellar_check_xdr(check_xdr)
        if xdr:
            await state.update_data(xdr=xdr)
            if check_xdr.find('mtl.ergvein.net/view') > -1 or check_xdr.find('eurmtl.me/sign_tools') > -1:
                await state.update_data(tools=check_xdr)
            await state.set_state(PinState.sign)
            await cmd_ask_pin(user_id, state)
        else:
            raise Exception('Bad xdr')
    except Exception as ex:
        logger.info(['my_state == MyState.StateSign', ex])
        await cmd_show_sign(user_id, state, my_gettext(user_id, 'bad_xdr', (check_xdr,)))


@router.callback_query(Text(text=["SendTr"]))
@router.callback_query(Text(text=["SendTools"]))
async def cmd_show_send_tr(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    xdr = data.get('xdr')
    tools = data.get('tools')
    try:
        if callback.data == "SendTools":
            try:
                # logger.info({"tx_body": xdr})
                if data.get('tools').find('mtl.ergvein.net/view') > -1:
                    rq = requests.post("https://mtl.ergvein.net/update", data={"tx_body": xdr})
                    parse_text = rq.text
                    if parse_text.find('Transaction history') > 0:
                        await cmd_info_message(callback, my_gettext(callback, 'check_here', (tools,)), state)
                    else:
                        parse_text = parse_text[parse_text.find('<section id="main">'):parse_text.find("</section>")]
                        await cmd_info_message(callback, parse_text[:4000], state)
                else:  # "https://eurmtl.me/sign_tools"
                    rq = requests.post(data.get('tools'), data={"tx_body": xdr})
                    parse_text = rq.text
                    #logger.info(parse_text)
                    if parse_text.find('Transaction signatures') > 0:
                        await cmd_info_message(callback, my_gettext(callback, 'check_here', (tools,)), state)
                    else:
                        parse_text = parse_text[parse_text.find('<section id="main">'):parse_text.find("</section>")]
                        await cmd_info_message(callback, parse_text[:4000], state)

            except Exception as ex:
                logger.info(['cmd_show_send_tr', callback, ex])
                await cmd_info_message(callback, my_gettext(callback, 'send_error'), state)

        else:
            await cmd_info_message(callback,
                                   my_gettext(callback, "try_send"),
                                   state)
            # save_xdr_to_send(callback.from_user.id, xdr)
            await async_stellar_send(xdr)
            await cmd_info_message(callback, my_gettext(callback, 'send_good'), state)
    except BaseHorizonError as ex:
        logger.info(['send BaseHorizonError', ex])
        msg = f"{ex.title}, error {ex.status}"
        await cmd_info_message(callback, f"{my_gettext(callback, 'send_error')}\n{msg}", state, resend_transaction=True)
    except Exception as ex:
        logger.exception(['send unknown error', ex])
        msg = 'unknown error'
        data[xdr] = xdr
        await cmd_info_message(callback, f"{my_gettext(callback, 'send_error')}\n{msg}", state, resend_transaction=True)


@router.message(PinState.ask_password)
async def cmd_password(message: types.Message, state: FSMContext):
    await state.update_data(pin=message.text)
    await message.delete()
    await state.set_state(PinState.sign_and_send)
    await sign_xdr(state, message.from_user.id)


@router.message(PinState.ask_password_set)
async def cmd_password_set(message: types.Message, state: FSMContext):
    await state.update_data(pin=message.text)
    await state.set_state(PinState.ask_password_set2)
    await message.delete()
    await send_message(message, my_gettext(message, 'resend_password'),
                       reply_markup=get_kb_return(message.from_user.id))


@router.message(PinState.ask_password_set2)
async def cmd_password_set2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    pin = data.get('pin', '')
    public_key = data.get('public_key', '')
    if data['pin'] == message.text:
        await state.set_state(None)
        pin_type = data.get('pin_type', '')
        stellar_change_password(user_id, public_key, str(user_id), pin, pin_type)
        await cmd_show_balance(user_id, state)
        await state.update_data(pin2='', pin='')
        await message.delete()
    else:
        await message.delete()
        await state.set_state(PinState.ask_password_set)
        await send_message(message, my_gettext(message, 'bad_passwords'),
                           reply_markup=get_kb_return(message.from_user.id))


@router.callback_query(Text(text=["ReSend"]))
async def cmd_resend(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    xdr = data.get('xdr')
    user_id = callback.from_user.id
    try:
        await cmd_info_message(user_id, my_gettext(user_id, "resend"), state)
        await async_stellar_send(xdr)
        await cmd_info_message(user_id, my_gettext(user_id, "send_good"), state)
    except BaseHorizonError as ex:
        logger.info(['ReSend BaseHorizonError', ex])
        msg = f"{ex.title}, error {ex.status}"
        await cmd_info_message(user_id, f"{my_gettext(user_id, 'send_error')}\n{msg}", state, resend_transaction=True)
    except Exception as ex:
        logger.exception(['ReSend unknown error', ex])
        msg = 'unknown error'
        data = await state.get_data()
        data[xdr] = xdr
        await cmd_info_message(user_id, f"{my_gettext(user_id, 'send_error')}\n{msg}", state, resend_transaction=True)
