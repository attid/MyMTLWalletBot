from aiogram import Router, types
from aiogram.filters import Text
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from loguru import logger

from keyboards.common_keyboards import get_return_button, get_kb_return
from routers.start_msg import cmd_show_balance, cmd_change_wallet, WalletSettingCallbackData
from utils.aiogram_utils import send_message, my_gettext
from utils.lang_utils import lang_dict, change_user_lang
from utils.stellar_utils import stellar_get_wallets_list, stellar_delete_wallets, stellar_set_default_wallets, \
    stellar_get_balance_str


class LangCallbackData(CallbackData, prefix="lang_"):
    action: str


router = Router()


async def cmd_language(chat_id: int, state: FSMContext):
    buttons = []

    for lang in lang_dict:
        buttons.append([
            types.InlineKeyboardButton(text=lang_dict[lang].get('1_lang', 'lang name error'),
                                       callback_data=LangCallbackData(action=lang).pack())
        ])

    buttons.append(get_return_button(chat_id))

    await send_message(chat_id, 'Choose language', reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(Text(text=["ChangeLang"]))
async def cmd_wallet_lang(callback: types.CallbackQuery, state: FSMContext):
    await cmd_language(callback.from_user.id, state)


@router.callback_query(LangCallbackData.filter())
async def callbacks_lang(callback: types.CallbackQuery, callback_data: LangCallbackData, state: FSMContext):
    logger.info(f'{callback.from_user.id}, {callback_data}')
    lang = callback_data.action
    change_user_lang(callback.from_user.id, lang)
    await callback.answer(my_gettext(callback, 'was_set', (lang,)))
    await cmd_show_balance(callback.from_user.id, state)


@router.callback_query(Text(text=["ChangeWallet"]))
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext):
    await cmd_change_wallet(callback.from_user.id, state)


@router.callback_query(WalletSettingCallbackData.filter())
async def cq_setting(callback: types.CallbackQuery, callback_data: WalletSettingCallbackData,
                     state: FSMContext):
    answer = callback_data.action
    idx = int(callback_data.idx)
    user_id = callback.from_user.id
    data = await state.get_data()
    wallets = data['wallets']
    if idx < len(wallets):
        if answer == 'DELETE':
            stellar_delete_wallets(user_id, wallets[idx][0])
            await cmd_change_wallet(callback.message.chat.id, state)
        if answer == 'SET_ACTIVE':
            stellar_set_default_wallets(user_id, wallets[idx][0])
            await cmd_change_wallet(callback.message.chat.id, state)
        if answer == 'NAME':
            try:
                msg = f"{wallets[idx][0]}\n" + my_gettext(callback, 'your_balance') + await stellar_get_balance_str(
                    user_id, wallets[idx][0])
            except:
                msg = f'Error load. Please delete this'
            await callback.answer(msg[:200], show_alert=True)
    await callback.answer()


@router.callback_query(Text(text=["Support"]))
async def cmd_wallet_setting(callback: types.CallbackQuery, state: FSMContext):
    await send_message(callback, my_gettext(callback, "support_bot"), reply_markup=get_kb_return(callback))
