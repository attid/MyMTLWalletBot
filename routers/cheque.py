import asyncio, uuid, jsonpickle
from dataclasses import dataclass
from typing import Union
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from loguru import logger
from sqlalchemy.orm import Session
from stellar_sdk import Asset

from db.models import ChequeStatus
from keyboards.common_keyboards import get_kb_return, get_return_button, get_kb_yesno_send_xdr
from routers.common_setting import cmd_language
from routers.start_msg import cmd_info_message
from routers.swap import StateSwapToken
from other.aiogram_tools import send_message, clear_state
from other.common_tools import get_user_id
from other.global_data import global_data
from other.lang_tools import my_gettext
from other.stellar_tools import (my_float, float2str, stellar_pay, stellar_get_user_account, eurmtl_asset,
                                 db_is_new_user,
                                 stellar_create_new, async_stellar_send, stellar_sign, stellar_get_master,
                                 stellar_user_sign, stellar_get_balances, stellar_add_trust, stellar_get_market_link)

router = Router()
router.message.filter(F.chat.type == "private")
cheque_public = 'GCYTGJ4VFRWYULX746TAOF4V6RYCEWG3TJ42JMG3GMJF7BJ44VVX6OUT'

# Wrapper functions for gradual migration to repository pattern
def _get_cheque_repo(session):
    from infrastructure.persistence.sqlalchemy_cheque_repository import SqlAlchemyChequeRepository
    return SqlAlchemyChequeRepository(session)

async def db_get_cheque(session, cheque_uuid, user_id=None):
    repo = _get_cheque_repo(session)
    cheque = await repo.get_by_uuid(cheque_uuid, user_id)
    if cheque:
        # Return db model for backward compatibility
        from db.models import MyMtlWalletBotCheque
        from sqlalchemy.future import select
        stmt = select(MyMtlWalletBotCheque).where(MyMtlWalletBotCheque.cheque_uuid == cheque_uuid)
        if user_id:
            stmt = stmt.where(MyMtlWalletBotCheque.user_id == user_id)
        result = session.execute(stmt)
        return result.scalar_one_or_none()
    return None

async def db_add_cheque(session, send_uuid, send_sum, send_count, user_id, send_comment):
    repo = _get_cheque_repo(session)
    await repo.create(send_uuid, send_sum, send_count, user_id, send_comment)
    # Return db model for backward compatibility
    return await db_get_cheque(session, send_uuid)

async def db_get_cheque_receive_count(session, cheque_uuid, user_id=None):
    repo = _get_cheque_repo(session)
    return await repo.get_receive_count(cheque_uuid, user_id)

async def db_get_available_cheques(session, user_id):
    repo = _get_cheque_repo(session)
    cheques = await repo.get_available(user_id)
    # Return db models for backward compatibility
    from db.models import MyMtlWalletBotCheque
    from sqlalchemy.future import select
    from db.models import ChequeStatus
    from db.models import MyMtlWalletBotChequeHistory
    from sqlalchemy import func
    return session.query(
        MyMtlWalletBotCheque
    ).outerjoin(
        MyMtlWalletBotChequeHistory,
        MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id
    ).group_by(
        MyMtlWalletBotCheque
    ).having(
        func.count(MyMtlWalletBotChequeHistory.cheque_id) < MyMtlWalletBotCheque.cheque_count
    ).filter(
        MyMtlWalletBotCheque.user_id == user_id,
        MyMtlWalletBotCheque.cheque_status != ChequeStatus.CANCELED.value
    ).all()

async def db_add_cheque_history(session, user_id, cheque_id):
    repo = _get_cheque_repo(session)
    await repo.add_history(cheque_id, user_id)



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


@router.callback_query(F.data=="CreateCheque")
@router.message(Command('create_cheque'))
async def cmd_create_cheque(
        update: Union[CallbackQuery, Message], state: FSMContext, session: Session
):
    await clear_state(state)
    if isinstance(update, Message):
        await update.delete()
    msg = my_gettext(update, 'send_cheque_sum')
    await send_message(session, update, msg, reply_markup=get_kb_return(update))
    await state.set_state(StateCheque.sending_sum)
    if isinstance(update, CallbackQuery):
        await update.answer()


