import pyqrcode as pyqrcode
from aiogram import Router, types
from aiogram.filters import Text
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from routers.start_msg import cmd_info_message, cmd_show_balance
from utils.aiogram_utils import my_gettext
from utils.stellar_utils import stellar_get_user_account

router = Router()


@router.callback_query(Text(text=["Receive"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext, session:Session):
    account_id = (await stellar_get_user_account(session,callback.from_user.id)).account.account_id
    msg = my_gettext(callback, "my_address",(
        account_id,))
    send_file = f'qr/{account_id}.png'
    qr = pyqrcode.create(account_id)
    qr.png(send_file, scale=6)

    await cmd_info_message(session, callback, msg,  send_file=send_file)
    await cmd_show_balance(session, callback.from_user.id, state, need_new_msg=True)
    await callback.answer()
