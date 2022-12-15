import os

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import fb
from utils.aiogram_utils import bot


class ExitState(StatesGroup):
    need_exit = State()


router = Router()


@router.message(Command(commands=["exit"]))
@router.message(Command(commands=["restart"]))
async def cmd_exit(message: types.Message, state: FSMContext):
    my_state = await state.get_state()
    if message.from_user.username == "itolstov":
        if my_state == ExitState.need_exit:
            await state.set_state(None)
            await message.reply("Chao :[[[")
            exit()
        else:
            await state.set_state(ExitState.need_exit)
            await message.reply(":'[")


async def cmd_send_file(message: types.Message, filename):
    if os.path.isfile(filename):
        await bot.send_document(message.chat.id, types.FSInputFile(filename))


@router.message(Command(commands=["log"]))
async def cmd_log(message: types.Message):
    if message.from_user.username == "itolstov":
        await cmd_send_file(message, 'MyMTLWallet_bot.log')
        await cmd_send_file(message, 'MyMTLWalletBot_check_transaction.log')


@router.message(Command(commands=["err"]))
async def cmd_log(message: types.Message):
    if message.from_user.username == "itolstov":
        await cmd_send_file(message, 'MyMTLWallet_bot.err')


@router.message(Command(commands=["update"]))
async def cmd_update(message: types.Message):
    if message.from_user.username == "itolstov":
        for rec in fb.execsql('select distinct m.user_id, m.user_name from mymtlwalletbot_user m where m.user_id > 0'):
            try:
                username = await bot.get_chat(rec[0])
                if username.username:
                    if username.username.lower() != rec[1]:
                        fb.execsql('update mymtlwalletbot_user m set m.user_name = ? where m.user_id = ?',
                                   (username.username.lower(), username.id))
                        await message.answer(f'username {username.username}')
            except Exception:  # ChatNotFound
                pass
        await message.answer('done')