@router.message(StateCheque.sending_sum)
async def cmd_cheque_get_sum(message: Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await cmd_cheque_show(session, message, state)
        await message.delete()
    else:
        await message.delete()


async def cmd_cheque_show(session: Session, message: Message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", str(uuid.uuid4().hex))
    await state.update_data(send_uuid=send_uuid)

    msg = my_gettext(message, 'send_cheque',
                     (float2str(send_sum), send_count, float(send_sum) * send_count, send_comment))

    # Refactored to use Clean Architecture Use Case
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    from infrastructure.services.stellar_service import StellarService
    from core.use_cases.cheque.create_cheque import CreateCheque
    from other.config_reader import config

    repo = SqlAlchemyWalletRepository(session)
    service = StellarService(horizon_url=config.horizon_url)
    use_case = CreateCheque(repo, service)

    result = await use_case.execute(
        user_id=message.from_user.id,
        amount=send_sum,
        count=send_count,
        memo=send_uuid[:16]
    )

    if result.success:
        xdr = result.xdr
    else:
        logger.error(f"CreateCheque failed: {result.error_message}")
        await send_message(session, message, f"Error: {result.error_message}", reply_markup=get_kb_return(message))
        return

    # xdr = await stellar_pay((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
    #                         cheque_public,
    #                         eurmtl_asset, send_sum * send_count, memo=send_uuid[:16])

    await state.update_data(xdr=xdr, operation='cheque')

    await send_message(session, message, msg, reply_markup=get_kb_send_cheque(message.from_user.id))


def get_kb_send_cheque(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_create_cheque'), callback_data="ChequeExecute")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_amount'), callback_data="CreateCheque")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_count'), callback_data="ChequeCount")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_comment'), callback_data="ChequeComment")],
        get_return_button(user_id)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data=="ChequeCount")
async def cmd_cheque_count(callback: CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'kb_change_count')
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
    await state.set_state(StateCheque.sending_count)
    await callback.answer()


@router.message(StateCheque.sending_count)
async def cmd_cheque_get_count(message: Message, state: FSMContext, session: Session):
    try:
        send_count = int(message.text)
        if send_count < 1:
            send_count = 1
    except:
        send_count = 1

    if send_count > 0:
        await state.update_data(send_count=send_count)
        await state.set_state(None)

        await cmd_cheque_show(session, message, state)
        await message.delete()
    else:
        await message.delete()


@router.callback_query(F.data=="ChequeComment")
async def cmd_cheque_comment(callback: CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'kb_change_comment')
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
    await state.set_state(StateCheque.sending_comment)
    await callback.answer()


@router.message(StateCheque.sending_comment)
async def cmd_cheque_get_comment(message: Message, state: FSMContext, session: Session):
    send_comment = message.text[:255]

    if send_comment:
        await state.update_data(send_comment=send_comment)
        await state.set_state(None)

        await cmd_cheque_show(session, message, state)
        await message.delete()
    else:
        await message.delete()


@router.callback_query(F.data=="ChequeExecute")
async def cmd_cheque_execute(callback: CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    # send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", str(uuid.uuid4().hex))
    msg = my_gettext(callback, 'confirm_send',
                     (float2str(send_sum * send_count), eurmtl_asset.code, cheque_public, send_uuid[:16]))
    await state.update_data(fsm_after_send=jsonpickle.dumps(cheque_after_send))
    await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback))
    await callback.answer()


