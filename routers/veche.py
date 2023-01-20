import requests
from aiogram import Router, types
from aiogram.filters import Text, Command
from aiogram.fsm.context import FSMContext

from loguru import logger
from routers.common_setting import cmd_language
from utils.aiogram_utils import my_gettext, send_message
from keyboards.common_keyboards import get_kb_yesno_send_xdr, get_kb_return
from utils.lang_utils import set_last_message_id, check_user_id
from utils.stellar_utils import stellar_get_user_account

router = Router()


@router.message(Command(commands=["start"]), Text(contains="veche_"))
async def cmd_start(message: types.Message, state: FSMContext, command: Command):
    await state.clear()

    # check address
    set_last_message_id(message.from_user.id, 0)
    await send_message(message.from_user.id, 'Loading')

    # if user not exist
    if not check_user_id(message.from_user.id):
        await send_message(message.from_user.id, 'You dont have wallet. Please run /start')
        return

    await cmd_login_to_veche(message.from_user.id, state, token=message.text.split(' ')[1][6:])


async def cmd_login_to_veche(chat_id: int, state: FSMContext, token = None, verifier = None):
    # start_cmd  veche_fb2XcCgY69ZuiBCzILwfnPum
    user_key = stellar_get_user_account(chat_id).account.account_id
    if verifier:
        message = user_key + verifier
        link = f"https://veche.montelibero.org/auth/page/mymtlwalletbot?" \
               f"account={user_key}" \
               f"&verifier={verifier}&signature=$$SIGN$$"
    else: #token
        message = user_key + token
        link = f"https://veche.montelibero.org/auth/page/mymtlwalletbot?" \
               f"account={user_key}" \
               f"&signature=$$SIGN$$"

    await state.update_data(message=message, link=link)
    await send_message(chat_id, my_gettext(chat_id, 'veche_ask'), reply_markup=get_kb_yesno_send_xdr(chat_id))


@router.callback_query(Text(text=["MTLToolsVeche"]))
async def cmd_tools_delegate(callback: types.CallbackQuery, state: FSMContext):
    user_key = stellar_get_user_account(callback.from_user.id).account.account_id
    verifier = requests.post(f"https://veche.montelibero.org/auth/page/mymtlwalletbot/verifier",
                             params={'account': user_key}).text
    # print(token)
    if verifier:
        await cmd_login_to_veche(callback.from_user.id, state, verifier=verifier)
    else:
        await callback.answer('Error with load Veche')
