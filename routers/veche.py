import jsonpickle
import requests
from aiogram import Router, types
from aiogram.filters import Text, Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session
from routers.start_msg import cmd_info_message
from utils.aiogram_utils import my_gettext, send_message
from keyboards.common_keyboards import get_kb_yesno_send_xdr
from utils.lang_utils import set_last_message_id, check_user_id
from utils.stellar_utils import stellar_get_user_account, stellar_user_sign_message

router = Router()


@router.message(Command(commands=["start"]), Text(contains="veche_"))
async def cmd_start_veche(message: types.Message, state: FSMContext, session: Session):
    await state.clear()

    # check address
    set_last_message_id(session, message.from_user.id, 0)
    await send_message(session, message.from_user.id, 'Loading')

    # if user not exist
    if not check_user_id(session, message.from_user.id):
        await send_message(session, message.from_user.id, 'You dont have wallet. Please run /start')
        return

    await cmd_login_to_veche(session, message.from_user.id, state, token=message.text.split(' ')[1][6:])


async def cmd_login_to_veche(session: Session, chat_id: int, state: FSMContext, token=None, verifier=None):
    # start_cmd  veche_fb2XcCgY69ZuiBCzILwfnPum
    user_key = (await stellar_get_user_account(session, chat_id)).account.account_id
    if verifier:
        message = user_key + verifier
        link = f"https://veche.montelibero.org/auth/page/mymtlwalletbot?" \
               f"account={user_key}" \
               f"&verifier={verifier}&signature=$$SIGN$$"
    else:  # token
        message = user_key + token
        link = f"https://veche.montelibero.org/auth/page/mymtlwalletbot?" \
               f"account={user_key}" \
               f"&signature=$$SIGN$$"

    await state.update_data(message=message, link=link)
    await state.update_data(fsm_func=jsonpickle.dumps(send_veche_link))
    await send_message(session, chat_id, my_gettext(chat_id, 'veche_ask'), reply_markup=get_kb_yesno_send_xdr(chat_id))


async def send_veche_link(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    pin = data.get('pin', '')
    message = data.get('message')
    link = data.get('link')
    msg = stellar_user_sign_message(session, message, user_id, str(pin))
    import urllib.parse
    link = link.replace('$$SIGN$$', urllib.parse.quote(msg))
    await state.update_data(link=link)
    await cmd_info_message(session, user_id, my_gettext(user_id, 'veche_go', (link,)), )
    set_last_message_id(session, user_id, 0)
    await state.set_state(None)


@router.callback_query(Text(text=["MTLToolsVeche"]))
async def cmd_tools_delegate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_key = (await stellar_get_user_account(session, callback.from_user.id)).account.account_id
    verifier = requests.post(f"https://veche.montelibero.org/auth/page/mymtlwalletbot/verifier",
                             params={'account': user_key}).text
    # print(token)
    if verifier:
        await cmd_login_to_veche(session, callback.from_user.id, state, verifier=verifier)
    else:
        await callback.answer('Error with load Veche')