async def cheque_after_send(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", '')
    cheque = await db_get_cheque(session, send_uuid)
    if cheque is None:
        cheque = await db_add_cheque(session, send_uuid, send_sum, send_count, user_id, send_comment)
    await state.update_data(last_message_id=0)
    #  "send_cheque_resend": "You have cheque {} with sum {} EURMTL for {} users, total sum {} with comment \"{}\" you can send link {} or press button to send"
    link = f'https://t.me/{(await global_data.bot.me()).username}?start=cheque_{send_uuid}'
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_cheque'), switch_inline_query='')],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_cheque_info'),
                                    callback_data=ChequeCallbackData(uuid=send_uuid, cmd='info').pack())],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_cancel_cheque'),
                                    callback_data=ChequeCallbackData(uuid=send_uuid, cmd='cancel').pack())],
        get_return_button(user_id)
    ])
    if cheque.cheque_status == ChequeStatus.CHEQUE.value:
        await send_message(session, user_id, my_gettext(user_id, 'send_cheque_resend',
                                                        (send_uuid, float2str(send_sum), send_count,
                                                         float(send_sum) * send_count, send_comment, link)),
                           reply_markup=kb)
    if cheque.cheque_status == ChequeStatus.INVOICE.value:
        await send_message(session, user_id, my_gettext(user_id, 'send_invoice_buy_resend',
                                                        (send_uuid, float2str(send_sum), send_count,
                                                         cheque.cheque_asset.split(':')[0], send_comment, link)),
                           reply_markup=kb)

    await state.update_data(last_message_id=0)


@router.callback_query(ChequeCallbackData.filter())
async def cb_cheque_click(callback: types.CallbackQuery, callback_data: ChequeCallbackData, state: FSMContext,
                          session: Session):
    cmd = callback_data.cmd
    cheque_uuid = callback_data.uuid
    cheque = await db_get_cheque(session, cheque_uuid, callback.from_user.id)
    if cheque.cheque_status == 1:
        await callback.answer('Cheque was already cancelled', show_alert=True)
        return
    total_count = cheque.cheque_count
    receive_count = await db_get_cheque_receive_count(session, cheque_uuid)
    if cmd == 'info':
        await callback.answer(f'Cheque was received {receive_count} from {total_count}', show_alert=True)
    elif cmd == 'cancel':
        if total_count > receive_count:
            global_data.cheque_queue.put_nowait(ChequeQuery(user_id=callback.from_user.id, cheque_uuid=cheque_uuid, state=state,
                                                username='', for_cancel=True))
            await callback.answer()
        else:
            await callback.answer('Nothing to cancel', show_alert=True)


async def cmd_cancel_cheque(session: Session, user_id: int, cheque_uuid: str, state: FSMContext):
    cheque = await db_get_cheque(session, cheque_uuid, user_id)
    cheque.cheque_status = 1
    total_count = cheque.cheque_count
    receive_count = await db_get_cheque_receive_count(session, cheque_uuid)
    cheque_pay = cheque.cheque_amount
    
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = SqlAlchemyWalletRepository(session)
    wallet = await repo.get_default_wallet(user_id)
    
    xdr = await stellar_pay(cheque_public,
                            wallet.public_key,
                            eurmtl_asset, (total_count - receive_count) * float(cheque_pay), memo=cheque_uuid[:16])
    xdr = stellar_sign(xdr, stellar_get_master(session).secret)

    await cmd_info_message(session,  user_id, my_gettext(user_id, "try_send2"))
    await state.update_data(xdr=xdr, operation='cancel_cheque')
    await async_stellar_send(xdr)
    await cmd_info_message(session,  user_id, my_gettext(user_id, 'send_good_cheque'))
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = SqlAlchemyWalletRepository(session)
    await repo.reset_balance_cache(user_id)


@router.inline_query(F.chat_type != "sender")
async def cmd_inline_query(inline_query: types.InlineQuery, session: Session):
    results = []
    # all exist cheques
    data = await db_get_available_cheques(session, inline_query.from_user.id)

    bot_name = (await global_data.bot.me()).username
    for record in data:
        if record.cheque_status == ChequeStatus.CHEQUE.value:
            link = f'https://t.me/{bot_name}?start=cheque_{record.cheque_uuid}'
            msg = my_gettext(inline_query.from_user.id, 'inline_cheque',
                             (record.cheque_amount, record.cheque_count, record.cheque_comment))
            button_text = my_gettext(inline_query.from_user.id, 'kb_get_cheque')
        else:  # record.cheque_status == ChequeStatus.INVOICE:
            link = f'https://t.me/{bot_name}?start=invoice_{record.cheque_uuid}'
            msg = my_gettext(inline_query.from_user.id, 'inline_invoice_buy',
                             (record.cheque_asset.split(':')[0], record.cheque_comment))
            button_text = my_gettext(inline_query.from_user.id, 'kb_get_invoice_buy')

        results.append(types.InlineQueryResultArticle(id=record.cheque_uuid,
                                                      title=msg,
                                                      input_message_content=types.InputTextMessageContent(
                                                          message_text=msg),
                                                      reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                                                          [types.InlineKeyboardButton(
                                                              text=button_text, url=link)
                                                          ]
                                                      ]
                                                      )))

    await inline_query.answer(
        results[:49], is_personal=True
    )


