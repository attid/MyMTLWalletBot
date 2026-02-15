import typing
from enum import Enum
from collections import defaultdict
from dataclasses import dataclass

import jsonpickle  # type: ignore
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
# from stellar_sdk import AiohttpClient, ServerAsync, TransactionBuilder, Network

from other.lang_tools import my_gettext
# from other.mytypes import MyAccount
from infrastructure.utils.stellar_utils import decode_data_value
# from other.stellar_tools import stellar_get_user_account
from routers.start_msg import cmd_show_balance
from routers.sign import cmd_ask_pin, PinState
from infrastructure.utils.telegram_utils import send_message, clear_last_message_id, clear_state
from infrastructure.utils.common_utils import get_user_id
from infrastructure.services.app_context import AppContext
from other.stellar_tools import have_free_xlm

bsn_router = Router()


class BSNStates(StatesGroup):
    waiting_for_tags = State()


KNOWN_TAGS = (
    "Name",
    "About",
    "Website",
    "OneFamily",
    "Spouse",
    "Guardian",
    "Ward",
    "Sympathy",
    "Love",
    "Divorce",
    "A",
    "B",
    "C",
    "D",
    "Employer",
    "Employee",
    "Contractor",
    "Client",
    "Partnership",
    "Collaboration",
    "OwnerMinority",
    "OwnerMajority",
    "Owner",
    "OwnershipFull",
    "OwnershipMajority",
    "WelcomeGuest",
    "FactionMember"
)

SEND_CALLBACK_DATA = "bsn:send"
BACK_CALLBACK_DATA = "bsn:back"

DELETE_KEY = "DELETE"


class ActionType(Enum):
    ADD = 'ADD'
    REMOVE = 'REMOVE'
    KEEP = 'KEEP'
    CHANGE = 'CHANGE'


class EmptyTag(ValueError):
    """
    Тег должен иметь хотя бы одну букву
    """
    raw_tag: str

    def __init__(self, raw_tag: str) -> None:
        self.raw_tag = raw_tag


class LengthError(ValueError):
    """
    Длина строки {len(value)} превышает 64 символов.
    """
    value: str

    def __init__(self, value: str) -> None:
        self.value = value


class Str64b(str):
    def __new__(cls, value):
        if len(value) > 64:
            raise LengthError(value)
        if len(value) < 1:
            raise ValueError("Не может быть пусто")
        return super().__new__(cls, value)


class Key(Str64b):
    pass


class Value(Str64b):
    pass


class Address(str):
    pass


@dataclass
class Tag:
    key: Key
    num: int | None = None

    def __str__(self):
        return f"{self.key}{self.num or ''}"

    def __hash__(self):
        return hash(self.__str__())

    @property
    def is_known_key(self):
        return self.key.lower() in {tag.lower() for tag in KNOWN_TAGS}

    @classmethod
    def parse(cls, raw_tag: str) -> "Tag":
        letters = ''
        digits = ''
        stop_index = 0
        for index, char in enumerate(raw_tag[::-1]):
            if char.isdigit():
                digits = f'{char}{digits}'
            else:
                stop_index = len(raw_tag) - index
                break
        letters = raw_tag[:stop_index]
        if not letters:
            raise EmptyTag(raw_tag)
        keys_map = {key.lower(): key for key in KNOWN_TAGS}

        key = Key(letters)
        if key.lower() in keys_map:
            key = Key(keys_map[key.lower()])
        num = int(digits) if digits else None
        return cls(key, num)


@dataclass
class BSNRow:
    tag: Tag
    value: Value
    action_type: ActionType = ActionType.KEEP
    old_value: Value | None = None

    def __str__(self):
        return f"{'⚠️ ' if self.tag.is_known_key else ''}{self.tag}: {self.value}"

    @classmethod
    def from_str(cls, tag: str, value: str) -> "BSNRow":
        return BSNRow(Tag.parse(tag), Value(value))

    def change_value(self, new_value: "Value") -> "BSNRow":
        self.old_value = self.value
        self.value = new_value
        self.action_type = ActionType.CHANGE
        return self

    def delete(self) -> "BSNRow":
        self.action_type = ActionType.REMOVE
        return self

    @property
    def is_modify(self):
        return self.action_type in (ActionType.REMOVE, ActionType.CHANGE, ActionType.ADD)

    def is_remove(self):
        return self.action_type == ActionType.REMOVE

    def is_change(self):
        return self.action_type == ActionType.CHANGE


