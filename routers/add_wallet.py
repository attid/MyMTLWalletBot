from aiogram import Router, types
from aiogram.filters import Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from keyboards.common_keyboards import get_kb_return
from utils.aiogram_utils import send_message, my_gettext, logger, cmd_info_message
from utils.stellar_utils import stellar_can_new, stellar_create_new, save_xdr_to_send, stellar_save_new


class StateAddWallet(StatesGroup):
    sending_private = State()
    sending_public = State()


router = Router()


@router.callback_query(Text(text=["AddWalletHaveKey"]))
async def cq_add(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'send_key')
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_private)
    await send_message(callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateAddWallet.sending_private)
async def cmd_send_for(message: types.Message, state: FSMContext):
    try:
        arg = message.text.split()
        if len(arg) == 2:
            public_key = stellar_save_new(message.from_user.id, message.from_user.username, arg[0], False, arg[1])
        else:
            public_key = stellar_save_new(message.from_user.id, message.from_user.username, arg[0], False)
        await state.update_data(public_key=public_key)
        await state.set_state(None)
        await cmd_show_add_wallet_choose_pin(message.chat.id, state,
                                             my_gettext(message, 'for_address').format(public_key))
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(message, my_gettext(message, 'bad_key') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(Text(text=["AddWalletNewKey"]))
async def cq_add(callback: types.CallbackQuery, state: FSMContext):
    if stellar_can_new(callback.from_user.id):
        xdr = stellar_create_new(callback.from_user.id, callback.from_user.username)
        await cmd_info_message(callback.message.chat.id, my_gettext(callback, "try_send"), state)
        save_xdr_to_send(callback.from_user.id, xdr)
        await callback.answer()
    else:
        await callback.answer(my_gettext(callback.message.chat.id, "max_wallets"), show_alert=True)


def get_kb_choose_pin(user_id: int) -> types.InlineKeyboardMarkup:
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_pin'),
                                    callback_data="PIN")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_password'),
                                    callback_data="Password")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_no_password'),
                                    callback_data="NoPassword"),
         ]
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


async def cmd_show_create(chat_id: int, kb_tmp):
    msg = my_gettext(chat_id, 'create_msg')
    await send_message(chat_id, msg, reply_markup=kb_tmp)


async def cmd_show_add_wallet_choose_pin(chat_id: int, state: FSMContext, msg=''):
    msg = msg + my_gettext(chat_id, 'choose_protect')
    await send_message(chat_id, msg, reply_markup=get_kb_choose_pin(chat_id), parse_mode='MARKDOWN')
