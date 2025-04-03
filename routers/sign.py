import asyncio
from datetime import datetime, timedelta
import jsonpickle
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from sqlalchemy.orm import Session
from stellar_sdk.exceptions import BadRequestError, BaseHorizonError
from sulguk import SULGUK_PARSE_MODE

from db.requests import db_reset_balance, db_get_default_wallet
from other.mytypes import MyResponse
from other.web_tools import http_session_manager
from routers.start_msg import cmd_show_balance, cmd_info_message
from other.aiogram_tools import (my_gettext, send_message, cmd_show_sign, long_line,
                                 get_web_request, get_web_decoded_xdr)
from keyboards.common_keyboards import get_kb_return, get_return_button
from other.global_data import global_data, LogQuery, StateSign
from other.stellar_tools import (stellar_change_password, stellar_user_sign, stellar_check_xdr,
                                 async_stellar_send, stellar_get_user_account, stellar_get_user_keypair,
                                 stellar_is_free_wallet)


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
router.message.filter(F.chat.type == "private")

kb_cash = {}


@router.callback_query(F.data == "Yes_send_xdr")
async def cmd_yes_send(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await state.set_state(PinState.sign_and_send)

    await cmd_ask_pin(session, callback.from_user.id, state)
    await callback.answer()


async def cmd_ask_pin(session: Session, chat_id: int, state: FSMContext, msg=None):
    data = await state.get_data()
    user_account = (await stellar_get_user_account(session, chat_id)).account.account_id
    simple_account = user_account[:4] + '..' + user_account[-4:]
    if msg is None:
        msg = data.get('msg')
        if msg is None:
            msg = my_gettext(chat_id, "enter_password", (simple_account,))
            await state.update_data(msg=msg)

    pin_type = data.get("pin_type")
    pin = data.get("pin", '')
    current_state = await state.get_state()

    if pin_type is None:
        pin_type = db_get_default_wallet(session, chat_id).use_pin
        await state.update_data(pin_type=pin_type)

    if pin_type == 1:  # pin
        msg = msg + "\n" + ''.ljust(len(pin), '*') + '\n\n' + long_line()
        if current_state == PinState.sign:
            msg += my_gettext(chat_id, 'confirm_send_mini_xdr')
        await send_message(session, chat_id, msg, reply_markup=get_kb_pin(data))

    if pin_type == 2:  # password
        msg = my_gettext(chat_id, "send_password", (simple_account,))
        if current_state == PinState.sign:
            msg += my_gettext(chat_id, 'confirm_send_mini_xdr')
        await state.set_state(PinState.ask_password)
        await send_message(session, chat_id, msg, reply_markup=get_kb_return(chat_id))

    if pin_type == 0:  # no password
        await state.update_data(pin=str(chat_id))
        msg = my_gettext(chat_id, 'confirm_send_mini', (simple_account,))
        if current_state == PinState.sign:
            msg += my_gettext(chat_id, 'confirm_send_mini_xdr')
        await send_message(session, chat_id, msg,
                           reply_markup=get_kb_nopassword(chat_id))

    if pin_type == 10:  # ro
        await state.update_data(pin='ro')
        msg = my_gettext(chat_id, "your_xdr", (data['xdr'],))
        await cmd_show_sign(session, chat_id, state,
                            msg,
                            use_send=False, xdr_uri=data['xdr'])


def get_kb_pin(data: dict) -> types.InlineKeyboardMarkup:
    if data['user_lang'] in kb_cash:
        return kb_cash[data['user_lang']]
    else:
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

        kb_buttons.append(get_return_button(data['user_lang']))
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        kb_cash[data['user_lang']] = keyboard
        return keyboard


@router.callback_query(PinCallbackData.filter())
async def cq_pin(query: types.CallbackQuery, callback_data: PinCallbackData, state: FSMContext, session: Session):
    answer = callback_data.action
    user_id = query.from_user.id
    data = await state.get_data()
    pin = data.get('pin', '')
    current_state = await state.get_state()

    if answer in '1234567890ABCDEF':
        pin += answer
        await state.update_data(pin=pin)
        await cmd_ask_pin(session, user_id, state)
        await query.answer(''.ljust(len(pin), '*'))
        if current_state in (PinState.sign, PinState.sign_and_send):  # sign and send
            try:
                stellar_get_user_keypair(session, user_id, pin)  # test pin
                await sign_xdr(session, state, user_id)
            except:
                pass

    if answer == 'Del':
        pin = pin[:len(pin) - 1]
        await state.update_data(pin=pin)
        await cmd_ask_pin(session, user_id, state)
        await query.answer(''.ljust(len(pin), '*'))

    if answer == 'Enter':
        if current_state == PinState.set_pin:  # ask for save need pin2
            await state.update_data(pin2=pin, pin='')
            await state.set_state(PinState.set_pin2)
            await cmd_ask_pin(session, user_id, state, my_gettext(user_id, "resend_password"))
        if current_state == PinState.set_pin2:  # ask pin2 for save
            pin2 = data.get('pin2', '')
            public_key = data.get('public_key', '')
            await state.set_state(None)
            pin_type = data.get('pin_type', '')

            if pin == pin2:
                stellar_change_password(session, user_id, str(user_id), pin, pin_type)
                await cmd_show_balance(session, user_id, state)
            else:
                await state.update_data(pin2='', pin='')
                await state.set_state(PinState.set_pin)
                await query.answer(my_gettext(user_id, "bad_passwords"), show_alert=True)
        if current_state in (PinState.sign, PinState.sign_and_send):  # sign and send
            try:
                stellar_get_user_keypair(session, user_id, pin)  # test pin
                await sign_xdr(session, state, user_id)
            except:
                await query.answer(my_gettext(user_id, "bad_password"), show_alert=True)
                return True
        return True


@router.message(StateFilter(PinState.sign, PinState.sign_and_send))
async def cmd_password_from_pin(message: types.Message, state: FSMContext, session: Session):
    pin = message.text.upper()
    user_id = message.from_user.id
    await state.update_data(pin=pin)
    await message.delete()
    await cmd_ask_pin(session, user_id, state)
    try:
        stellar_get_user_keypair(session, user_id, pin)  # test pin
        await sign_xdr(session, state, user_id)
    except:
        pass


async def sign_xdr(session: Session, state, user_id):
    data = await state.get_data()
    current_state = await state.get_state()
    pin = data.get('pin', '')
    await state.set_state(None)
    xdr = data.get('xdr')
    fsm_func = data.get('fsm_func')
    fsm_after_send = data.get('fsm_after_send')
    # buy_address = data.get('buy_address')
    # usdt_address = data.get('usdt_address')
    # donate = data.get('donate')
    try:
        if user_id > 0:
            if fsm_func:
                fsm_func = jsonpickle.loads(fsm_func)
                await fsm_func(session, user_id, state)
            else:
                xdr = stellar_user_sign(session, xdr, user_id, str(pin))
                await state.set_state(None)
                await state.update_data(xdr=xdr)
                if current_state == PinState.sign_and_send:
                    await state.update_data(
                        try_sent_xdr=(datetime.now() + timedelta(minutes=5)).strftime('%d.%m.%Y %H:%M:%S'))
                    await cmd_info_message(session, user_id,
                                           my_gettext(user_id, "try_send")
                                           )
                    # save_xdr_to_send(user_id, xdr)
                    resp = await async_stellar_send(xdr)
                    resp = MyResponse.from_dict(resp)
                    await state.update_data(try_sent_xdr=None)
                    link_msg = ''
                    if resp.paging_token:
                        link_msg = f'\n(<a href="https://stellar.expert/explorer/public/tx/{resp.paging_token}">expert link</a>)'

                    msg = my_gettext(user_id, "send_good") + link_msg

                    success_msg = data.get('success_msg')
                    if success_msg:
                        msg = msg + '\n\n' + success_msg

                    await cmd_info_message(session, user_id, msg)
                    if success_msg:
                        await state.update_data(last_message_id=0)

                    if fsm_after_send:
                        fsm_after_send = jsonpickle.loads(fsm_after_send)
                        await fsm_after_send(session, user_id, state)
                if current_state == PinState.sign:
                    await cmd_show_sign(session, user_id, state,
                                        my_gettext(user_id, "your_xdr_sign", (xdr,)),
                                        use_send=True)
                global_data.log_queue.put_nowait(LogQuery(
                    user_id=user_id,
                    log_operation='sign',
                    log_operation_info=data.get('operation')
                ))

    except BadRequestError as ex:
        extras = ex.extras.get('result_codes', 'no extras') if ex.extras else ex.detail
        msg = f"{ex.title}, error {ex.status}, {extras}"
        logger.info(['BadRequestError', msg, current_state])
        await cmd_info_message(session, user_id,
                               f"{my_gettext(user_id, 'send_error')}\n{msg}", resend_transaction=True)
        await state.update_data(try_sent_xdr=None)
    except BaseHorizonError as ex:
        extras = ex.extras.get('result_codes', 'no extras') if ex.extras else ex.detail
        msg = f"{ex.title}, error {ex.status}, {extras}"
        logger.info(['BaseHorizonError', msg, current_state])
        await cmd_info_message(session, user_id,
                               f"{my_gettext(user_id, 'send_error')}\n{msg}", resend_transaction=True)
        await state.update_data(try_sent_xdr=None)
    except TimeoutError as ex:
        logger.info(['TimeoutError', ex, current_state])
        await cmd_info_message(session, user_id, 'timeout error =( ')
    except Exception as ex:
        logger.info(['ex', ex, current_state])
        await cmd_info_message(session, user_id, my_gettext(user_id, "bad_password"))
    await asyncio.to_thread(db_reset_balance,session, user_id)
    await state.update_data(pin='')


def get_kb_nopassword(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons = [[types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_yes_do'),
                                           callback_data=PinCallbackData(action="Enter").pack())],
               get_return_button(chat_id)]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data == "Sign")
