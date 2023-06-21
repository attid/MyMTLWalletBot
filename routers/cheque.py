import asyncio, uuid, fb, jsonpickle
from dataclasses import dataclass
from datetime import datetime
from typing import Union
from aiogram import types, Router, F
from aiogram.filters import Text, Command, callback_data
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from loguru import logger
from keyboards.common_keyboards import get_kb_return, get_return_button, get_kb_yesno_send_xdr
from routers.common_setting import cmd_language
from routers.start_msg import cmd_info_message
from utils.aiogram_utils import send_message, bot, cheque_queue
from utils.lang_utils import my_gettext, set_last_message_id
from utils.stellar_utils import (my_float, float2str, stellar_pay, stellar_get_user_account, eurmtl_asset, is_new_user,
                                 stellar_create_new, async_stellar_send, stellar_sign, stellar_get_master,
                                 stellar_user_sign, stellar_get_user_public)

router = Router()
cheque_public = 'GCYTGJ4VFRWYULX746TAOF4V6RYCEWG3TJ42JMG3GMJF7BJ44VVX6OUT'


class StateCheque(StatesGroup):
    sending_sum = State()
    sending_comment = State()
    sending_count = State()


class ChequeCallbackData(CallbackData, prefix="cheque_callback_"):
    uuid: str
    cmd: str


@dataclass
class ChequeQuery:
    user_id: int
    cheque_uuid: str
    state: FSMContext
    username: str
    for_cancel: bool = False


@router.callback_query(Text(text=["CreateCheque"]))
async def cmd_create_cheque(callback: CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'send_cheque_sum')
    await send_message(callback, msg, reply_markup=get_kb_return(callback))
    await state.set_state(StateCheque.sending_sum)
    await callback.answer()


@router.message(StateCheque.sending_sum)
async def cmd_cheque_get_sum(message: Message, state: FSMContext):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await cmd_cheque_show(message, state)
        await message.delete()
    else:
        await message.delete()


async def cmd_cheque_show(message: Message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", str(uuid.uuid4().hex))
    await state.update_data(send_uuid=send_uuid)

    msg = my_gettext(message, 'send_cheque',
                     (float2str(send_sum), send_count, float(send_sum) * send_count, send_comment))

    xdr = await stellar_pay((await stellar_get_user_account(message.from_user.id)).account.account_id,
                            cheque_public,
                            eurmtl_asset, send_sum * send_count, memo=send_uuid[:16])

    await state.update_data(xdr=xdr, operation='cheque')

    await send_message(message, msg, reply_markup=get_kb_send_cheque(message.from_user.id))


def get_kb_send_cheque(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_create_cheque'), callback_data="ChequeExecute")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_amount'), callback_data="CreateCheque")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_count'), callback_data="ChequeCount")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_comment'), callback_data="ChequeComment")],
        get_return_button(user_id)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(Text(text=["ChequeCount"]))
async def cmd_cheque_count(callback: CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'kb_change_count')
    await send_message(callback, msg, reply_markup=get_kb_return(callback))
    await state.set_state(StateCheque.sending_count)
    await callback.answer()


@router.message(StateCheque.sending_count)
async def cmd_cheque_get_count(message: Message, state: FSMContext):
    try:
        send_count = int(message.text)
        if send_count < 1:
            send_count = 1
    except:
        send_count = 1

    if send_count > 0:
        await state.update_data(send_count=send_count)
        await state.set_state(None)

        await cmd_cheque_show(message, state)
        await message.delete()
    else:
        await message.delete()


@router.callback_query(Text(text=["ChequeComment"]))
async def cmd_cheque_comment(callback: CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'kb_change_comment')
    await send_message(callback, msg, reply_markup=get_kb_return(callback))
    await state.set_state(StateCheque.sending_comment)
    await callback.answer()


@router.message(StateCheque.sending_comment)
async def cmd_cheque_get_comment(message: Message, state: FSMContext):
    send_comment = message.text[:255]

    if send_comment:
        await state.update_data(send_comment=send_comment)
        await state.set_state(None)

        await cmd_cheque_show(message, state)
        await message.delete()
    else:
        await message.delete()


@router.callback_query(Text(text=["ChequeExecute"]))
async def cmd_cheque_comment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", str(uuid.uuid4().hex))
    msg = my_gettext(callback, 'confirm_send',
                     (float2str(send_sum * send_count), eurmtl_asset.code, cheque_public, send_uuid[:16]))
    await state.update_data(fsm_after_send=jsonpickle.dumps(cheque_after_send))
    await send_message(callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    await callback.answer()


async def cheque_after_send(user_id: int, state: FSMContext):
    data = await state.get_data()
    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", '')
    fb.execsql("insert into mymtlwalletbot_cheque (cheque_uuid, cheque_amount, cheque_count, user_id, cheque_comment) "
               "VALUES (?, ?, ?, ?, ?)", (send_uuid, send_sum, send_count, user_id, send_comment))
    set_last_message_id(user_id, 0)
    #  "send_cheque_resend": "You have cheque {} with sum {} EURMTL for {} users, total sum {} with comment \"{}\" you can send link {} or press button to send"
    link = f'https://t.me/{(await bot.me()).username}?start=cheque_{send_uuid}'
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_cheque'), switch_inline_query='')],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_cheque_info'),
                                    callback_data=ChequeCallbackData(uuid=send_uuid, cmd='info').pack())],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_cancel_cheque'),
                                    callback_data=ChequeCallbackData(uuid=send_uuid, cmd='cancel').pack())],
        get_return_button(user_id)
    ])
    await send_message(user_id, my_gettext(user_id, 'send_cheque_resend',
                                           (send_uuid, float2str(send_sum), send_count,
                                            float(send_sum) * send_count, send_comment, link)), reply_markup=kb)
    set_last_message_id(user_id, 0)