class BSNData:
    address: Address

    _map: dict[Tag, BSNRow]
    _multiple_tag_numbers: dict[Key, set[int]]

    def __init__(self, address: Address, data: list[BSNRow]):
        self.address = address
        self._map = dict()
        self._multiple_tag_numbers = defaultdict(set)

        for row in data:
            self._map[row.tag] = row
            if row.tag.num:
                self._multiple_tag_numbers[row.tag.key].add(row.tag.num)

    def _get_next_num(self, key: Key) -> int:
        num = 1
        while num in self._multiple_tag_numbers[key]:
            num += 1
        return num

    def _make_tag(self, key: Key) -> Tag:
        tag = Tag.parse(key)
        if tag.num is None:
            tag.num = self._get_next_num(tag.key)
        return tag

    def add_new_data_row(self, key: Key, value: Value):
        tag = self._make_tag(key)
        if tag in self._map:
            self._map[tag].change_value(value)
        else:
            row = BSNRow(tag, value, ActionType.ADD)
            self._map[tag] = row
        if tag.num:
            self._multiple_tag_numbers[tag.key].add(tag.num)

    def del_data_row(self, key: Key):
        tag = Tag.parse(key)
        if tag in self._map:
            self._map[tag].delete()
        if tag.num:
            self._multiple_tag_numbers[tag.key].remove(tag.num)

    def is_empty(self):
        return len(self.changed_items()) == 0

    def changed_items(self) -> tuple[BSNRow, ...]:
        return tuple(filter(lambda _row: _row.is_modify, self._map.values()))


def format_bsn_row(bsn_row: BSNRow) -> str:
    action_map = {
        ActionType.REMOVE: '[-]',
        ActionType.ADD: '[+]',
        ActionType.CHANGE: '[*]',
    }
    tag = bsn_row.tag
    value = bsn_row.value
    warn = '⚠️ ' if not tag.is_known_key else ''
    old_value = f" ({bsn_row.old_value})" if bsn_row.is_change() else ''
    return f"{action_map[bsn_row.action_type]} {warn}<code>{tag}</code>: {value}{old_value}\n"


def make_tag_message(bsn_data: BSNData, user_id: typing.Union[CallbackQuery, Message, int, str], app_context: AppContext) -> str:
    user_id_int: int = int(user_id) if isinstance(user_id, str) else get_user_id(user_id)
    help_text = my_gettext(user_id_int, 'bsn_help_text', (DELETE_KEY,), app_context=app_context)

    if bsn_data.is_empty():
        message = my_gettext(user_id_int, 'bsn_empty_message', app_context=app_context)
    else:
        message = my_gettext(user_id_int, 'bsn_address_part', (bsn_data.address,), app_context=app_context)
        flag = False
        for bsn_row in bsn_data.changed_items():
            if not bsn_row.tag.is_known_key:
                flag = True
            message += format_bsn_row(bsn_row)
        if flag:
            message += my_gettext(user_id_int, 'bsn_warning', app_context=app_context)
        message += my_gettext(user_id_int, 'bsn_last_part', app_context=app_context)
    message += help_text
    return message


def get_bsn_kb(user_id: typing.Union[CallbackQuery, Message, int, str],
               app_context: AppContext, send_enabled: bool = False) -> InlineKeyboardMarkup:
    user_id_int: int = int(user_id) if isinstance(user_id, str) else get_user_id(user_id)
    builder = InlineKeyboardBuilder()
    if send_enabled:
        builder.button(text=my_gettext(user_id_int, 'kb_send', app_context=app_context), callback_data=SEND_CALLBACK_DATA)
    builder.button(text=my_gettext(user_id_int, 'kb_back', app_context=app_context), callback_data=BACK_CALLBACK_DATA)
    builder.adjust(1, 1)
    return builder.as_markup()


async def parse_tag(*, tag: str, bsn_data: BSNData, message: Message, session: AsyncSession, app_context: AppContext) -> None:
    if tag:
        tag_value = tag.split(' ', 1)
        if len(tag_value) == 2:
            try:
                if tag_value[1] == DELETE_KEY:
                    bsn_data.del_data_row(key=Key(tag_value[0]))
                else:
                    key, value = tag_value
                    if value.startswith('@'):
                        user_repo = app_context.repository_factory.get_user_repository(session)
                        public_key, user_id = await user_repo.get_account_by_username(value)
                        if public_key:
                            value = public_key
                    bsn_data.add_new_data_row(key=Key(key), value=Value(value))
            except ValueError as e:
                await message.answer(my_gettext(message, 'bsn_error', (parse_exception(e, message, app_context),), app_context=app_context))
        else:
            await message.answer(my_gettext(message, 'bsn_tag_value', (tag,), app_context=app_context))


def parse_exception(exc: Exception, user_id: typing.Union[CallbackQuery, Message, int, str], app_context: AppContext) -> str:
    user_id_int: int = int(user_id) if isinstance(user_id, str) else get_user_id(user_id)
    if isinstance(exc, EmptyTag):
        return my_gettext(user_id_int, 'bsn_empty_tag_error', (exc.raw_tag,), app_context=app_context)
    if isinstance(exc, LengthError):
        return my_gettext(user_id_int, 'bsn_length_error', (len(exc.value), exc.value), app_context=app_context)
    return str(exc)