async def cmd_sign(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await cmd_show_sign(session, callback.from_user.id, state, my_gettext(callback, 'send_xdr'))
    await state.set_state(StateSign.sending_xdr)
    await state.update_data(part_xdr='')
    await callback.answer()


@router.message(StateSign.sending_xdr)
async def cmd_send_xdr(message: types.Message, state: FSMContext, session: Session):
    await cmd_check_xdr(session, message.text, message.from_user.id, state)
    await message.delete()


async def cmd_check_xdr(session: Session, check_xdr: str, user_id, state: FSMContext):
    try:
        data = await state.get_data()
        part_xdr = data.get('part_xdr')

        if len(check_xdr) >= 4096:
            # possible we have xdr in 2\3 message
            part_xdr = part_xdr + check_xdr
            await state.update_data(part_xdr=part_xdr)
            await asyncio.sleep(3)

            data = await state.get_data()
            part_xdr = data.get('part_xdr')
            if len(part_xdr) == 0:
                return
            check_xdr = part_xdr

        # else:
        if part_xdr:
            check_xdr = part_xdr + check_xdr
            await state.update_data(part_xdr='')

        ####
        is_free = await stellar_is_free_wallet(session, user_id)
        xdr = await stellar_check_xdr(check_xdr, for_free_account=is_free)
        if xdr:
            await state.update_data(xdr=xdr)
            if check_xdr.find('eurmtl.me/sign_tools') > -1:
                await state.update_data(tools=check_xdr, operation='sign_tools')
            await state.set_state(PinState.sign)
            await cmd_ask_pin(session, user_id, state)
        else:
            raise Exception('Bad xdr')
    except Exception as ex:
        logger.info(['my_state == MyState.StateSign', ex])
        await cmd_show_sign(session, user_id, state, my_gettext(user_id, 'bad_xdr', (check_xdr,)))


@router.callback_query(F.data == "SendTr")
@router.callback_query(F.data == "SendTools")
async def cmd_show_send_tr(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    callback_url = data.get('callback_url')
    xdr = data.get('xdr')
    try:
        if callback.data == "SendTools":
            if callback_url:
                try:
                    response = await http_session_manager.get_web_request('POST',
                                                                          url=callback_url,
                                                                          data={"xdr": xdr})

                    logger.debug(f"Callback response: {response.data}")
                    if response.status == 200:
                        # Проверяем, есть ли return_url
                        return_url = data.get('return_url')
                        if return_url:
                            # Создаем клавиатуру с кнопкой "вернуться на сайт"
                            buttons = [[types.InlineKeyboardButton(
                                text=my_gettext(callback.from_user.id, 'return_to_site'),
                                url=return_url
                            )]]
                            buttons.append(get_return_button(callback.from_user.id))
                            keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
                            
                            # Отправляем сообщение с клавиатурой
                            await send_message(session, callback.from_user.id, f'SUCCESS', reply_markup=keyboard)
                        else:
                            await cmd_info_message(session, callback, f'SUCCESS')
                    else:
                        await cmd_info_message(session, callback, f'ERROR')
                except Exception as ex:
                    logger.info(['cmd_show_send_tr', callback, ex])
                    await cmd_info_message(session, callback, my_gettext(callback, 'send_error'))
            else:
                try:
                    response = await http_session_manager.get_web_request('POST',
                                                                          url='https://eurmtl.me/remote/update_signature',
                                                                          json={"xdr": xdr})

                    # status, response_json = await get_web_request('POST', url='https://eurmtl.me/remote/update_signature',
                    #                                               json={"xdr": xdr})
                    # { "SUCCESS": true/false, "MESSAGES": ["список", "сообщений", "об", "обработке"] }
                    msgs = '\n'.join(response.data.get('MESSAGES'))
                    if response.data.get('SUCCESS'):
                        await cmd_info_message(session, callback, f'SUCCESS\n{msgs}')
                    else:
                        await cmd_info_message(session, callback, f'ERROR\n{msgs}')
                    # else:
                    #     await cmd_info_message(session, callback, status)

                except Exception as ex:
                    logger.info(['cmd_show_send_tr', callback, ex])
                    await cmd_info_message(session, callback, my_gettext(callback, 'send_error'))
        else:
            await cmd_info_message(session, callback,
                                   my_gettext(callback, "try_send"),
                                   )
            # save_xdr_to_send(callback.from_user.id, xdr)
            await async_stellar_send(xdr)
            await cmd_info_message(session, callback, my_gettext(callback, 'send_good'), )
    except BaseHorizonError as ex:
        logger.info(['send BaseHorizonError', ex])
        msg = f"{ex.title}, error {ex.status}"
        await cmd_info_message(session, callback, f"{my_gettext(callback, 'send_error')}\n{msg}",
                               resend_transaction=True)
    except Exception as ex:
        logger.exception(['send unknown error', ex])
        msg = 'unknown error'
        data[xdr] = xdr
        await cmd_info_message(session, callback, f"{my_gettext(callback, 'send_error')}\n{msg}",
                               resend_transaction=True)


@router.message(PinState.ask_password)
async def cmd_password(message: types.Message, state: FSMContext, session: Session):
    await state.update_data(pin=message.text)
    await message.delete()
    await state.set_state(PinState.sign_and_send)
    await sign_xdr(session, state, message.from_user.id)


@router.message(PinState.ask_password_set)
async def cmd_password_set(message: types.Message, state: FSMContext, session: Session):
    await state.update_data(pin=message.text)
    await state.set_state(PinState.ask_password_set2)
    await message.delete()
    await send_message(session, message, my_gettext(message, 'resend_password'),
                       reply_markup=get_kb_return(message.from_user.id))


@router.message(PinState.ask_password_set2)
async def cmd_password_set2(message: types.Message, state: FSMContext, session: Session):
    data = await state.get_data()
    user_id = message.from_user.id
    pin = data.get('pin', '')
    # public_key = data.get('public_key', '')
    if data['pin'] == message.text:
        await state.set_state(None)
        pin_type = data.get('pin_type', '')
        stellar_change_password(session, user_id, str(user_id), pin, pin_type)
        await cmd_show_balance(session, user_id, state)
        await state.update_data(pin2='', pin='')
        await message.delete()
    else:
        await message.delete()
        await state.set_state(PinState.ask_password_set)
        await send_message(session, message, my_gettext(message, 'bad_passwords'),
                           reply_markup=get_kb_return(message.from_user.id))


@router.callback_query(F.data == "ReSend")
async def cmd_resend(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    xdr = data.get('xdr')
    user_id = callback.from_user.id
    try:
        await cmd_info_message(session, user_id, my_gettext(user_id, "resend"), )
        await async_stellar_send(xdr)
        await cmd_info_message(session, user_id, my_gettext(user_id, "send_good"), )
    except BaseHorizonError as ex:
        logger.info(['ReSend BaseHorizonError', ex])
        msg = f"{ex.title}, error {ex.status}"
        await cmd_info_message(session, user_id, f"{my_gettext(user_id, 'send_error')}\n{msg}", resend_transaction=True)
    except Exception as ex:
        logger.info(['ReSend unknown error', ex])
        msg = 'unknown error'
        data = await state.get_data()
        data[xdr] = xdr
        await cmd_info_message(session, user_id, f"{my_gettext(user_id, 'send_error')}\n{msg}", resend_transaction=True)


@router.callback_query(F.data == "Decode")
async def cmd_decode_xdr(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    xdr = data.get('xdr')

    msg = await get_web_decoded_xdr(xdr)

    # msg = msg.replace("&nbsp;", "\u00A0")
    await cmd_show_sign(session, callback.from_user.id, state, msg[:4000], use_send=True, parse_mode=SULGUK_PARSE_MODE)