########################################################################################################################
########################################################################################################################
########################################################################################################################


@router.message(Command(commands=["start"]), F.text.contains("cheque_"))
@router.message(Command(commands=["start"]), F.text.contains("invoice_"))
async def cmd_start_cheque(message: types.Message, state: FSMContext, session: Session):
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading')

    cheque_uuid = message.text.split(' ')[1].split('_')[1]
    await state.update_data(cheque_uuid=cheque_uuid)
    user_id = message.from_user.id

    cheque = await db_get_cheque(session, cheque_uuid)
    if not cheque or await db_get_cheque_receive_count(session, cheque_uuid, user_id) > 0 \
            or await db_get_cheque_receive_count(session, cheque_uuid) >= cheque.cheque_count:
        await send_message(session, user_id, my_gettext(user_id, 'bad_cheque'), reply_markup=get_kb_return(user_id))
        return

    # "inline_cheque": "Чек на {} EURMTL, для {} получателя/получателей, \n\n \"{}\"",
    if cheque.cheque_status == ChequeStatus.CHEQUE.value:
        msg = my_gettext(user_id, 'inline_cheque', (cheque.cheque_amount, cheque.cheque_count, cheque.cheque_comment))
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_get_cheque'), callback_data='ChequeYes')],
            get_return_button(user_id)
        ])
    else:
        msg = my_gettext(user_id, 'inline_invoice_buy',
                         (cheque.cheque_asset.split(':')[0], cheque.cheque_comment))
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_get_invoice_buy'), callback_data='InvoiceYes')],
            get_return_button(user_id)
        ])

    await send_message(session, message, msg, reply_markup=kb)


