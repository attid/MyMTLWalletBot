from aiogram import Router, types
import re
import json

from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session

from db.requests import db_get_user_account_by_username
from routers.send import cmd_send_04, cmd_send_choose_token
from utils.gpt import gpt_check_message
from utils.stellar_utils import find_stellar_public_key, find_stellar_federation_address, stellar_check_account

router = Router()


@router.message()
async def cmd_last_route(message: types.Message, state: FSMContext, session: Session):
    if message.chat.type != "private":
        return
    # if forwarded
    if message.forward_sender_name or message.forward_from:
        public_key = None
        if message.text:
            public_key = find_stellar_public_key(message.text)
            if public_key is None:
                public_key = find_stellar_federation_address(message.text.lower())

        if message.caption and public_key is None:
            public_key = find_stellar_public_key(message.caption)
            if public_key is None:
                public_key = find_stellar_federation_address(message.caption.lower())

        if message.forward_from and public_key is None:
            public_key, user_id = db_get_user_account_by_username(session, '@' + message.forward_from.username)

        if public_key:
            my_account = await stellar_check_account(public_key)
            if my_account:
                await state.update_data(send_address=my_account.account.account.account_id)
                if my_account.memo:
                    await state.update_data(memo=my_account.memo, federal_memo=True)

                await state.set_state(None)
                await cmd_send_choose_token(message, state, session)
                return

    if message.from_user.username == "itolstov":
        if len(message.text.split()) > 3:
            gpt_answer = await gpt_check_message(message.text)

            json_match = re.search(r'{.*}', gpt_answer)
            if json_match:
                json_cmd = json.loads(json_match.group())
                # { "command": "transfer", "amount": 10, "address": "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB", "memo": "спасибо за помощь" }
                if json_cmd.get('command') == 'transfer':
                    try:
                        await state.update_data(send_sum=float(json_cmd.get('amount')),
                                                send_asset_code='EURMTL',
                                                send_address=json_cmd.get('address'),
                                                send_asset_issuer='GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'
                                                )
                        # if memo exist add memo
                        if json_cmd.get('memo'):
                            await state.update_data(memo=json_cmd.get('memo'))
                        await cmd_send_04(session, message, state)
                    except:
                        pass

            else:
                await message.answer(gpt_answer)

    await message.delete()
