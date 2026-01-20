from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from keyboards.common_keyboards import get_return_button, get_kb_return
from routers.send import cmd_send_04
from infrastructure.utils.telegram_utils import send_message, long_line
from other.lang_tools import my_gettext
# from other.stellar_tools import *
from infrastructure.utils.stellar_utils import my_float
from other.config_reader import config
from other.grist_tools import load_fest_info
from infrastructure.services.app_context import AppContext
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()
router.message.filter(F.chat.type == "private")


class SendLevel24(CallbackData, prefix="send_level_24"):
    level_1: str


class StateFest(StatesGroup):
    sending_sum = State()


@router.message(StateFest.sending_sum)
async def cmd_fest_get_sum(message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    await message.delete()
    try:
        send_sum = my_float(message.text)
    except ValueError:
        send_sum = 0.0

    data = await state.get_data()
    level_1 = data.get('level_1')
    if not level_1:
        return
    address_id = config.fest_menu[level_1]

    if send_sum > 0.0:
        await state.set_state(None)

        await state.update_data(send_sum=send_sum,
                                send_address=address_id,
                                # memo=seller.get('memo', None),
                                send_asset_code='EURMTL',
                                send_asset_issuer='GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V',
                                )

        await cmd_send_04(session, message, state, app_context=app_context)
    else:
        keyboard = get_kb_return(message.from_user.id, app_context=app_context)
        await send_message(session, message, f"{my_gettext(message, 'bad_sum', app_context=app_context)}\n{data.get('msg', '')}",
                           reply_markup=keyboard, app_context=app_context)


@router.callback_query(F.data == "Fest2024")
async def cmd_fest(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    if data.get('user_lang') and data.get('user_lang') == 'ru':
        msg = 'Выберите участника '
    else:
        msg = 'Choose participant '

    kb_tmp = []
    for level_name in config.fest_menu:
        kb_tmp.append([types.InlineKeyboardButton(text=f"{level_name}",
                                                  callback_data=SendLevel24(
                                                      level_1=level_name).pack()
                                                  )])

    kb_tmp.append(get_return_button(callback, app_context=app_context))
    await send_message(session, callback, msg + long_line(),
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp),
                       need_new_msg=True, app_context=app_context)


@router.callback_query(SendLevel24.filter())
async def cmd_fest_level_24(callback: types.CallbackQuery, callback_data: SendLevel24, state: FSMContext,
                            session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()

    level_1 = callback_data.level_1
    # seller_id = config.fest_menu[level_1]

    await state.set_state(StateFest.sending_sum)
    if data.get('user_lang') and data.get('user_lang') == 'ru':
        menu_name = level_1
        msg = 'Пришлите сумму в EURMTL для отправки на кошелек ' + menu_name
    else:
        menu_name = level_1
        msg = 'Send sum in EURMTL to wallet ' + menu_name

    # if seller.get('msg') is not None:
    #     msg = seller['msg'] + '\n\n' + msg

    await send_message(session, callback, msg, reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)
    await state.update_data(msg=msg, level_1=level_1)


@router.message(Command(commands=["reload_fest_menu"]))
async def cmd_reload_fest_menu(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.from_user.username != "itolstov":
        return
    config.fest_menu = await load_fest_info()
    await message.answer(text='redy')