@router.callback_query(F.data=="ChequeYes")
async def cmd_cheque_yes(callback: CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    # await cmd_send_money_from_cheque(callback.from_user.id, state, cheque_uuid=data['cheque_uuid'],
    #                                 message=callback)
    global_data.cheque_queue.put_nowait(ChequeQuery(user_id=callback.from_user.id, cheque_uuid=data['cheque_uuid'], state=state,
                                        username=callback.from_user.username))
    await callback.answer()


async def cmd_send_money_from_cheque(session: Session, user_id: int, state: FSMContext, cheque_uuid: str,
                                     username: str):
    cheque = await db_get_cheque(session, cheque_uuid)
    if not cheque or await db_get_cheque_receive_count(session, cheque_uuid, user_id) > 0 \
            or await db_get_cheque_receive_count(session, cheque_uuid) >= cheque.cheque_count:
        await send_message(session, user_id, my_gettext(user_id, 'bad_cheque'), reply_markup=get_kb_return(user_id))
        return

    await db_add_cheque_history(session, user_id, cheque.cheque_id)

    xdr = None
    was_new = db_is_new_user(session, user_id)
    if was_new:
        xdr = await stellar_create_new(session, user_id, username)

    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = SqlAlchemyWalletRepository(session)
    wallet = await repo.get_default_wallet(user_id)
    
    xdr = await stellar_pay(cheque_public,
                            wallet.public_key,
                            eurmtl_asset, float(cheque.cheque_amount), memo=cheque.cheque_uuid[:16], xdr=xdr)
    if was_new:
        xdr = stellar_user_sign(session, xdr, user_id, str(user_id))

    xdr = stellar_sign(xdr, stellar_get_master(session).secret)

    await cmd_info_message(session,  user_id, my_gettext(user_id, "try_send2"))
    await state.update_data(xdr=xdr, operation='receive_cheque')
    await async_stellar_send(xdr)
    await cmd_info_message(session,  user_id, my_gettext(user_id, 'send_good_cheque'))
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    repo = SqlAlchemyWalletRepository(session)
    await repo.reset_balance_cache(user_id)

    if was_new:
        await asyncio.sleep(2)
        await cmd_language(session, user_id)


async def cheque_worker(session_pool):
    while True:  # not queue.empty():
        cheque_item: ChequeQuery = await global_data.cheque_queue.get()
        # logger.info(f'{cheque_item} start')

        try:
            with session_pool() as session:
                if cheque_item.for_cancel:
                    await cmd_cancel_cheque(session, cheque_item.user_id, cheque_item.cheque_uuid, cheque_item.state)
                else:
                    await cmd_send_money_from_cheque(session, cheque_item.user_id, cheque_item.state,
                                                     cheque_item.cheque_uuid,
                                                     cheque_item.username)
        except Exception as e:
            logger.warning(f' {cheque_item.cheque_uuid}-{cheque_item.user_id} failed {type(e)}')
        global_data.cheque_queue.task_done()


@router.callback_query(F.data=="InvoiceYes")
async def cmd_invoice_yes(callback: CallbackQuery, state: FSMContext, session: Session):
    # Step 1: Check if the invoice is alive
    data = await state.get_data()
    cheque_uuid = data['cheque_uuid']
    user_id = callback.from_user.id
    xdr = None

    cheque = await db_get_cheque(session, cheque_uuid)
    if not cheque or await db_get_cheque_receive_count(session, cheque_uuid, user_id) > 0 \
            or await db_get_cheque_receive_count(session, cheque_uuid) >= cheque.cheque_count:
        await callback.answer(my_gettext(user_id, 'bad_cheque'))
        return

    # Step 2: Check if the asset from the cheque is in the balance
    cheque_asset_code, cheque_asset_issuer = cheque.cheque_asset.split(':')
    
    # Refactored to use GetWalletBalance Use Case
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    from infrastructure.services.stellar_service import StellarService
    from core.use_cases.wallet.get_balance import GetWalletBalance
    from other.config_reader import config as app_config
    repo = SqlAlchemyWalletRepository(session)
    service = StellarService(horizon_url=app_config.horizon_url)
    balance_use_case = GetWalletBalance(repo, service)
    all_balances = await balance_use_case.execute(user_id=callback.from_user.id)
    asset_list = [b for b in all_balances if b.asset_code == cheque_asset_code]
    if not asset_list:
        # If the cheque asset is not in the balance list, add the trust line
        user_key = await stellar_get_user_account(session, callback.from_user.id)
        xdr = await stellar_add_trust(user_key.account.account_id, Asset(cheque_asset_code, cheque_asset_issuer))
    eurmtl_balances = [b for b in all_balances if b.asset_code == eurmtl_asset.code]
    if eurmtl_balances:
        max_eurmtl = eurmtl_balances[0].balance
    else:
        max_eurmtl = 0

    await state.update_data(send_asset_code=eurmtl_asset.code,
                            send_asset_issuer=eurmtl_asset.issuer,
                            receive_asset_code=cheque_asset_code,
                            receive_asset_issuer=cheque_asset_issuer
                            )
    data = await state.get_data()
    msg = my_gettext(callback, 'send_sum_swap', (data.get('send_asset_code'),
                                                 max_eurmtl,
                                                 data.get('receive_asset_code'),
                                                 stellar_get_market_link(Asset(data.get("send_asset_code"),
                                                                               data.get("send_asset_issuer")),
                                                                         Asset(data.get('receive_asset_code'),
                                                                               data.get('receive_asset_issuer')))
                                                 ))
    await state.set_state(StateSwapToken.swap_sum)
    await state.update_data(msg=msg, xdr=xdr)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################


@router.message(Command(commands=["cheques"]))
async def cmd_cheques(message: types.Message, state: FSMContext, session: Session):
    await clear_state(state)
    # Получение списка доступных чеков
    cheques = await db_get_available_cheques(session, message.from_user.id)

    # Перебор чеков и их отправка
    for cheque in cheques:
        data = {
            "send_sum": cheque.cheque_amount,
            "send_count": cheque.cheque_count,
            "send_comment": cheque.cheque_comment,
            "send_uuid": cheque.cheque_uuid,
        }
        await state.update_data(data)
        await cheque_after_send(session, message.from_user.id, state)
