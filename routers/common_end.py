from aiogram import Router, types, F
import re
import json

from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import Session


from routers.send import cmd_send_04, cmd_send_choose_token
from routers.sign import cmd_check_xdr
from infrastructure.utils.telegram_utils import clear_last_message_id, clear_state
from other.gpt import gpt_check_message
from infrastructure.utils.stellar_utils import (
    find_stellar_addresses, find_stellar_federation_address, 
    extract_url, is_base64, is_valid_stellar_address
)
from other.stellar_tools import stellar_check_account

router = Router()
router.message.filter(F.chat.type == "private")


from infrastructure.services.app_context import AppContext

@router.message()
async def cmd_last_route(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    if message.chat.type != "private":
        return

    text = message.text
    entities = message.entities or []

    # Check for 'eurmtl.me/sign_tools' in text or entities
    has_sign_tools_link = 'eurmtl.me/sign_tools' in text or any('eurmtl.me/sign_tools' in entity.url for entity in entities if entity.type == 'url')
    if has_sign_tools_link or (len(text) > 60 and is_base64(text)):
        await clear_state(state)
        await clear_last_message_id(message.from_user.id, app_context=app_context)
        xdr_to_check = extract_url(text) if has_sign_tools_link else text
        await cmd_check_xdr(session=session, check_xdr=xdr_to_check,
                            user_id=message.from_user.id, state=state, app_context=app_context)
        return
    message_is_key = len(text) > 55 and is_valid_stellar_address(text)

    # if forwarded
    if message.forward_sender_name or message.forward_from or message_is_key:
        public_key = None
        if message.text:
            public_keys = find_stellar_addresses(message.text)
            if public_keys:
                public_key = public_keys[0]
            else:
                public_key = find_stellar_federation_address(message.text.lower())

        if message.caption and public_key is None:
            public_keys = find_stellar_addresses(message.caption)
            if public_keys:
                public_key = public_keys[0]
            else:
                public_key = find_stellar_federation_address(message.caption.lower())

        if message.forward_from and public_key is None:
            user_repo = app_context.repository_factory.get_user_repository(session)
            public_key, user_id = await user_repo.get_account_by_username('@' + message.forward_from.username)

        if public_key:
            my_account = await stellar_check_account(public_key)
            if my_account:
                await state.update_data(send_address=my_account.account_id)
                if my_account.memo:
                    await state.update_data(memo=my_account.memo, federal_memo=True)

                await state.set_state(None)
                await cmd_send_choose_token(message, state, session, app_context=app_context)
                return

    # if message.from_user.username == "itolstov":
    #     if len(message.text.split()) > 3:
    #         gpt_answer = await gpt_check_message(message.text)
    #
    #         json_match = re.search(r'{.*}', gpt_answer)
    #         if json_match:
    #             json_cmd = json.loads(json_match.group())
    #             # { "command": "transfer", "amount": 10, "address": "GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB", "memo": "спасибо за помощь" }
    #             if json_cmd.get('command') == 'transfer':
    #                 try:
    #                     await state.update_data(send_sum=float(json_cmd.get('amount')),
    #                                             send_asset_code='EURMTL',
    #                                             send_address=json_cmd.get('address'),
    #                                             send_asset_issuer='GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'
    #                                             )
    #                     # if memo exist add memo
    #                     if json_cmd.get('memo'):
    #                         await state.update_data(memo=json_cmd.get('memo'))
    #                     await cmd_send_04(session, message, state)
    #                 except:
    #                     pass
    #
    #         else:
    #             await message.answer(gpt_answer)

    await message.delete()
