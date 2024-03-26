from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy.orm import Session
from db.requests import db_delete_wallet, get_wallet_info
from keyboards.common_keyboards import get_return_button, get_kb_return
from routers.start_msg import cmd_show_balance, cmd_change_wallet, WalletSettingCallbackData
from utils.aiogram_utils import send_message, my_gettext, clear_state
from utils.lang_utils import lang_dict, change_user_lang
from utils.stellar_utils import db_set_default_wallets, \
    stellar_get_balance_str


class LangCallbackData(CallbackData, prefix="lang_"):
    action: str


router = Router()


async def cmd_language(session: Session, chat_id: int):
    buttons = []

    for lang in lang_dict:
        buttons.append([
            types.InlineKeyboardButton(text=lang_dict[lang].get('1_lang', 'lang name error'),
                                       callback_data=LangCallbackData(action=lang).pack())
        ])

    buttons.append(get_return_button(chat_id))

    await send_message(session, chat_id, 'Choose language',
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "ChangeLang")
async def cmd_wallet_lang(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await cmd_language(session, callback.from_user.id)


@router.callback_query(LangCallbackData.filter())
async def callbacks_lang(callback: types.CallbackQuery, callback_data: LangCallbackData, state: FSMContext,
                         session: Session):
    logger.info(f'{callback.from_user.id}, {callback_data}')
    lang = callback_data.action
    change_user_lang(session, callback.from_user.id, lang)
    await state.update_data(user_lang=lang)
    await callback.answer(my_gettext(callback, 'was_set', (lang,)))
    await cmd_show_balance(session, callback.from_user.id, state)


@router.callback_query(F.data == "ChangeWallet")
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await cmd_change_wallet(callback.from_user.id, state, session)


@router.message(Command(commands=["change_wallet"]))
async def cmd_wallet_setting_msg(message: types.Message, state: FSMContext, session: Session):
    await message.delete()
    await clear_state(state)
    await cmd_change_wallet(message.from_user.id, state, session)


@router.callback_query(WalletSettingCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: WalletSettingCallbackData,
                     state: FSMContext, session: Session):
    answer = callback_data.action
    idx = str(callback_data.idx)
    user_id = callback.from_user.id
    data = await state.get_data()
    wallets = data['wallets']
    if wallets.get(idx):
        if answer == 'DELETE':
            await state.update_data(idx=idx)
            await cmd_confirm_delete(session, user_id, state)
        if answer == 'SET_ACTIVE':
            db_set_default_wallets(session, user_id, wallets[idx])
            await cmd_change_wallet(callback.message.chat.id, state, session)
        if answer == 'NAME':
            try:
                info = get_wallet_info(session, user_id, wallets[idx])
                msg = f"{wallets[idx]} {info}\n" + my_gettext(callback,
                                                              'your_balance') + '\n' + await stellar_get_balance_str(
                    session, user_id, wallets[idx])
            except:
                msg = f'Error load. Please delete this'
            await callback.answer(msg[:200], show_alert=True)
    await callback.answer()


async def cmd_confirm_delete(session: Session, user_id, state: FSMContext):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_yes'),
                                    callback_data="YES_DELETE"),
         types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_no'),
                                    callback_data="Return"),
         ]
    ]
    #"kb_delete": "Удалить",
    data = await state.get_data()
    idx = data.get('idx')
    wallets = data['wallets']
    wallet = wallets[idx]
    text = my_gettext(user_id, 'kb_delete') + '\n' + wallet
    await send_message(session=session, user_id=user_id, msg=text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "YES_DELETE")
async def cmd_yes_delete(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    idx = data.get('idx')
    wallets = data['wallets']
    db_delete_wallet(session, callback.from_user.id, wallets[idx], idx=int(idx))
    await callback.answer()
    await cmd_change_wallet(callback.message.chat.id, state, session)


@router.callback_query(F.data == "Support")
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await send_message(session, callback, my_gettext(callback, "support_bot"), reply_markup=get_kb_return(callback))