@router.callback_query(ChequeCallbackData.filter())
async def cb_send_choose_token(callback: types.CallbackQuery, callback_data: ChequeCallbackData, state: FSMContext):
    cmd = callback_data.cmd
    cheque_uuid = callback_data.uuid
    if fb.execsql1('select cheque_status from mymtlwalletbot_cheque where cheque_uuid = ? and user_id = ?',
                   (cheque_uuid, callback.from_user.id), '1') > 0:
        await callback.answer('Cheque was already cancelled', show_alert=True)
        return
    total_count = fb.execsql1(
        'select cheque_count from mymtlwalletbot_cheque where cheque_uuid = ? and user_id = ?',
        (cheque_uuid, callback.from_user.id), '0')
    receive_count = fb.execsql1('select count(*) from mymtlwalletbot_cheque ch '
                                'join mymtlwalletbot_cheque_history h on ch.cheque_id = h.cheque_id '
                                'where ch.cheque_uuid = ? and ch.user_id = ?', (cheque_uuid, callback.from_user.id),
                                '0')
    if cmd == 'info':
        await callback.answer(f'Cheque was received {receive_count} from {total_count}', show_alert=True)
    elif cmd == 'cancel':
        if total_count > receive_count:
            cheque_queue.put_nowait(ChequeQuery(user_id=callback.from_user.id, cheque_uuid=cheque_uuid, state=state,
                                                username='', for_cancel=True))
            await callback.answer()
        else:
            await callback.answer('Nothing to cancel', show_alert=True)


async def cmd_cancel_cheque(user_id: int, cheque_uuid: str, state: FSMContext):
    fb.execsql("update mymtlwalletbot_cheque set cheque_status = 1 where cheque_uuid = ? and user_id = ?",
               (cheque_uuid, user_id))
    total_count = fb.execsql1('select cheque_count from mymtlwalletbot_cheque where cheque_uuid = ? and user_id = ?',
                              (cheque_uuid, user_id), '0')
    receive_count = fb.execsql1('select count(*) from mymtlwalletbot_cheque ch '
                                'join mymtlwalletbot_cheque_history h on ch.cheque_id = h.cheque_id '
                                'where ch.cheque_uuid = ? and ch.user_id = ?', (cheque_uuid, user_id), '0')
    cheque_pay = fb.execsql1('select cheque_amount from mymtlwalletbot_cheque where cheque_uuid = ? and user_id = ?',
                             (cheque_uuid, user_id), '0')
    xdr = await stellar_pay(cheque_public,
                            stellar_get_user_public(user_id),
                            eurmtl_asset, (total_count - receive_count) * float(cheque_pay), memo=cheque_uuid[:16])
    xdr = stellar_sign(xdr, stellar_get_master().secret)

    await cmd_info_message(user_id, my_gettext(user_id, "try_send2"), state)
    await state.update_data(xdr=xdr, operation='cancel_cheque')
    await async_stellar_send(xdr)
    await cmd_info_message(user_id, my_gettext(user_id, 'send_good_cheque'), state)
    fb.reset_balance(user_id)


@router.inline_query(F.chat_type != "sender")
async def cmd_inline_query(inline_query: types.InlineQuery):
    results = []
    # all exist cheques
    data = fb.execsql('select cheque_id, cheque_uuid, cheque_amount, cheque_count, user_id, cheque_comment  '
                      ' from mymtlwalletbot_cheque ch where cheque_count > (select count(*) '
                      ' from mymtlwalletbot_cheque_history h where h.cheque_id = ch.cheque_id) '
                      ' and ch.user_id = ?  and ch.cheque_status = 0',
                      (inline_query.from_user.id,))
    bot_name = (await bot.me()).username
    for record in data:
        link = f'https://t.me/{bot_name}?start=cheque_{record[1]}'
        msg = my_gettext(inline_query.from_user.id, 'inline_cheque', (record[2], record[3], record[5]))
        results.append(types.InlineQueryResultArticle(id=record[1],
                                                      title=msg,
                                                      input_message_content=types.InputTextMessageContent(
                                                          message_text=msg),
                                                      reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                                                          [types.InlineKeyboardButton(
                                                              text=my_gettext(inline_query.from_user.id,
                                                                              'kb_get_cheque'), url=link)
                                                          ]
                                                      ]
                                                      )))
    await inline_query.answer(
        results[:49], is_personal=True
    )


