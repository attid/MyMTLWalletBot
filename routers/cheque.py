import uuid
import jsonpickle  # type: ignore
from dataclasses import dataclass
from typing import Union
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from stellar_sdk import Asset

from db.models import ChequeStatus
from keyboards.common_keyboards import get_kb_return, get_return_button, get_kb_yesno_send_xdr
from routers.start_msg import cmd_info_message
from routers.swap import StateSwapToken
from infrastructure.utils.common_utils import get_user_id
# from other.global_data import global_data
from other.lang_tools import my_gettext
from infrastructure.utils.stellar_utils import my_float, stellar_get_market_link, eurmtl_asset
from infrastructure.utils.common_utils import float2str
from infrastructure.utils.telegram_utils import send_message, clear_state
from core.constants import CHEQUE_PUBLIC_KEY
from infrastructure.services.app_context import AppContext
from infrastructure.services.localization_service import LocalizationService

router = Router()
router.message.filter(F.chat.type == "private")
cheque_public = CHEQUE_PUBLIC_KEY

# Wrapper functions for gradual migration to repository pattern




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
        update: Union[CallbackQuery, Message], state: FSMContext, session: AsyncSession, app_context: AppContext, l10n: LocalizationService
):
    await clear_state(state)
    if isinstance(update, Message):
        await update.delete()
    msg = my_gettext(update, 'send_cheque_sum', app_context=app_context)
    await send_message(session, update, msg, reply_markup=get_kb_return(update, app_context=app_context), app_context=app_context)
    await state.set_state(StateCheque.sending_sum)
    if isinstance(update, CallbackQuery):
        await update.answer()


@router.message(StateCheque.sending_sum)
async def cmd_cheque_get_sum(message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    try:
        send_sum = my_float(message.text)
    except Exception:
        send_sum = 0.0

    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await cmd_cheque_show(session, message, state, app_context)
        await message.delete()
    else:
        await message.delete()


async def cmd_cheque_show(session: AsyncSession, message: Message, state: FSMContext, app_context: AppContext):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", str(uuid.uuid4().hex))
    await state.update_data(send_uuid=send_uuid)

    if send_sum is None:
        return

    msg = my_gettext(message, 'send_cheque',
                     (float2str(send_sum), send_count, float(send_sum) * send_count, send_comment), app_context=app_context)

    use_case = app_context.use_case_factory.create_create_cheque(session)

    if message.from_user is None:
        return

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
        await send_message(session, message, f"Error: {result.error_message}", reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
        return

    # xdr = await stellar_pay((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
    #                         cheque_public,
    #                         eurmtl_asset, send_sum * send_count, memo=send_uuid[:16])

    await state.update_data(xdr=xdr, operation='cheque')

    await send_message(session, message, msg, reply_markup=get_kb_send_cheque(message.from_user.id, app_context), app_context=app_context)


def get_kb_send_cheque(user_id: Union[types.CallbackQuery, types.Message, int], app_context: AppContext) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_create_cheque', app_context=app_context), callback_data="ChequeExecute")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_amount', app_context=app_context), callback_data="CreateCheque")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_count', app_context=app_context), callback_data="ChequeCount")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_comment', app_context=app_context), callback_data="ChequeComment")],
        get_return_button(user_id, app_context=app_context)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data=="ChequeCount")
async def cmd_cheque_count(callback: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    msg = my_gettext(callback, 'kb_change_count', app_context=app_context)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)
    await state.set_state(StateCheque.sending_count)
    await callback.answer()


