from typing import List, Union
from urllib.parse import urlparse, parse_qs

import jsonpickle
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from loguru import logger
from sqlalchemy.orm import Session
from stellar_sdk import Asset
from stellar_sdk.sep.federation import resolve_stellar_address

from db.requests import (db_get_user_account_by_username, db_get_book_data, db_get_user_data, db_get_wallets_list,
                         db_get_user)
from utils.aiogram_utils import my_gettext, send_message, bot, check_username
from keyboards.common_keyboards import get_kb_return, get_return_button, get_kb_yesno_send_xdr, \
    get_kb_offers_cancel
from mytypes import Balance
from utils.common_utils import get_user_id
from utils.stellar_utils import stellar_check_account, stellar_is_free_wallet, stellar_get_balances, stellar_pay, \
    stellar_get_user_account, my_float, float2str, db_update_username, stellar_get_selling_offers_sum


class StateSendToken(StatesGroup):
    sending_for = State()
    sending_sum = State()
    sending_memo = State()


class SendAssetCallbackData(CallbackData, prefix="send_asset_"):
    answer: str


router = Router()


def get_kb_send(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [[types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_choose'), switch_inline_query_current_chat='')],
               get_return_button(user_id)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


async def cmd_send_start(user_id: int, state: FSMContext, session: Session):
    msg = my_gettext(user_id, 'send_address')
    # keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True,
    #                                     keyboard=[[types.KeyboardButtonRequestUser()]])
    # await send_message(session,user_id, msg, reply_markup=keyboard)
    await send_message(session, user_id, msg, reply_markup=get_kb_send(user_id))
    await state.set_state(StateSendToken.sending_for)


@router.callback_query(F.data == "Send")
async def cmd_send_callback(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await cmd_send_start(callback.from_user.id, state, session)
    await callback.answer()


@router.message(Command(commands=["send"]))
async def cmd_send_message(message: types.Message, state: FSMContext, session: Session):
    await message.delete()
    await cmd_send_start(message.from_user.id, state, session)


@router.message(StateSendToken.sending_for, F.text)
async def cmd_send_for(message: Message, state: FSMContext, session: Session):
    data = await state.get_data()
    if '@' == data.get('qr', message.text)[0]:
        try:
            public_key, user_id = db_get_user_account_by_username(session, message.text)
            tmp_name = await check_username(user_id)
            if tmp_name is None or tmp_name.lower() != message.text.lower()[1:]:
                db_update_username(session, user_id, tmp_name)
                raise Exception("Имя пользователя не совпадает")
            logger.info(f"{message.from_user.id}, {message.text}, {message.text[1:]}, {public_key}")
        except Exception as ex:
            logger.info(["StateSendFor", data.get('qr', message.text), ex])
            await send_message(session, message.chat.id, my_gettext(message.chat.id, 'send_error2'),
                               reply_markup=get_kb_return(message))
            return
    else:
        public_key = data.get('qr', message.text)
    my_account = await stellar_check_account(public_key)
    if my_account:
        await state.update_data(send_address=my_account.account.account.account_id)
        if my_account.memo:
            await state.update_data(memo=my_account.memo, federal_memo=True)

        await state.set_state(None)
        await cmd_send_choose_token(message, state, session)
    else:
        free_wallet = await stellar_is_free_wallet(session, message.from_user.id)
        address = data.get('qr', message.text)
        if address.find('*') > 0:
            try:
                address = resolve_stellar_address(address).account_id
            except Exception as ex:
                logger.info(["StateSendFor", address, ex])
        if (not free_wallet) and (len(address) == 56) and (address[0] == 'G'):  # need activate
            await state.update_data(send_address=address)
            await state.set_state(state=None)
            await cmd_create_account(message.from_user.id, state, session)
        else:
            msg = my_gettext(message, 'send_error2') + '\n' + my_gettext(message, 'send_address')
            await send_message(session, message, msg, reply_markup=get_kb_return(message))


async def cmd_send_choose_token(message: types.Message, state: FSMContext, session: Session):
    data = await state.get_data()
    address = data.get('send_address')
    link = 'https://stellar.expert/explorer/public/account/' + address
    link = f'<a href="{link}">{address}</a>'

    msg = my_gettext(message, 'choose_token', (link,))
    asset_list = await stellar_get_balances(session, message.from_user.id)
    sender_asset_list = await stellar_get_balances(session, message.from_user.id, address)
    kb_tmp = []
    for token in asset_list:
        for sender_token in sender_asset_list:
            if token.asset_code == sender_token.asset_code:
                kb_tmp.append([types.InlineKeyboardButton(text=f"{token.asset_code} ({float2str(token.balance)})",
                                                          callback_data=SendAssetCallbackData(
                                                              answer=token.asset_code).pack()
                                                          )])
    kb_tmp.append(get_return_button(message))
    await send_message(session, message, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp),
                       need_new_msg=True)
    await state.update_data(assets=jsonpickle.encode(asset_list))


@router.callback_query(SendAssetCallbackData.filter())
async def cb_send_choose_token(callback: types.CallbackQuery, callback_data: SendAssetCallbackData, state: FSMContext,
                               session: Session):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data['assets'])

    for asset in asset_list:
        if asset.asset_code == answer:
            if my_float(asset.balance) == 0.0:
                await callback.answer(my_gettext(callback, "zero_sum"), show_alert=True)
            else:
                msg = my_gettext(callback, 'send_sum', (asset.asset_code,
                                                        asset.balance))

                # Get summ of tokens, blocked by Sell offers 
                blocked_token_sum = await stellar_get_selling_offers_sum(session, callback.from_user.id, asset)

                # If user has some assets that are blocked by offers, remind him\her about it.
                if blocked_token_sum > 0:
                    msg += '\n\n' + my_gettext(
                        callback,
                        'send_summ_blocked_by_offers',
                        (blocked_token_sum, asset.asset_code)
                    )

                await state.update_data(send_asset_code=asset.asset_code, send_asset_issuer=asset.asset_issuer,
                                        send_asset_max_sum=asset.balance, send_asset_blocked_sum=blocked_token_sum,
                                        msg=msg)
                data = await state.get_data()  # Get updated data

                await state.set_state(StateSendToken.sending_sum)
                keyboard = get_kb_offers_cancel(callback.from_user.id, data)
                await send_message(session, callback, msg, reply_markup=keyboard)
    return True


@router.callback_query(StateSendToken.sending_sum, F.data == "CancelOffers")
async def cq_send_cancel_offers_click(callback: types.CallbackQuery, state: FSMContext, session: Session):
    """
        Handle callback event 'CancelOffers_send' in state 'sending_sum'.
        Invert state of 'cancel offers' flag by clicking on button.
    """
    data = await state.get_data()
    data['cancel_offers'] = not data.get('cancel_offers', False)  # Invert checkbox state
    await state.update_data(cancel_offers=data['cancel_offers'])

    # Update message with the same text and changed button checkbox state
    msg = data['msg']
    keyboard = get_kb_offers_cancel(callback.from_user.id, data)
    await send_message(session, callback, msg, reply_markup=keyboard)


@router.message(StateSendToken.sending_sum)
async def cmd_send_get_sum(message: Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
        db_user = db_get_user(session, message.from_user.id)
        if db_user.can_5000 == 0 and send_sum > 5000:
            data = await state.get_data()
            msg0 = my_gettext(message, 'need_update_limits')
            await send_message(session, message, msg0 + data['msg'], reply_markup=get_kb_return(message))
            await message.delete()
            return

    except:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await cmd_send_04(session, message, state)
        await message.delete()
    else:
        keyboard = get_kb_offers_cancel(message.from_user.id, data)
        await send_message(session, message, f"{my_gettext(message, 'bad_sum')}\n{data['msg']}",
                           reply_markup=keyboard)


async def cmd_send_04(session: Session, message: types.Message, state: FSMContext, need_new_msg=None):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_address = data.get("send_address")
    send_memo = data.get("memo")
    federal_memo = data.get("federal_memo")
    send_asset_name = data["send_asset_code"]
    send_asset_issuer = data["send_asset_issuer"]
    cancel_offers = data.get('cancel_offers', False)

    # Add msg about cancelling offers to the confirmation request
    msg = my_gettext(
        message,
        'confirm_send',
        (float2str(send_sum), send_asset_name, send_address, send_memo)
    )
    if cancel_offers:
        msg = msg + my_gettext(message, 'confirm_cancel_offers', (send_asset_name,))

    xdr = await stellar_pay((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                            send_address,
                            Asset(send_asset_name, send_asset_issuer), send_sum, memo=send_memo,
                            cancel_offers=cancel_offers)

    await state.update_data(xdr=xdr, operation='send', success_msg=my_gettext(message, 'confirm_send_success',
                                                                              (float2str(send_sum), send_asset_name,
                                                                               send_address, send_memo)))

    add_button_memo = federal_memo is None
    await send_message(session, message, msg,
                       reply_markup=get_kb_yesno_send_xdr(message, add_button_memo=add_button_memo),
                       need_new_msg=need_new_msg)


@router.callback_query(F.data == "Memo")
async def cmd_get_memo(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'send_memo')
    await state.set_state(StateSendToken.sending_memo)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateSendToken.sending_memo)
async def cmd_send_memo(message: Message, state: FSMContext, session: Session):
    send_memo = message.text[:28]

    if len(send_memo) > 0:
        await state.update_data(memo=send_memo)
    await cmd_send_04(session, message, state, need_new_msg=True)


async def cmd_create_account(user_id: int, state: FSMContext, session: Session):
    data = await state.get_data()

    send_sum = data.get('activate_sum', 5)
    asset_list = await stellar_get_balances(session, user_id, asset_filter='XLM')
    send_asset_code = asset_list[0].asset_code
    send_asset_issuer = asset_list[0].asset_issuer
    send_address = data.get('send_address', 'None 0_0')
    msg = my_gettext(user_id, 'confirm_activate', (send_address, send_sum))

    xdr = await stellar_pay((await stellar_get_user_account(session, user_id)).account.account_id,
                            send_address,
                            Asset(send_asset_code, send_asset_issuer), send_sum, create=True)

    await state.update_data(xdr=xdr, send_asset_code=send_asset_code, send_asset_issuer=send_asset_issuer,
                            send_sum=send_sum)

    kb = get_kb_yesno_send_xdr(user_id)
    kb.inline_keyboard.insert(1, [types.InlineKeyboardButton(text='Send 15 xlm',
                                                             callback_data="Send15xlm")])
    await send_message(session, user_id, msg, reply_markup=kb, need_new_msg=True)


@router.callback_query(F.data == "Send15xlm")
async def cmd_get_memo(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await state.update_data(activate_sum=15)
    await cmd_create_account(callback.from_user.id, state, session)


@router.message(StateSendToken.sending_for, F.photo)
@router.message(F.photo)
async def handle_docs_photo(message: types.Message, state: FSMContext, session: Session):
    logger.info(f'{message.from_user.id}')
    if message.photo:
        await bot.download(message.photo[-1], destination=f'qr/{message.from_user.id}.jpg')
        from PIL import Image
        from pyzbar.pyzbar import decode
        data = decode(Image.open(f"qr/{message.from_user.id}.jpg"))
        if data:
            logger.info(str(data[0].data))
            qr_data = data[0].data.decode()
            if len(qr_data) == 56 and qr_data[0] == 'G':
                await state.update_data(qr=qr_data, last_message_id=0)
                await message.reply(qr_data)
                await cmd_send_for(message, state, session)
            elif len(qr_data) > 56 and qr_data.startswith('web+stellar:pay'):
                parsed = urlparse(qr_data)
                query_parameters = parse_qs(parsed.query)

                destination = query_parameters.get("destination")[0]
                amount = query_parameters.get("amount")[0]
                asset_code = query_parameters.get("asset_code")[0]
                asset_issuer = query_parameters.get("asset_issuer")[0]
                memo = query_parameters.get("memo")
                if memo:
                    memo = memo[0]

                await state.update_data(send_sum=amount,
                                        send_address=destination,
                                        memo=memo,
                                        send_asset_code=asset_code,
                                        send_asset_issuer=asset_issuer,
                                        last_message_id=0)

                await cmd_send_04(session, message, state)
            else:
                await message.reply('Bad QR code =(')
            # await message.delete()


@router.inline_query(F.chat_type == "sender")
async def cmd_inline_query(inline_query: types.InlineQuery, session: Session, ):
    if inline_query.chat_type != "sender":
        await inline_query.answer([], is_personal=True, cache_time=100)
        return
    results = []

    # Query from the address book
    book_data = db_get_book_data(session, inline_query.from_user.id)
    data = [(record.address, record.name) for record in book_data]

    # Query from the wallets
    wallet_data = db_get_wallets_list(session, inline_query.from_user.id)
    for record in wallet_data:
        simple_account = record.public_key[:4] + '..' + record.public_key[-4:]
        data.append((record.public_key, simple_account))

    if len(inline_query.query) > 2:
        for record in data:
            if (record[0] + record[1]).upper().find(inline_query.query.upper()) != -1:
                results.append(types.InlineQueryResultArticle(id=record[0],
                                                              title=record[1],
                                                              input_message_content=types.InputTextMessageContent(
                                                                  message_text=record[0])))

        # Query from users
        user_data = db_get_user_data(session, inline_query.query)
        for record in user_data:
            user = f'@{record.user_name}'
            results.append(types.InlineQueryResultArticle(id=user, title=user,
                                                          input_message_content=types.InputTextMessageContent(
                                                              message_text=user)))
        await inline_query.answer(
            results[:49], is_personal=True
        )
    else:
        for record in data:
            results.append(types.InlineQueryResultArticle(id=record[0],
                                                          title=record[1],
                                                          input_message_content=types.InputTextMessageContent(
                                                              message_text=record[0])))
        await inline_query.answer(
            results[:49], is_personal=True
        )
