import typing

from aiogram import F, Router
from aiogram.filters import Command, CommandObject

from routers.bsn.constants import BACK_CALLBACK_DATA, DELETE_KEY, SEND_CALLBACK_DATA
from routers.bsn.models import BSNData
from routers.bsn.states import BSNStates
from routers.bsn.utils import bsn_stellar_get_data, cmd_gen_data_xdr, get_bsn_kb, make_tag_message, parse_tag
from routers.bsn.value_objects import Address, Key, Value
from routers.start_msg import cmd_show_balance
from routers.sign import cmd_ask_pin, PinState

if typing.TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message
    from aiogram.fsm.context import FSMContext

bsn_router = Router()


@bsn_router.message(Command("bsn", ignore_case=True))
async def bsn_mode_command(message: "Message", state: "FSMContext", command: "CommandObject", session: "Session", **kwargs) -> None:
    tags = await bsn_stellar_get_data(session, message.from_user.id)
    if command.args:
        tag = command.args
        await parse_tag(tag, tags, message)
    await message.reply(
        make_tag_message(tags, message.from_user.id),
        reply_markup=get_bsn_kb(message.from_user.id, not tags.is_empty()),
    )
    await state.set_state(BSNStates.waiting_for_tags)
    await state.update_data({'tags': tags})


@bsn_router.message(BSNStates.waiting_for_tags)
async def process_tags(message: "Message", state: "FSMContext"):
    data = await state.get_data()
    tags = data.get('tags')
    new_tags: list[str] = message.text.split('\n')
    for tag in new_tags:
        tag = tag.strip()
        await parse_tag(tag, tags, message)

    await state.update_data({'tags': tags})
    await message.answer(
        make_tag_message(tags, message.from_user.id),
        reply_markup=get_bsn_kb(message.from_user.id, not tags.is_empty()),
    )


@bsn_router.callback_query(BSNStates.waiting_for_tags, F.data == SEND_CALLBACK_DATA)
async def finish_send_bsn(callback_query: "CallbackQuery", state: "FSMContext", session: "Session",  **kwargs) -> None:
    await state.set_state(None)
    await state.update_data({'tags': None})
    data = await state.get_data()
    bsn_data: BSNData = data['tags']
    xdr = await cmd_gen_data_xdr(bsn_data)
    await state.update_data(xdr=xdr)

    await state.set_state(PinState.sign_and_send)
    await cmd_ask_pin(session, callback_query.from_user.id, state)
    await callback_query.answer()


@bsn_router.callback_query(BSNStates.waiting_for_tags, F.data == BACK_CALLBACK_DATA)
async def finish_back_bsn(callback_query: "CallbackQuery", state: "FSMContext", session: "Session",  **kwargs) -> None:
    await state.set_state(None)
    await state.update_data({'tags': None})
    await cmd_show_balance(session, callback_query.message.chat.id, state)
    await callback_query.answer()