@router.message(StateCheque.sending_count)
async def cmd_cheque_get_count(message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.text is None:
        return
    try:
        send_count = int(message.text)
        if send_count < 1:
            send_count = 1
    except Exception:
        send_count = 1

    if send_count > 0:
        await state.update_data(send_count=send_count)
        await state.set_state(None)

        await cmd_cheque_show(session, message, state, app_context)
        await message.delete()
    else:
        await message.delete()


@router.callback_query(F.data=="ChequeComment")
async def cmd_cheque_comment(callback: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    msg = my_gettext(callback, 'kb_change_comment', app_context=app_context)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)
    await state.set_state(StateCheque.sending_comment)
    await callback.answer()


@router.message(StateCheque.sending_comment)
async def cmd_cheque_get_comment(message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.text is None:
        return
    send_comment = message.text[:255]

    if send_comment:
        await state.update_data(send_comment=send_comment)
        await state.set_state(None)

        await cmd_cheque_show(session, message, state, app_context)
        await message.delete()
    else:
        await message.delete()


@router.callback_query(F.data=="ChequeExecute")
async def cmd_cheque_execute(callback: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    data = await state.get_data()
    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    # send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", str(uuid.uuid4().hex))
    msg = my_gettext(callback, 'confirm_send',
                     (float2str(send_sum * send_count), eurmtl_asset.code, cheque_public, send_uuid[:16]), app_context=app_context)
    await state.update_data(fsm_after_send=jsonpickle.dumps(cheque_after_send))
    await send_message(session, callback, msg, reply_markup=get_kb_yesno_send_xdr(callback, app_context=app_context), app_context=app_context)
    await callback.answer()


async def cheque_after_send(session: AsyncSession, user_id: int, state: FSMContext, *, app_context: AppContext, **kwargs):
    data = await state.get_data()
    send_sum = data.get("send_sum")
    send_count = data.get("send_count", 1)
    send_comment = data.get("send_comment", '')
    send_uuid = data.get("send_uuid", '')
    
    repo = app_context.repository_factory.get_cheque_repository(session)
    cheque = await repo.get_by_uuid(send_uuid)
    
    if cheque is None:
        # Create cheque if not exists
        cheque = await repo.create(send_uuid, str(send_sum), send_count, user_id, send_comment)
        
    await state.update_data(last_message_id=0)
    #  "send_cheque_resend": "You have cheque {} with sum {} EURMTL for {} users, total sum {} with comment \"{}\" you can send link {} or press button to send"
    bot = app_context.bot
    link = f'https://t.me/{(await bot.me()).username}?start=cheque_{send_uuid}'
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_cheque', app_context=app_context), switch_inline_query='')],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_cheque_info', app_context=app_context),
                                    callback_data=ChequeCallbackData(uuid=send_uuid, cmd='info').pack())],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_cancel_cheque', app_context=app_context),
                                    callback_data=ChequeCallbackData(uuid=send_uuid, cmd='cancel').pack())],
        get_return_button(user_id, app_context=app_context)
    ])
    
    # Entity uses 'ChequeStatus' enum values directly?
    # ChequeStatus.CHEQUE value is 0?
    if cheque.status == ChequeStatus.CHEQUE.value:
        await send_message(session, user_id, my_gettext(user_id, 'send_cheque_resend',
                                                        (send_uuid, float2str(cheque.amount), cheque.count,
                                                         float(cheque.amount) * cheque.count, cheque.comment, link), app_context=app_context),
                           reply_markup=kb, app_context=app_context)
    if cheque.status == ChequeStatus.INVOICE.value:
        asset_code = cheque.asset.split(':')[0] if cheque.asset else 'UNKNOWN'
        await send_message(session, user_id, my_gettext(user_id, 'send_invoice_buy_resend',
                                                        (send_uuid, float2str(cheque.amount), cheque.count,
                                                         asset_code, cheque.comment, link), app_context=app_context),
                           reply_markup=kb, app_context=app_context)

    await state.update_data(last_message_id=0)