########################################################################################################################
########################################################################################################################
########################################################################################################################


@router.message(Command(commands=["start"]), Text(contains="cheque_"))
async def cmd_start_cheque(message: types.Message, state: FSMContext, command: Command):
    await state.clear()

    # check address
    set_last_message_id(message.from_user.id, 0)
    await send_message(message.from_user.id, 'Loading')

    cheque_uuid = message.text.split(' ')[1][7:]
    await state.update_data(cheque_uuid=cheque_uuid)
    user_id = message.from_user.id

    cheque = fb.execsql("select cheque_id, cheque_uuid, cheque_amount, cheque_count, user_id, cheque_comment "
                        "from mymtlwalletbot_cheque where cheque_uuid = ? and cheque_status = 0", (cheque_uuid,))
    if not cheque or len(cheque) == 0 or (
            fb.execsql1('select count(*) from mymtlwalletbot_cheque_history h '
                        'where h.user_id = ? and h.cheque_id = ?', (user_id, cheque[0][0])) > 0) or (
            fb.execsql1('select count(*) from mymtlwalletbot_cheque_history h '
                        'where h.cheque_id = ?', (cheque[0][0],), '0') >= cheque[0][3]):
        await send_message(user_id, my_gettext(user_id, 'bad_cheque'), reply_markup=get_kb_return(user_id))
        return

    # "inline_cheque": "Чек на {} EURMTL, для {} получателя/получателей, \n\n \"{}\"",
    msg = my_gettext(user_id, 'inline_cheque', (cheque[0][2], cheque[0][3], cheque[0][5]))
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_get_cheque'), callback_data='ChequeYes')],
        get_return_button(user_id)
    ])

    await send_message(message, msg, reply_markup=kb)


@router.callback_query(Text(text=["ChequeYes"]))
async def cmd_cheque_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # await cmd_send_money_from_cheque(callback.from_user.id, state, cheque_uuid=data['cheque_uuid'],
    #                                 message=callback)
    cheque_queue.put_nowait(ChequeQuery(user_id=callback.from_user.id, cheque_uuid=data['cheque_uuid'], state=state,
                                        username=callback.from_user.username))
    await callback.answer()


async def cmd_send_money_from_cheque(user_id: int, state: FSMContext, cheque_uuid: str, username: str):
    cheque = fb.execsql("select cheque_id, cheque_uuid, cheque_amount, cheque_count, user_id, cheque_comment "
                        "from mymtlwalletbot_cheque where cheque_uuid = ? and cheque_status = 0", (cheque_uuid,))
    if not cheque or len(cheque) == 0 or (
            fb.execsql1('select count(*) from mymtlwalletbot_cheque_history h '
                        'where h.user_id = ? and h.cheque_id = ?', (user_id, cheque[0][0])) > 0) or (
            fb.execsql1('select count(*) from mymtlwalletbot_cheque_history h '
                        'where h.cheque_id = ?', (cheque[0][0],), '0') >= cheque[0][3]):
        await send_message(user_id, my_gettext(user_id, 'bad_cheque'), reply_markup=get_kb_return(user_id))
        return

    fb.execsql('insert into mymtlwalletbot_cheque_history (user_id, dt_block, cheque_id) VALUES (?, ?, ?)',
               (user_id, datetime.now(), cheque[0][0]))

    xdr = None
    was_new = is_new_user(user_id)
    if was_new:
        xdr = await stellar_create_new(user_id, username)

    xdr = await stellar_pay(cheque_public,
                            stellar_get_user_public(user_id),
                            eurmtl_asset, float(cheque[0][2]), memo=cheque[0][1][:16], xdr=xdr)
    if was_new:
        xdr = stellar_user_sign(xdr, user_id, str(user_id))

    xdr = stellar_sign(xdr, stellar_get_master().secret)

    await cmd_info_message(user_id, my_gettext(user_id, "try_send2"), state)
    await state.update_data(xdr=xdr, operation='receive_cheque')
    await async_stellar_send(xdr)
    await cmd_info_message(user_id, my_gettext(user_id, 'send_good_cheque'), state)
    fb.reset_balance(user_id)

    if was_new:
        await asyncio.sleep(2)
        await cmd_language(user_id, state)


async def cheque_worker():
    while True:  # not queue.empty():
        cheque_item: ChequeQuery = await cheque_queue.get()
        # logger.info(f'{cheque_item} start')

        try:
            if cheque_item.for_cancel:
                await cmd_cancel_cheque(cheque_item.user_id, cheque_item.cheque_uuid, cheque_item.state)
            else:
                await cmd_send_money_from_cheque(cheque_item.user_id, cheque_item.state, cheque_item.cheque_uuid,
                                                 cheque_item.username)

        except Exception as e:
            logger.warning(f' {cheque_item.cheque_uuid}-{cheque_item.user_id} failed {type(e)}')
        cheque_queue.task_done()
