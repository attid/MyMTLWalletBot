from aiogram import Router, types
from aiogram.filters import Command, Text
from aiogram.fsm.context import FSMContext
from routers.common_setting import cmd_language
from utils.aiogram_utils import cmd_show_balance, send_message
from utils.lang_utils import set_last_message_id, my_gettext

router = Router()


@router.message(Command(commands=["start"]))
async def cmd_start(message: types.Message, state: FSMContext, command: Command):
    # logger.info([message.from_user.id, ' cmd_start'])
    await state.clear()

    # check address
    set_last_message_id(message.from_user.id, 0)
    await send_message(message.from_user.id, 'Loading')

    await cmd_language(message.from_user.id, state)


@router.callback_query(Text(text=["Return"]))
async def callbacks_num(callback: types.CallbackQuery, state: FSMContext):
    await cmd_show_balance(callback.message.chat.id, state)
    await callback.answer()