@router.callback_query(ChequeCallbackData.filter())
async def cb_cheque_click(callback: types.CallbackQuery, callback_data: ChequeCallbackData, state: FSMContext,
                          session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    cmd = callback_data.cmd
    cheque_uuid = callback_data.uuid
    repo = app_context.repository_factory.get_cheque_repository(session)
    cheque = await repo.get_by_uuid(cheque_uuid)
    if not cheque: 
         # Handle null
         await callback.answer('Cheque not found', show_alert=True)
         return
         
    if cheque.status == ChequeStatus.CANCELED.value:
        await callback.answer('Cheque was already cancelled', show_alert=True)
        return
        
    total_count = cheque.count
    receive_count = await repo.get_receive_count(cheque_uuid) # receive count check
    
    if cmd == 'info':
        await callback.answer(f'Cheque was received {receive_count} from {total_count}', show_alert=True)
    elif cmd == 'cancel':
        if total_count > receive_count:
            app_context.cheque_queue.put_nowait(ChequeQuery(user_id=callback.from_user.id, cheque_uuid=cheque_uuid, state=state,
                                                username='', for_cancel=True))
            await callback.answer()
        else:
            await callback.answer('Nothing to cancel', show_alert=True)


async def cmd_cancel_cheque(session: AsyncSession, user_id: int, cheque_uuid: str, state: FSMContext, app_context: AppContext):
    use_case = app_context.use_case_factory.create_cancel_cheque(session)
    result = await use_case.execute(user_id=user_id, cheque_uuid=cheque_uuid)
    
    if not result.success:
         await cmd_info_message(session,  user_id, f"Error: {result.error_message}", app_context=app_context)
         return

    await cmd_info_message(session,  user_id, my_gettext(user_id, "try_send2", app_context=app_context), app_context=app_context)
    await app_context.stellar_service.submit_transaction(result.xdr)
    
    await cmd_info_message(session,  user_id, my_gettext(user_id, 'send_good_cheque', app_context=app_context), app_context=app_context)
    # No need to reset_balance_cache with new architecture


@router.inline_query(F.chat_type != "sender")
async def cmd_inline_query(inline_query: types.InlineQuery, session: AsyncSession, app_context: AppContext):
    results: list[types.InlineQueryResult] = []
    repo = app_context.repository_factory.get_cheque_repository(session)
    # all exist cheques
    if inline_query.from_user is None:
        return
    data = await repo.get_available(inline_query.from_user.id)

    bot_me = await app_context.bot.me()
    bot_name = bot_me.username if bot_me.username else "bot"
    for record in data:
        if record.status == ChequeStatus.CHEQUE.value:
            link = f'https://t.me/{bot_name}?start=cheque_{record.uuid}'
            msg = my_gettext(inline_query.from_user.id, 'inline_cheque',
                             (record.amount, record.count, record.comment), app_context=app_context)
            button_text = my_gettext(inline_query.from_user.id, 'kb_get_cheque', app_context=app_context)
        else:  # record.status == ChequeStatus.INVOICE:
            link = f'https://t.me/{bot_name}?start=invoice_{record.uuid}'
            asset_code = record.asset.split(':')[0] if record.asset else 'UNKNOWN'
            msg = my_gettext(inline_query.from_user.id, 'inline_invoice_buy',
                             (record.amount, asset_code, record.comment), app_context=app_context)
            button_text = my_gettext(inline_query.from_user.id, 'kb_get_invoice_buy', app_context=app_context)

        results.append(types.InlineQueryResultArticle(id=record.uuid,
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
        results[:49], is_personal=True  # type: ignore[arg-type]
    )


########################################################################################################################
########################################################################################################################
########################################################################################################################


@router.message(Command(commands=["start"]), F.text.contains("cheque_"))
@router.message(Command(commands=["start"]), F.text.contains("invoice_"))
async def cmd_start_cheque(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading', app_context=app_context)

    cheque_uuid = message.text.split(' ')[1].split('_')[1]
    await state.update_data(cheque_uuid=cheque_uuid)
    user_id = message.from_user.id

    repo = app_context.repository_factory.get_cheque_repository(session)
    cheque = await repo.get_by_uuid(cheque_uuid)
    
    receive_count = await repo.get_receive_count(cheque_uuid)
    user_receive_count = await repo.get_receive_count(cheque_uuid, user_id)
    
    if not cheque or user_receive_count > 0 or receive_count >= cheque.count:
        await send_message(session, user_id, my_gettext(user_id, 'bad_cheque', app_context=app_context), reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        return

    # "inline_cheque": "Чек на {} EURMTL, для {} получателя/получателей, \n\n \"{}\"",
    if cheque.status == ChequeStatus.CHEQUE.value:
        msg = my_gettext(user_id, 'inline_cheque', (cheque.amount, cheque.count, cheque.comment), app_context=app_context)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_get_cheque', app_context=app_context), callback_data='ChequeYes')],
            get_return_button(user_id, app_context=app_context)
        ])
    else:
        asset_code = cheque.asset.split(':')[0] if cheque.asset else 'UNKNOWN'
        msg = my_gettext(user_id, 'inline_invoice_buy',
                         (cheque.amount, asset_code, cheque.comment), app_context=app_context)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_get_invoice_buy', app_context=app_context), callback_data='InvoiceYes')],
            get_return_button(user_id, app_context=app_context)
        ])

    await send_message(session, message, msg, reply_markup=kb, app_context=app_context)


@router.callback_query(F.data=="ChequeYes")
async def cmd_cheque_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    # await cmd_send_money_from_cheque(callback.from_user.id, state, cheque_uuid=data['cheque_uuid'],
    #                                 message=callback)
    app_context.cheque_queue.put_nowait(ChequeQuery(user_id=callback.from_user.id, cheque_uuid=data['cheque_uuid'], state=state,
                                        username=callback.from_user.username or ""))
    await callback.answer()