async def cmd_gen_data_xdr(bsn_data: BSNData, app_context: AppContext) -> str:
    data: dict[str, str | None] = {}
    for bsn_row in bsn_data.changed_items():
        if bsn_row.is_remove():
            data[str(bsn_row.tag)] = None
        else:
            data[str(bsn_row.tag)] = str(bsn_row.value)

    return await app_context.stellar_service.build_manage_data_transaction(
        source_account_id=bsn_data.address,
        data=data
    )


async def bsn_stellar_get_data(session: AsyncSession, user_id: int, app_context: AppContext, public_key=None) -> BSNData:
    if public_key:
        pk = public_key
    else:
         repo = app_context.repository_factory.get_wallet_repository(session)
         wallet = await repo.get_default_wallet(user_id)
         pk = wallet.public_key if wallet else ""

    account_details = await app_context.stellar_service.get_account_details(pk)
    if not account_details:
         data_dict = {}
    else:
         data_dict = account_details.get('data', {})

    for data_name in list(data_dict):
        data_dict[data_name] = decode_data_value(data_dict[data_name])

    return BSNData(
        address=Address(pk),
        data=[BSNRow.from_str(key, value) for key, value in data_dict.items()]
    )


@bsn_router.message(BSNStates.waiting_for_tags)
async def process_tags(message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None or message.chat is None:
        return
    data = await state.get_data()
    tags_json = data.get('tags')
    if not tags_json:
        return
    tags: BSNData = jsonpickle.loads(tags_json)

    text = message.text
    if text.lower().startswith('/bsn'):
        text = text[5:].strip()

    new_tags: list[str] = text.split('\n')

    for tag in new_tags:
        tag = tag.strip()
        await parse_tag(tag=tag, message=message, session=session, bsn_data=tags, app_context=app_context)

    await state.update_data(tags=jsonpickle.dumps(tags))
    await clear_last_message_id(message.chat.id, app_context=app_context)
    await send_message(session, user_id=message, msg=make_tag_message(tags, message.from_user.id, app_context),
                       reply_markup=get_bsn_kb(message.from_user.id, app_context, not tags.is_empty()), app_context=app_context)


@bsn_router.message(Command("bsn", ignore_case=True))
async def bsn_mode_command(message: Message, state: FSMContext, command: CommandObject, session: AsyncSession, app_context: AppContext,
                           **kwargs) -> None:
    if message.from_user is None or message.chat is None:
        return
    await clear_state(state)
    tags = await bsn_stellar_get_data(session, message.from_user.id, app_context=app_context)
    if command.args:
        tag = command.args
        await parse_tag(tag=tag, bsn_data=tags, message=message, session=session, app_context=app_context)
    await clear_last_message_id(message.chat.id, app_context=app_context)
    await send_message(session, user_id=message, msg=make_tag_message(tags, message.from_user.id, app_context),
                       reply_markup=get_bsn_kb(message.from_user.id, app_context, not tags.is_empty()), app_context=app_context)
    await state.set_state(BSNStates.waiting_for_tags)
    await state.update_data(tags=jsonpickle.dumps(tags))


@bsn_router.callback_query(BSNStates.waiting_for_tags, F.data == SEND_CALLBACK_DATA)
async def finish_send_bsn(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext, **kwargs) -> None:
    if callback_query.from_user is None:
        return
    await state.set_state(None)
    data = await state.get_data()
    tags_json = data.get('tags')
    if not tags_json:
        return
    bsn_data: BSNData = jsonpickle.loads(tags_json)

    if not await have_free_xlm(session=session, user_id=callback_query.from_user.id, app_context=app_context):
        await callback_query.answer(my_gettext(callback_query, 'low_xlm', app_context=app_context), show_alert=True)
        return

    xdr = await cmd_gen_data_xdr(bsn_data, app_context=app_context)
    await state.update_data(tags=None)
    await state.update_data(xdr=xdr)

    await state.set_state(PinState.sign_and_send)
    await cmd_ask_pin(session, callback_query.from_user.id, state, app_context=app_context)
    await callback_query.answer()


@bsn_router.callback_query(BSNStates.waiting_for_tags, F.data == BACK_CALLBACK_DATA)
async def finish_back_bsn(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext, **kwargs) -> None:
    if callback_query.message is None or callback_query.message.chat is None:
        return
    await state.set_state(None)
    await state.update_data(tags=None)
    await cmd_show_balance(session, callback_query.message.chat.id, state, app_context=app_context)
    await callback_query.answer()