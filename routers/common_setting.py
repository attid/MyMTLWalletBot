from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy.orm import Session

from keyboards.common_keyboards import get_return_button, get_kb_return
from routers.start_msg import cmd_show_balance, cmd_change_wallet, WalletSettingCallbackData
from infrastructure.utils.telegram_utils import send_message, my_gettext, clear_state
# from other.global_data import global_data
from other.lang_tools import change_user_lang
from other.stellar_tools import stellar_get_balance_str
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.services.localization_service import LocalizationService
from infrastructure.services.app_context import AppContext


class LangCallbackData(CallbackData, prefix="lang_"):
    action: str


router = Router()
router.message.filter(F.chat.type == "private")


async def cmd_language(session: Session, chat_id: int, l10n: LocalizationService, *, app_context: AppContext):
    buttons = []

    for lang in l10n.lang_dict:
        buttons.append([
            types.InlineKeyboardButton(text=l10n.lang_dict[lang].get('1_lang', 'lang name error'),
                                       callback_data=LangCallbackData(action=lang).pack())
        ])

    buttons.append(get_return_button(chat_id, app_context=app_context))

    await send_message(session, chat_id, 'Choose language',
                       reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons), app_context=app_context)


@router.callback_query(F.data == "ChangeLang")
async def cmd_wallet_lang(callback: types.CallbackQuery, state: FSMContext, session: Session, l10n: LocalizationService, app_context: AppContext):
    await cmd_language(session, callback.from_user.id, l10n, app_context=app_context)


@router.callback_query(LangCallbackData.filter())
async def callbacks_lang(callback: types.CallbackQuery, callback_data: LangCallbackData, state: FSMContext,
                         session: Session, l10n: LocalizationService, app_context: AppContext):
    logger.info(f'{callback.from_user.id}, {callback_data}')
    lang = callback_data.action
    await change_user_lang(session, callback.from_user.id, lang)
    await state.update_data(user_lang=lang)
    await callback.answer(my_gettext(callback, 'was_set', (lang,), app_context=app_context))
    await cmd_show_balance(session, callback.from_user.id, state, app_context=app_context)


@router.callback_query(F.data == "ChangeWallet")
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    await cmd_change_wallet(callback.from_user.id, state, session, app_context=app_context)


@router.message(Command(commands=["change_wallet"]))
async def cmd_wallet_setting_msg(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    await message.delete()
    await clear_state(state)
    await cmd_change_wallet(message.from_user.id, state, session, app_context=app_context)


@router.callback_query(WalletSettingCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: WalletSettingCallbackData,
                     state: FSMContext, session: Session, app_context: AppContext):
    answer = callback_data.action
    idx = str(callback_data.idx)
    user_id = callback.from_user.id
    data = await state.get_data()
    wallets = data['wallets']
    if wallets.get(idx):
        if answer == 'DELETE':
            await state.update_data(idx=idx)
            await cmd_confirm_delete(session, user_id, state, app_context=app_context)
        if answer == 'SET_ACTIVE':
            wallet_repo = SqlAlchemyWalletRepository(session)
            await wallet_repo.set_default_wallet(user_id, wallets[idx])
            await cmd_change_wallet(callback.message.chat.id, state, session, app_context=app_context)
        if answer == 'NAME':
            try:
                wallet_repo = SqlAlchemyWalletRepository(session)
                info = await wallet_repo.get_info(user_id, wallets[idx])
                msg = f"{wallets[idx]} {info}\n" + my_gettext(callback, 'your_balance',
                                                              app_context=app_context) + '\n' + await stellar_get_balance_str(
                    session, user_id, wallets[idx])
            except:
                msg = f'Error load. Please delete this'
            await callback.answer(msg[:200], show_alert=True)
    await callback.answer()


async def cmd_confirm_delete(session: Session, user_id, state: FSMContext, app_context: AppContext):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_yes', app_context=app_context),
                                    callback_data="YES_DELETE"),
         types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_no', app_context=app_context),
                                    callback_data="Return"),
         ]
    ]
    #"kb_delete": "Удалить",
    data = await state.get_data()
    idx = data.get('idx')
    wallets = data['wallets']
    wallet = wallets[idx]
    text = my_gettext(user_id, 'kb_delete', app_context=app_context) + '\n' + wallet
    await send_message(session=session, user_id=user_id, msg=text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons), app_context=app_context)


@router.callback_query(F.data == "YES_DELETE")
async def cmd_yes_delete(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    data = await state.get_data()
    idx = data.get('idx')
    wallets = data['wallets']
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    wallet_repo = SqlAlchemyWalletRepository(session)
    await wallet_repo.delete(callback.from_user.id, wallets[idx], wallet_id=int(idx))
    await callback.answer()
    await cmd_change_wallet(callback.message.chat.id, state, session, app_context=app_context)


@router.callback_query(F.data == "Support")
async def cmd_support(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    await send_message(session, callback, my_gettext(callback, "support_bot", app_context=app_context), reply_markup=get_kb_return(callback, app_context=app_context), app_context=app_context)