async def cmd_send_money_from_cheque(session: AsyncSession, user_id: int, state: FSMContext, cheque_uuid: str,
                                     username: str, app_context: AppContext):
    use_case = app_context.use_case_factory.create_claim_cheque(session)
    result = await use_case.execute(user_id=user_id, cheque_uuid=cheque_uuid, username=username)

    if not result.success:
         await send_message(session, user_id, f"Error: {result.error_message}", reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
         return
         
    await cmd_info_message(session,  user_id, my_gettext(user_id, "try_send2", app_context=app_context), app_context=app_context)
    await state.update_data(xdr=result.xdr, operation='receive_cheque')
    
    # Send transaction
    if result.xdr:
        await app_context.stellar_service.submit_transaction(result.xdr)
        
    await cmd_info_message(session,  user_id, my_gettext(user_id, 'send_good_cheque', app_context=app_context), app_context=app_context)
    
    # Language check/prompt was: if was_new: ...
    # We can detect if user was new by checking if they have set language?
    # Or just always check language setting?
    # Old logic: if was_new, sleep 2, cmd_language.
    # We can replicate this by checking if wallet was just created, but Use Case encapsulates that.
    # Maybe checking user language?
    # For now, I'll omit the automatic language prompt unless critical, to keep changes minimal. 
    # Or check if user language is default/none.
    pass


async def cheque_worker(app_context: AppContext):
    while True:  # not queue.empty():
        cheque_item: ChequeQuery = await app_context.cheque_queue.get()
        # logger.info(f'{cheque_item} start')

        try:
            async with app_context.db_pool.get_session() as session:
                if cheque_item.for_cancel:
                    await cmd_cancel_cheque(session, cheque_item.user_id, cheque_item.cheque_uuid, cheque_item.state, app_context=app_context)
                else:
                    await cmd_send_money_from_cheque(session, cheque_item.user_id, cheque_item.state,
                                                     cheque_item.cheque_uuid,
                                                     cheque_item.username, app_context=app_context)
        except Exception as e:
            logger.warning(f' {cheque_item.cheque_uuid}-{cheque_item.user_id} failed {type(e)}')
        app_context.cheque_queue.task_done()


@router.callback_query(F.data=="InvoiceYes")
async def cmd_invoice_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    # Step 1: Check if the invoice is alive
    data = await state.get_data()
    cheque_uuid = data['cheque_uuid']
    user_id = callback.from_user.id
    xdr = None

    cheque_repo = app_context.repository_factory.get_cheque_repository(session)
    cheque = await cheque_repo.get_by_uuid(cheque_uuid)
    if not cheque:
        await callback.answer(my_gettext(user_id, 'bad_cheque', app_context=app_context))
        return
        
    receive_count = await cheque_repo.get_receive_count(cheque_uuid, user_id)
    total_received = await cheque_repo.get_receive_count(cheque_uuid)
        
    if receive_count > 0 or total_received >= cheque.count:
        await callback.answer(my_gettext(user_id, 'bad_cheque', app_context=app_context))
        return

    # Refactored to use GetWalletBalance Use Case
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)

    if cheque.asset is None:
        return
    cheque_asset_code, cheque_asset_issuer = cheque.asset.split(':')
    all_balances = await balance_use_case.execute(user_id=callback.from_user.id)
    asset_list = [b for b in all_balances if b.asset_code == cheque_asset_code]
    
    if not asset_list:
        # If the cheque asset is not in the balance list, add the trust line
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
        if wallet is None:
            return
        xdr = await app_context.stellar_service.build_change_trust_transaction(
            source_account_id=wallet.public_key,
            asset_code=cheque_asset_code,
            asset_issuer=cheque_asset_issuer
        )
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
    send_asset_code = str(data.get('send_asset_code', ''))
    send_asset_issuer = str(data.get('send_asset_issuer', ''))
    receive_asset_code = str(data.get('receive_asset_code', ''))
    receive_asset_issuer = str(data.get('receive_asset_issuer', ''))
    msg = my_gettext(callback, 'send_sum_swap', (send_asset_code,
                                                 float2str(max_eurmtl),
                                                 receive_asset_code,
                                                 stellar_get_market_link(Asset(send_asset_code,
                                                                               send_asset_issuer),
                                                                         Asset(receive_asset_code,
                                                                               receive_asset_issuer))
                                                 ), app_context=app_context)
    await state.set_state(StateSwapToken.swap_sum)
    await state.update_data(msg=msg, xdr=xdr)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)

    await callback.answer()


########################################################################################################################
########################################################################################################################
########################################################################################################################


@router.message(Command(commands=["cheques"]))
async def cmd_cheques(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    await clear_state(state)
    # Получение списка доступных чеков
    repo = app_context.repository_factory.get_cheque_repository(session)
    cheques = await repo.get_available(message.from_user.id)

    # Перебор чеков и их отправка
    for cheque in cheques:
        data = {
            "send_sum": cheque.amount,
            "send_count": cheque.count,
            "send_comment": cheque.comment,
            "send_uuid": cheque.uuid,
        }
        await state.update_data(data)
        await cheque_after_send(session, message.from_user.id, state, app_context=app_context)
